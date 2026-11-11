"""Fresh expressions, continuous numeric fixtures, and true rejection/review cycles."""
import collections
import concurrent.futures
import copy
import itertools
import json
import random
import time
from bs_common import ROOT,BL_ROOT,BP_ROOT,SOURCE,read,write,rows,save_rows,sha,signature
from br_common import ROOT as BR_ROOT
from bl_common import PRIORS,PARENT
from be_language import paths3,question,parse_question
from bl_spec import install,equal_spec
from full_isa_math import UNARY,BINARY,registers
from full_isa_vm import build
from bl_vm import CachedVM
from ay_data import make,op_count
from az_data import tree
from az_teacher import pool_for
from ay_codec import compile_spec,encode
from ar_spec import verify,equivalent,expected
from bc_data import mutated_specs
from bh_lessons import goal_row
from bl_runtime import Session,render
from bo_review_state_fix import snapshot,corrected
from bj_runtime import SPEC_DIAG
from bp_course import encoded
from transformers import AutoTokenizer


TRAIN_NUMBERS=['0.5','1','1.5','2','2.5','3','-1','-2','0.375','1.625','2.875']
DEV_NUMBERS=['0.63841','1.13841','2.63841','17.63841']
TEST_NUMBERS=['0.71963','1.21963','2.71963','23.71963']


def stream(path):
    if path.exists():
        with path.open()as f:
            for line in f:
                if line.strip():yield json.loads(line)


def wording(g,style,identity):
    g=copy.deepcopy(g);q=question(g['spec'],style,identity)
    assert equal_spec(parse_question(q,g['spec']['angle']),g['spec'])
    pool=pool_for(q);g.update(task=q,pool=pool,reference_body=compile_spec(g['spec'],pool),spec_body=encode(g['spec'],pool),style=style)
    if 'bad_spec'in g:g.update(bad_body=compile_spec(g['bad_spec'],pool),bad_spec_body=encode(g['bad_spec'],pool))
    return g


def continuous(spec,seed,n):
    rng=random.Random(seed);result=[]
    atoms=[-2.75,-1.5,-.625,-.01,0,.01,.25,.75,1.25,2.25,3.5]
    for attempt in range(6000):
        x={f'R{i:X}':str(round(rng.uniform(-3.5,3.5)if rng.random()<.8 else rng.choice(atoms),6))for i in range(15)}
        x.update(X='0.37',Y='-.82',Z='1.23',T='-2.41')
        try:
            y=expected(spec,x)
            if abs(y['X'])>1e6:continue
        except (ValueError,ArithmeticError,OverflowError,KeyError):continue
        result.append(x)
        if len(result)==n:return result
    return None


def replacements(expr,kind):
    out=[]
    def walk(node,path):
        if isinstance(node,str)and kind=='argument':
            out.append((path,f'R{(int(node[1:],16)+1)%15:X}'))
        elif isinstance(node,list):
            if kind=='order':
                if node[0]in ['-','/','pow']:out.append((path,[node[0],*copy.deepcopy(node[1:][::-1])]))
                if node[0]in UNARY and isinstance(node[1],list)and node[1][0]in UNARY:
                    out.append((path,[node[1][0],[node[0],copy.deepcopy(node[1][1])]]))
            for i,c in enumerate(node[1:],1):walk(c,path+[i])
    walk(expr,[])
    for path,newvalue in out:
        new=copy.deepcopy(expr)
        if not path:new=newvalue
        else:
            at=new
            for i in path[:-1]:at=at[i]
            at[path[-1]]=newvalue
        yield new


def wrong(g,vm,kind,held):
    candidates=[]
    for e in replacements(g['spec']['X'],kind):candidates.append((kind,{**g['spec'],'X':e,'writes':{r:e for r in g['spec']['writes']}}))
    candidates.extend(('operation',s)for s in mutated_specs(g['spec']))
    e=['neg',copy.deepcopy(g['spec']['X'])];candidates.append(('negation_fallback',{**g['spec'],'X':e,'writes':{r:e for r in g['spec']['writes']}}))
    bank=g['public_inputs']+g['checker_inputs']+g['audit_inputs']
    for label,s in candidates:
        if paths3(s['X'])&held:continue
        try:
            code=compile_spec(s,g['pool']);packet=encode(s,g['pool'])
            if equivalent(s,g['spec'],bank)['tested_equal']:continue
            if verify(vm,code,g['pool'],s,bank)['status']!='TESTED':continue
            if verify(vm,code,g['pool'],g['spec'],g['checker_inputs'])['status']!='FAIL':continue
            if verify(vm,code,g['pool'],g['spec'],g['audit_inputs'])['status']!='FAIL':continue
            return label,s,code,packet
        except (ValueError,ArithmeticError,OverflowError):continue
    return None


def worker(item):
    spec,identifier,split,family,seed,style,kind,held=item;install();vm=CachedVM(512)
    g=make(vm,spec,identifier,split,family,family,seed)
    if not g:return None
    n=26 if split=='train'else 34 if split=='development'else 50
    bank=continuous(spec,seed+1,n)
    if bank is None or verify(vm,g['reference_body'],g['pool'],spec,bank)['status']!='TESTED':return None
    g.update(public_inputs=bank[:2],checker_inputs=bank[2:18],audit_inputs=bank[18:]);g=wording(g,style,identifier)
    bad=wrong(g,vm,kind,{tuple(x)for x in held})
    if bad is None:return None
    label,hyp,body,packet=bad;g.update(error_kind=label,bad_spec=hyp,bad_body=body,bad_spec_body=packet)
    return g


def main():
    ROOT.mkdir(exist_ok=True);assert not(ROOT/'frozen.json').exists()
    if(ROOT/'data-frozen.json').exists():return
    install();build();rng=random.Random(261121111);started=time.monotonic();seen=set();occupied=set();legacy=[]
    for p in list(dict.fromkeys([*PRIORS,PARENT,BL_ROOT,BP_ROOT])):
        for split in ['train','development','closed']:
            for g in stream(p/(split+'-clean.jsonl')):
                seen.add(signature(g['spec']));occupied|=paths3(g['spec']['X'])
                if p==BL_ROOT and split=='train':legacy.append(g)
    for panel in ['train','wording','inputs','new_ast']:
        for g in stream(BR_ROOT/(panel+'.jsonl')):seen.add(signature(g['spec']));occupied|=paths3(g['spec']['X'])
    safe=[o for o in UNARY if o not in ['exp','pow10','sign','int','frac']]
    free=[t for t in itertools.product(safe,repeat=3)if len(set(t))>=2 and t not in occupied]
    held=rng.sample(free,12);dev=set(held[:6]);test=set(held[6:]);allheld=dev|test
    # A complete retired parser bank is preserved as labels; no old closed result
    # is described as a fresh exam. Only old *training* intents enter replay.
    rng.shuffle(legacy);replay=[];quotas=collections.Counter()
    for g in legacy:
        kind='composition'if op_count(g['spec']['X'])>=3 else'other'
        if quotas[kind]>=1024:continue
        g=copy.deepcopy(g);g.update(id='bs:replay:'+str(len(replay)),source_id=g['id']);replay.append(g);quotas[kind]+=1
        if len(replay)==2048:break
    assert len(replay)==2048
    retired_dev=rows(PARENT/'development-clean.jsonl');rng.shuffle(retired_dev);retention=[];seen_ret=set()
    trainkeys={signature(g['spec'])for g in replay}
    for g in retired_dev:
        k=signature(g['spec'])
        if k in seen_ret or k in trainkeys:continue
        retention.append(g);seen_ret.add(k)
        if len(retention)==96:break
    assert len(retention)==96
    goals={};rejects=collections.Counter();quotas_by_split={
        'train':{'unary':72,'binary':48,'composition':216,'constant':48},
        'development':{'unary':16,'binary':16,'composition':48,'constant':16},
        'closed':{'unary':32,'binary':32,'composition':160,'constant':32}}
    with concurrent.futures.ProcessPoolExecutor(4)as pool:
        for split,quotas in quotas_by_split.items():
            existing=ROOT/(split+'.jsonl')
            if existing.exists():
                values=rows(existing);probe=CachedVM();fixed=[]
                for g in values:
                    if verify(probe,g['bad_body'],g['pool'],g['spec'],g['checker_inputs'])['status']!='FAIL'or verify(probe,g['bad_body'],g['pool'],g['spec'],g['audit_inputs'])['status']!='FAIL':
                        found=wrong(g,probe,g['error_kind'],allheld if split=='train'else test if split=='development'else dev)
                        assert found is not None,g['id']
                        kind,s,body,packet=found;g.update(error_kind=kind,bad_spec=s,bad_body=body,bad_spec_body=packet);fixed.append(g['id'])
                goals[split]=values;save_rows(existing,values)
                print(json.dumps({'resumed_ASTs':split,'goals':len(values),'fixed_nondetectable_wrong_cases':fixed}),flush=True);continue
            values=[]
            for family,n in quotas.items():
                accepted=0;attempt=0
                while accepted<n:
                    batch=[]
                    for _ in range(min(64,max(16,2*(n-accepted)))):
                        attempt+=1
                        if attempt>n*15000:raise RuntimeError((split,family,accepted))
                        literals=TRAIN_NUMBERS if split=='train'else DEV_NUMBERS if split=='development'else TEST_NUMBERS
                        if family=='unary':expr=[list(UNARY)[attempt%len(UNARY)],f'R{rng.randrange(15):X}']
                        elif family=='binary':expr=[list(BINARY)[attempt%len(BINARY)],f'R{rng.randrange(15):X}',{'constant':rng.choice(literals)}]
                        elif family=='constant':expr=tree(rng,literals,True,0,2)
                        elif split!='train':
                            a,b,c=rng.choice(sorted(dev if split=='development'else test));expr=[a,[b,[c,f'R{rng.randrange(15):X}']]]
                            if rng.random()<.6:expr=[rng.choice(['+','-','*']),expr,{'constant':rng.choice(literals)}]
                        else:expr=tree(rng,literals,False,0,rng.choice([3,4]))
                        count=op_count(expr)
                        if count>5 or(family=='composition'and count<2):continue
                        if family!='constant'and not registers(expr):continue
                        p=paths3(expr)
                        if split=='train'and p&allheld:continue
                        if split=='development'and p&test:continue
                        if split=='closed'and p&dev:continue
                        spec={'X':expr,'writes':{f'R{rng.randrange(15):X}':expr}if rng.random()<.2 else{},'angle':rng.choice(['DEG','RAD','GRAD'])}
                        key=signature(spec)
                        if key in seen:continue
                        seen.add(key);identifier=f'bs:{split}:{family}:{attempt:06}'
                        batch.append((spec,identifier,split,family,rng.randrange(2**31),rng.choice(['bracket','named','chain']),['operation','argument','order'][attempt%3],sorted(allheld)if split=='train'else sorted(test if split=='development'else dev)))
                    for g in pool.map(worker,batch):
                        if g is None:rejects['ROM_or_wrong_pair']+=1;continue
                        if accepted==n:continue
                        values.append(g);accepted+=1
                print(json.dumps({'split':split,'family':family,'goals':len(values),'seconds':round(time.monotonic()-started,1)}),flush=True)
            goals[split]=values;save_rows(ROOT/(split+'.jsonl'),values)
    save_rows(ROOT/'replay-goals.jsonl',replay);save_rows(ROOT/'retention.jsonl',retention)
    lessons=[];vm=CachedVM();tok=AutoTokenizer.from_pretrained(SOURCE/'hf',local_files_only=True);Session.tokenizer=tok
    def add(g,s,action,origin,body=None):
        r=goal_row(g,0,origin);r.update(state=snapshot(s),action=action,body=body or [],simple=False);lessons.append(r)
    def review(g,s,origin):
        s.apply_action('diag',SPEC_DIAG);s.replan_attempted=True
        r=goal_row(g,0,origin);r.update(state=s.replan_state(),action='write',body=[]);lessons.append(r)
        s.apply_replan(g['spec_body'])
    def finish(g,s,code_good,origin):
        if not code_good:
            add(g,s,'write',origin);s.apply_action('write',g['spec_body'])
        missing=sorted(set([0,1])-set(s.runs))
        for case in missing:add(g,s,'run','fresh_run',[case]);s.apply_action('run',[case])
        add(g,s,'done','fresh_done');s.apply_action('done',[]);assert s.finished
    for index,g0 in enumerate(goals['train']):
        for variant in [0,1]:
            g=wording(g0,['bracket','chain'][variant],g0['id']+':'+str(variant))
            if variant:
                bank=continuous(g['spec'],261122000+index,26)
                if bank is None or verify(vm,g['reference_body'],g['pool'],g['spec'],bank)['status']!='TESTED'or verify(vm,g['bad_body'],g['pool'],g['bad_spec'],bank)['status']!='TESTED'or verify(vm,g['bad_body'],g['pool'],g['spec'],bank[2:18])['status']!='FAIL'or verify(vm,g['bad_body'],g['pool'],g['spec'],bank[18:])['status']!='FAIL':continue
                g.update(public_inputs=bank[:2],checker_inputs=bank[2:18],audit_inputs=bank[18:])
            lessons.append(goal_row(g,0,'fresh_goal'))
            for code_good in [True,False]:
                body=g['reference_body']if code_good else g['bad_body']
                s=Session(g,body,vm,'spec',g['spec'],True,start_case=variant)
                finish(g,s,code_good,'fresh_write')
                s=Session(g,body,vm,'spec',g['bad_spec'],True,start_case=variant)
                add(g,s,'diag','fresh_diag',SPEC_DIAG);review(g,s,'review_fix');finish(g,s,code_good,'fresh_write')
                # One real rejected DONE, including the positive PUBLIC_RUNS case.
                s=Session(g,body,vm,'spec',g['spec'],True,start_case=variant)
                if code_good:s.runs.pop(1-variant,None)
                result=s.apply_action('done',[]);assert result=='done_rejected'
                if code_good:
                    add(g,s,'run','rejected_good_run',[1-variant]);s.pending_runs=[];s.apply_action('run',[1-variant])
                    finish(g,s,True,'fresh_write')
                else:finish(g,s,False,'rejected_write')
                s=Session(g,body,vm,'spec',g['spec'],True,start_case=variant)
                review(g,s,'review_keep');finish(g,s,code_good,'fresh_write')
                s=Session(g,body,vm,'spec',g['bad_spec'],True,start_case=variant)
                s.apply_action('diag',SPEC_DIAG);s.replan_attempted=True;s.apply_replan(g['bad_spec_body']);add(g,s,'unsure','fresh_unsure')
    for g in replay:lessons.append(goal_row(g,0,'old_translate'))
    old_counts=collections.Counter()
    allowed={'good_spec_good_code':'old_done','good_spec_bad_code':'old_write','replay_repair':'old_write','replay_run_0':'old_run','replay_run_1':'old_run','replay_done':'old_done'}
    for row in stream(BP_ROOT/'lessons.jsonl'):
        kind=allowed.get(row['origin'])
        if not kind or old_counts[kind]>=768:continue
        if paths3(row['target_spec']['X'])&allheld:continue
        row=corrected(row);row.update(origin=kind);lessons.append(row);old_counts[kind]+=1
    kept=[];mapping={};skips=collections.Counter()
    for r in lessons:
        try:
            text,info=render(r['state'],tok);assert info['fits'];encoded(tok,r)
        except (ValueError,AssertionError):skips[r['origin']]+=1;continue
        target=(r['action'],tuple(r['spec_body']if r['action']=='write'else r['body']))
        if text in mapping:
            assert mapping[text]==target,('Conflicting label',r['origin']);continue
        mapping[text]=target;r['id']=f'bs:lesson:{len(kept):06}';kept.append(r)
    save_rows(ROOT/'lessons.jsonl',kept)
    names=['train.jsonl','development.jsonl','closed.jsonl','retention.jsonl','replay-goals.jsonl','lessons.jsonl']
    write(ROOT/'data-frozen.json',{'files':{n:sha(ROOT/n)for n in names},'goals':{k:len(v)for k,v in goals.items()},
        'replay_goals':len(replay),'lessons':len(kept),'origins':dict(collections.Counter(r['origin']for r in kept)),
        'bounded_skips':dict(skips),'dev_triples':sorted(dev),'test_triples':sorted(test),'parent_and_prior_target_triples_absent':True,
        'all_new_signatures_excluded_from_previous_goals':True,'continuous_numeric_fixtures':True,'correct_review_snapshots':True,
        'conflicting_labels':0,'fresh_rejected_DONE_paths_are_real_ROM':True,'SGD_started':False,'seconds':time.monotonic()-started})
    print(json.dumps(read(ROOT/'data-frozen.json')),flush=True)


if __name__=='__main__':main()
