"""32 unambiguous tasks; real complete repair/review cycles and held-out probes."""
import collections
import copy
import json
import random
from transformers import AutoTokenizer
from br_common import ROOT,SOURCE,BL_ROOT,read,write,rows,save_rows,sha,signature
from bl_spec import install,equal_spec
from bl_vm import CachedVM
from full_isa_math import UNARY,BINARY
from ay_data import make,fixture_inputs
from be_language import question,parse_question
from az_teacher import pool_for
from ay_codec import compile_spec,encode
from ar_spec import verify,equivalent
from bc_data import mutated_specs
from bh_lessons import goal_row
from bl_runtime import Session,render
from bo_review_state_fix import snapshot
from bj_runtime import SPEC_DIAG
from bp_course import encoded


def rendered_goal(g,style,identity):
    g=copy.deepcopy(g);q=question(g['spec'],style,identity);assert equal_spec(parse_question(q,g['spec']['angle']),g['spec'])
    p=pool_for(q);g.update(task=q,pool=p,reference_body=compile_spec(g['spec'],p),spec_body=encode(g['spec'],p))
    if 'bad_spec'in g:g.update(bad_body=compile_spec(g['bad_spec'],p),bad_spec_body=encode(g['bad_spec'],p))
    return g


def wrong(g,vm):
    candidates=list(mutated_specs(g['spec']));expr=['neg',copy.deepcopy(g['spec']['X'])]
    candidates.append({**g['spec'],'X':expr,'writes':{k:expr for k in g['spec']['writes']}})
    bank=g['public_inputs']+g['checker_inputs']+g['audit_inputs']
    for spec in candidates:
        try:
            body=compile_spec(spec,g['pool']);packet=encode(spec,g['pool'])
            if equivalent(spec,g['spec'],bank)['tested_equal']:continue
            if verify(vm,body,g['pool'],spec,bank)['status']!='TESTED':continue
            if verify(vm,body,g['pool'],g['spec'],bank)['status']!='FAIL':continue
            return spec,body,packet
        except (ValueError,ArithmeticError):continue
    raise ValueError(('No valid wrong counterpart',g['id']))


def make_goal(vm,spec,identifier,split,panel,family,rng):
    for _ in range(100):
        g=make(vm,spec,identifier,split,panel,family,rng.randrange(2**31))
        if g:return rendered_goal(g,'bracket',identifier)
    raise ValueError(('Cannot ROM-certify goal',identifier,spec))


def main():
    ROOT.mkdir(exist_ok=True);assert not(ROOT/'frozen.json').exists()
    if(ROOT/'data-frozen.json').exists():return
    install();rng=random.Random(261120111);vm=CachedVM();goals=[]
    exprs=[([op,f'R{i%15:X}'],'unary')for i,op in enumerate(UNARY)]
    exprs += [([op,f'R{(i+3)%15:X}',f'R{(i+8)%15:X}'],'binary')for i,op in enumerate(BINARY)]
    c=lambda x:{'constant':str(x)}
    composites=[['+',['square','R1'],['sin','R2']],['/',['abs','R3'],['+',['square','R4'],c(1)]],
                ['square',['+','R5',c(1.5)]],['sqrt',['abs','R6']],['sin',['*',c(2),'R7']],
                ['neg',['frac','R8']],['*',['ln',['abs','R9']],'RA'],['pow',['+',['abs','RB'],c(1)],c(2.5)],
                ['+',['reciprocal','RC'],c(0.5)]]
    exprs += [(x,'composition')for x in composites];assert len(exprs)==32
    for i,(expr,family)in enumerate(exprs):
        spec={'X':expr,'writes':{f'R{(i+6)%15:X}':expr}if i%4==0 else{},'angle':['DEG','RAD','GRAD'][i%3]}
        g=make_goal(vm,spec,f'br:train:{i:02}','train','train',family,rng);bad,bad_body,bad_packet=wrong(g,vm)
        g.update(bad_spec=bad,bad_body=bad_body,bad_spec_body=bad_packet);goals.append(g)
    out=[]
    def add(g,s,action,origin,body=None):
        r=goal_row(g,0,origin);r.update(state=snapshot(s),action=action,body=body or [],simple=False);out.append(r)
    def review(g,s,good=True):
        s.apply_action('diag',SPEC_DIAG);s.replan_attempted=True
        r=goal_row(g,0,'review_fix'if not equal_spec(s.declared_spec,g['spec'])else'review_keep')
        r.update(state=s.replan_state(),action='write',body=[]);out.append(r)
        s.apply_replan(g['spec_body']if good else g['bad_spec_body'])
    for g in goals:
        out.append(goal_row(g,0,'goal'))
        for case in [0,1]:
            for hyp_ok in [True,False]:
                for code_ok in [True,False]:
                    s=Session(g,g['reference_body']if code_ok else g['bad_body'],vm,'spec',g['spec']if hyp_ok else g['bad_spec'],True,start_case=case)
                    if not hyp_ok:
                        add(g,s,'diag','diag',SPEC_DIAG);review(g,s)
                    elif case==1:
                        # Explicit positive controls after a completed unnecessary
                        # review prevent using the exhausted-review flag as truth.
                        review(g,s)
                    if code_ok:
                        add(g,s,'done','done');s.apply_action('done',[]);assert s.finished
                    else:
                        add(g,s,'write','write');s.apply_action('write',g['spec_body'])
                        add(g,s,'run','run_'+str(1-case),[1-case]);s.apply_action('run',[1-case])
                        add(g,s,'done','done');s.apply_action('done',[]);assert s.finished
            for code_ok in [True,False]:
                s=Session(g,g['reference_body']if code_ok else g['bad_body'],vm,'spec',g['bad_spec'],True,start_case=case)
                s.apply_action('diag',SPEC_DIAG);s.replan_attempted=True;s.apply_replan(g['bad_spec_body'])
                add(g,s,'unsure','unsure_used_review')
            for code_ok in [True,False]:
                s=Session(g,g['reference_body']if code_ok else g['bad_body'],vm,'spec',g['spec'],True,start_case=case)
                for _ in range(11):s.apply_action('run',[case])
                add(g,s,'done'if code_ok else'unsure','done'if code_ok else'unsure_budget')
    # Identical prompts must have identical labels, including SPEC bodies.
    tok=AutoTokenizer.from_pretrained(SOURCE/'hf',local_files_only=True);mapping={};kept=[];duplicates=0
    for r in out:
        text,info=render(r['state'],tok);assert info['fits']
        target=(r['action'],tuple(r['spec_body']if r['action']=='write'else r['body']))
        if text in mapping:
            assert mapping[text]==target,('Conflicting labels',r['group_id']);duplicates+=1;continue
        mapping[text]=target;r['id']=f'br:lesson:{len(kept):04}';assert len(encoded(tok,r)[0])<=1024;kept.append(r)
    panels={'train':goals,'wording':[],'inputs':[],'new_ast':[]}
    for g in goals:
        w=rendered_goal(g,'chain','new:'+g['id']);w.update(id=g['id'].replace(':train:',':wording:'),panel='wording');panels['wording'].append(w)
        n=copy.deepcopy(g);n.update(id=g['id'].replace(':train:',':inputs:'),panel='inputs')
        for attempt in range(100):
            bank=fixture_inputs(g['spec'],rng.randrange(2**31),50)
            if bank and verify(vm,g['reference_body'],g['pool'],g['spec'],bank)['status']=='TESTED'and verify(vm,g['bad_body'],g['pool'],g['bad_spec'],bank)['status']=='TESTED'and verify(vm,g['bad_body'],g['pool'],g['spec'],bank)['status']=='FAIL':break
        else:raise ValueError('Uncertifiable new-input panel')
        n.update(public_inputs=bank[:2],checker_inputs=bank[2:18],audit_inputs=bank[18:]);panels['inputs'].append(n)
    held=[tuple(x)for x in read(BL_ROOT/'ast-frozen.json')['test_triples']];seen={signature(g['spec'])for g in goals}
    attempts=0
    while len(panels['new_ast'])<32:
        attempts+=1
        if attempts>20000:raise RuntimeError('Held AST generation exhausted')
        a,b,cop=rng.choice(held);expr=[a,[b,[cop,f'R{rng.randrange(15):X}']]]
        spec={'X':expr,'writes':{},'angle':rng.choice(['DEG','RAD','GRAD'])};key=signature(spec)
        if key in seen:continue
        g=make(vm,spec,f'br:new_ast:{len(panels["new_ast"]):02}','closed','new_ast','composition',rng.randrange(2**31))
        if not g:continue
        g=rendered_goal(g,'bracket',g['id'])
        try:bad,body,packet=wrong(g,vm)
        except ValueError:continue
        g.update(bad_spec=bad,bad_body=body,bad_spec_body=packet);panels['new_ast'].append(g);seen.add(key)
    save_rows(ROOT/'lessons.jsonl',kept)
    for panel,items in panels.items():save_rows(ROOT/(panel+'.jsonl'),items)
    write(ROOT/'data-frozen.json',{'files':{n:sha(ROOT/n)for n in ['lessons.jsonl',*[p+'.jsonl'for p in panels]]},
          'training_goals':32,'rows':len(kept),'origins':dict(collections.Counter(r['origin']for r in kept)),
          'identical_duplicate_prompts_removed':duplicates,'conflicting_prompt_labels':0,'all_labels_real_ROM_verified':True,
          'review_flag_snapshot_correct':True,'question_parser_roundtrip_checked':True,'panels':{p:len(x)for p,x in panels.items()},
          'new_AST_triples_excluded_from_parent_task_training':True,'basic_train_goals_may_overlap_parent_training':True,
          'no_device_access':True,'SGD_started':False})
    print(json.dumps(read(ROOT/'data-frozen.json')),flush=True)


if __name__=='__main__':main()
