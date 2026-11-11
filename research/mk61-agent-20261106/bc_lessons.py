"""Correct repairs, false-check conflicts, exact past errors and broad replay."""
import collections
import concurrent.futures
import copy
import json
from bc_common import ROOT,read,rows,write,save_rows,sha,TRAIN_NUMBERS
from bc_self import bad_hypothesis,rejected_session,wrong_program
from ba_lessons import chunk_lessons,make_row
from az_runtime import Session
from az_teacher import pool_for
from ay_codec import compile_spec,encode
from full_isa_vm import FullVM,build
from ar_spec import verify

def self_chunk(groups):
    vm=FullVM();out=[];stats=collections.Counter()
    for g in groups:
        assert verify(vm,g['reference_body'],g['pool'],g['spec'],g['audit_inputs'])['status']=='TESTED'
        for kind in ['valid_feedback','wrong_hypothesis']:
            try:s=rejected_session(g,vm,kind)
            except (ValueError,ArithmeticError):stats['unconstructable_conflict']+=1;continue
            if s.finished:stats['checker_blind_spot']+=1;continue
            assert s.history[-1]['kind']=='done_rejected'
            if kind=='wrong_hypothesis':
                assert verify(vm,s.body,s.pool,g['spec'],g['audit_inputs'])['status']=='TESTED'
                row=make_row(g,s,'unsure','conflict_unsure',True,priority=True);row['curriculum']='wrong_hypothesis_visible_conflict';out.append(row);stats['preserve_correct_code_conflicts']+=1
            else:
                row=make_row(g,s,'write','self_repair',False,priority=True);row['curriculum']='legitimate_rejection';out.append(row)
                s.apply_action('write',g['spec_body']);other=1-s.case
                out.append(make_row(g,s,'run','run',True,[other]));s.apply_action('run',[other])
                out.append(make_row(g,s,'done','self_done',True));stats['legitimate_repair_cycles']+=1
                s.apply_action('done',[]);assert s.finished
        # A correct program receives the same DONE target before any feedback,
        # regardless of an unobserved private hypothesis: no latent-label leak.
        for hyp in [g['spec'],None]:
            if hyp is None:
                try:hyp=bad_hypothesis(g,vm)[0]
                except (ValueError,ArithmeticError):continue
            s=Session(g,g['reference_body'],vm,'spec',hyp,True)
            out.append(make_row(g,s,'done','self_done',True))
    return out,dict(stats)

def main():
    assert not(ROOT/'frozen.json').exists()
    if(ROOT/'lessons-frozen.json').exists():return
    t=read(ROOT/'teacher-frozen.json')
    for n,d in t['files'].items():assert sha(ROOT/n)==d,n
    groups=rows(ROOT/'train-clean.jsonl');build();output=[];counts=collections.Counter()
    chunks=[groups[i:i+24]for i in range(0,len(groups),24)]
    with concurrent.futures.ProcessPoolExecutor(4)as pool:
        for i,(values,c)in enumerate(pool.map(chunk_lessons,chunks)):
            output+=values;counts.update(c)
            if i%15==0:print(json.dumps({'raw_chunks':i+1,'total':len(chunks),'lessons':len(output)}),flush=True)
    unique=list({g['id']:g for g in groups}.values());chunks=[unique[i:i+16]for i in range(0,len(unique),16)]
    with concurrent.futures.ProcessPoolExecutor(4)as pool:
        for i,(values,c)in enumerate(pool.map(self_chunk,chunks)):
            output+=values;counts.update(c)
            if i%15==0:print(json.dumps({'self_chunks':i+1,'total':len(chunks),'lessons':len(output)}),flush=True)
    vm=FullVM();by_source={g['source_id']:g for g in groups if g.get('curriculum')=='retired_exam_error'}
    originals={}
    for old in rows(ROOT/'retired19-states.jsonl'):
        g=by_source.get(old['task_id'])
        if g is None:continue
        originals[old['task_id']]=old['goal']
        action=old['target_action'];origin='conflict_unsure'if old['reason']=='visible_check_conflict'else'self_repair'if action=='write'else'self_done'if action=='done'else action
        for task in [old['goal']['task'],g['task']]:
            state=copy.deepcopy(old['state']);state['view']['task']=task;state['view']['id']=g['id']
            row=make_row(g,None,action,origin,old['program_correct'],old['target_body'],True);row['state']=state;row['curriculum']='exact_retired_self_error';output.append(row);counts['exact_retired_states']+=1
    for source,original in originals.items():
        row=make_row(original,None,'write','goal',False);row['group_id']=by_source[source]['id'];row['curriculum']='exact_retired_prompt';output.append(row)
        counts['exact_retired_goal_prompts']+=1
    template=groups[0]
    for i,value in enumerate(dict.fromkeys(pool_for('')+TRAIN_NUMBERS)):
        task='Оставь в X число '+value+'; память сохрани и остановись.'
        g={**template,'id':f'bc:binding:{i:03}','task':task,'pool':pool_for(task),'family':'binding','curriculum':'binding',
           'spec':{'X':{'constant':value},'writes':{},'angle':'RAD'}}
        g['reference_body']=compile_spec(g['spec'],g['pool']);g['spec_body']=encode(g['spec'],g['pool']);output.append(make_row(g,None,'write','goal',False))
    for shard in [0,1]:
        f=read(ROOT/f'mined-{shard}.json');assert sha(ROOT/f'mined-{shard}.jsonl')==f['file_sha256']
        values=rows(ROOT/f'mined-{shard}.jsonl');output+=values;counts['parent_self_mined_states']+=len(values)
    for i,row in enumerate(output):row['id']=f'bc:lesson:{i:07}'
    file=ROOT/'lessons.jsonl';save_rows(file,output)
    write(ROOT/'lessons-frozen.json',{'rows':len(output),'counts':dict(collections.Counter(r['origin']for r in output)),
        'details':dict(counts),'sha256':sha(file),'all_rejections_from_real_self_sessions':True,
        'unobserved_hypothesis_never_changes_action_label':True,'conflict_UNSURE_preserves_correct_program':True})
    print(json.dumps({'lessons_complete':len(output),'details':dict(counts)}),flush=True)

if __name__=='__main__':main()
