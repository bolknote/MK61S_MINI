"""ROM-verified complete cycles, real own errors, and matched code/spec contrasts."""
import collections
import concurrent.futures
import copy
import hashlib
import json
from cb_common import ROOT,CA_ROOT,CA_RESULTS,read,write,rows,save_rows,sha
from cb_runtime import session_type,snapshot,render
from bj_runtime import SPEC_DIAG
from ay_codec import encode
from ar_spec import equivalent,verify,infer
from bl_spec import install
from bl_vm import CachedVM
from be_language import paths3
from aq_protocol import prompt_ids,header_ids,NO_BODY,END
from ha_protocol import bytes_text
from transformers import AutoTokenizer
from cb_common import ACTOR


def target(session,goal,vm):
    bank=goal['public_inputs']+goal['checker_inputs']+goal['audit_inputs']
    hyp=equivalent(session.declared_spec,goal['spec'],bank)['tested_equal']
    good=verify(vm,session.body,session.pool,goal['spec'],bank)['status']=='TESTED'
    remaining=12-len(session.history);eligible,missing,failed=session.eligibility()
    if not hyp:
        needed=3 if good else 5
        action='unsure'if session.replan_attempted or remaining<needed else'diag'
        return action,SPEC_DIAG[:]if action=='diag'else[],hyp,good
    if not good or failed:
        return ('write',encode(goal['spec'],session.pool),hyp,good)if remaining>=3 else('unsure',[],hyp,good)
    if missing:
        return ('run',[missing[0]],hyp,good)if remaining>=len(missing)+1 else('unsure',[],hyp,good)
    return 'done',[],hyp,good


def clean_chunk(goals):
    install();vm=CachedVM(1024);Session=session_type('full');out=[]
    def add(g,s,origin,contrast=None):
        action,body,hyp,good=target(s,g,vm)
        row={'task_id':g['id'],'question':g['task'],'family':g['family'],'state':snapshot(s),'target_spec':g['spec'],
            'action':action,'body':body,'origin':origin,'spec_correct':hyp,'code_correct':good,
            'retain':g.get('curriculum')=='old_success'and hyp and action in ['write','run','done']}
        if contrast:row.update(contrast_id=contrast,contrast_side='good'if good else'bad')
        out.append(row);return action,body
    def review(s,g,correct):
        before=list(s.body);s.apply_action('diag',SPEC_DIAG);s.pending_replan=False;s.replan_attempted=True
        s.apply_replan(encode(g['spec']if correct else g['bad_spec'],s.pool));assert s.body==before
    for g in goals:
        bank=g['public_inputs']+g['checker_inputs']+g['audit_inputs']
        assert verify(vm,g['reference_body'],g['pool'],g['spec'],bank)['status']=='TESTED'
        assert verify(vm,g['bad_body'],g['pool'],g['spec'],bank)['status']!='TESTED'
        identity=g['id']+':'+hashlib.sha256(g['task'].encode()).hexdigest()[:10]
        for case in [0,1]:
            for hyp_ok in [True,False]:
                for code_ok in [True,False]:
                    s=Session(g,g['reference_body']if code_ok else g['bad_body'],vm,'spec',g['spec']if hyp_ok else g['bad_spec'],True,start_case=case)
                    contrast=identity+f':{case}:initial'if hyp_ok else None
                    add(g,s,'clean_initial',contrast)
                    if hyp_ok!=code_ok:
                        s.apply_action('done',[]);assert not s.finished
                        add(g,s,'after_reject')
                    if not hyp_ok:
                        review(s,g,True)
                        add(g,s,'after_review',identity+f':{case}:review')
                    elif case==1:
                        # A used review must also occur with a correct hypothesis.
                        review(s,g,True);add(g,s,'positive_used_review')
                    if not code_ok:
                        s.apply_action('write',encode(g['spec'],s.pool));action,body=add(g,s,'after_write')
                        assert action=='run';s.apply_action(action,body)
                        action,body=add(g,s,'after_run');assert action=='done'
                    s.apply_action('done',[]);assert s.finished
                    assert verify(vm,s.body,s.pool,g['spec'],bank)['status']=='TESTED'
            for code_ok in [True,False]:
                s=Session(g,g['reference_body']if code_ok else g['bad_body'],vm,'spec',g['bad_spec'],True,start_case=case)
                review(s,g,False);action,_=add(g,s,'failed_review');assert action=='unsure'
            for code_ok in [True,False]:
                s=Session(g,g['reference_body']if code_ok else g['bad_body'],vm,'spec',g['spec'],True,start_case=case)
                for _ in range(11):s.apply_action('run',[case])
                action,_=add(g,s,'budget_control');assert action==('done'if code_ok else'unsure')
    return out


def onpolicy(goals,held):
    install();vm=CachedVM(2048);Session=session_type('full');byid={g['id']:g for g in goals};out=[];counts=collections.Counter()
    sources=[CA_ROOT/f'baseline-{split}-own.json'for split in ['development','closed']]
    sources += [CA_RESULTS/f'{split}-notes-own.json'for split in ['development','closed']]
    for path in sources:
        for record in read(path)['own']['records']:
            g=byid.get(record['task_id'])
            if g is None:continue
            s=Session(g,g['reference_body']if record['initially_correct']else g['bad_body'],vm,'spec',record['initial_spec'],True)
            for h in record['history']:
                generation=h.get('generation',{})
                if generation.get('profile')=='actor':
                    state=snapshot(s);allowed=True
                    for spec in [state['declared_spec']]:
                        if spec and paths3(spec['X'])&held:allowed=False
                    try:allowed=allowed and not(paths3(infer(s.body,s.pool,g['spec']['angle'])['X'])&held)
                    except(ValueError,ArithmeticError,KeyError):allowed=False
                    if allowed:
                        action,body,hyp,good=target(s,g,vm)
                        out.append({'task_id':g['id'],'question':g['task'],'family':g['family'],'state':state,'target_spec':g['spec'],
                            'action':action,'body':body,'origin':'onpolicy_'+action,'spec_correct':hyp,'code_correct':good,
                            'retain':g.get('curriculum')=='old_success'and hyp and action in ['write','run','done'],
                            'source_report':str(path.relative_to(CA_ROOT)),'source_action':generation.get('action')})
                        counts['states']+=1
                    else:counts['uninferrable_or_held_state_excluded']+=1
                if h['kind']=='generation_error':break
                if h['kind']=='replan':
                    s.pending_replan=False;s.replan_attempted=True;s.apply_replan(h['body'])
                elif h.get('harness_forced')=='missing_public_run':
                    assert s.pending_runs and s.pending_runs.pop(0)==h['body'][0];s.apply_action('run',h['body'])
                elif generation and generation.get('action'):
                    try:s.apply_action(generation['action'],generation['body'])
                    except(ValueError,ArithmeticError,RuntimeError)as error:
                        s.observation='ERROR '+str(error);s.history.append({'kind':'error','observation':s.observation})
                    if h['kind']=='write':assert s.body==h['body']
            counts['episodes']+=1
    return out,dict(counts)


def main():
    assert not(ROOT/'frozen.json').exists()
    if(ROOT/'lessons-frozen.json').exists():return
    assert read(ROOT/'teacher-frozen.json')['complete'];goals=rows(ROOT/'retired-train.jsonl')+rows(ROOT/'train.jsonl')
    held={tuple(t)for values in read(ROOT/'ast-frozen.json')['held_triples'].values()for t in values}
    out=[];chunks=[goals[i:i+12]for i in range(0,len(goals),12)]
    with concurrent.futures.ProcessPoolExecutor(4)as pool:
        for i,values in enumerate(pool.map(clean_chunk,chunks)):
            out.extend(values)
            if i%4==0:print({'clean_chunks':i+1,'of':len(chunks),'states':len(out)},flush=True)
    values,onpolicy_counts=onpolicy(goals,held);out.extend(values)
    tok=AutoTokenizer.from_pretrained(ACTOR/'hf',local_files_only=True);kept=[];labels={};seen=set();stats=collections.Counter();label_conflicts=[]
    for row in out:
        action=row['action'];body=row['body'];header=[]if action in NO_BODY else header_ids(tok,action)
        tail=[]if action in NO_BODY else tok.encode(bytes_text(body),add_special_tokens=False)+[END]
        assert len(header)+len(tail)<=160
        texts={f:render(row['state'],f)for f in ['original','full','notes']}
        fitted={f:len(prompt_ids(tok,p))+len(header)+len(tail)<=1000 for f,p in texts.items()}
        if not fitted['notes']:stats['unfitted_notes_excluded']+=1;continue
        if not fitted['full']:stats['notes_only_states']+=1
        row['full_fits']=fitted['full'];row['original_fits']=fitted['original'];target_label=(action,tuple(body))
        formats=['notes']+(['full']if fitted['full']else[])
        if row['retain']and fitted['original']:formats.append('original')
        for f in formats:
            p=texts[f]
            if p in labels and labels[p]!=target_label:label_conflicts.append({'task_id':row['task_id'],'origin':row['origin'],'format':f,'old':labels[p],'new':target_label})
            labels[p]=target_label
        identity=(texts['notes'],action,tuple(body),row.get('contrast_id'),row.get('contrast_side'),row['retain'])
        if identity in seen:stats['duplicates_removed']+=1;continue
        seen.add(identity);row['id']=f'cb:state:{len(kept):06}';kept.append(row);stats['kept_'+row['origin']]+=1;stats['action_'+action]+=1
    write(ROOT/'label-check.json',{'conflicts':label_conflicts,'count':len(label_conflicts)});assert not label_conflicts,label_conflicts[:5]
    save_rows(ROOT/'lessons.jsonl',kept)
    write(ROOT/'lessons-frozen.json',{'complete':True,'states':len(kept),'goals':len(goals),'onpolicy':onpolicy_counts,'counts':dict(stats),
        'all_clean_cycles_ROM_verified':True,'no_hidden_truth_in_prompts':True,'review_availability_visible':True,
        'matching_prompt_label_conflicts':0,'held_ASTs_excluded_from_states':True,'files':{n:sha(ROOT/n)for n in ['lessons.jsonl','label-check.json']}})
    print(read(ROOT/'lessons-frozen.json'),flush=True)


if __name__=='__main__':main()
