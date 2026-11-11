"""Actual ROM rollouts, matched code/condition pairs and retired actor mistakes."""
import collections
import concurrent.futures
import copy
import json
import random
from ba_common import ROOT,PARENT,TRAIN_NUMBERS,rows,read,write,save_rows,sha
from ba_pools import rng_for
from ba_data import mutated_specs
from ay_codec import compile_spec,encode
from az_lessons import mutant as fallback_mutant
from az_runtime import Session,snapshot,goal_state
from ay_data import op_count
from ar_spec import verify
from full_isa_vm import FullVM,build
from ha_protocol import assemble


def wrong_program(g,vm,kind):
    candidates=list(mutated_specs(g['spec']));rng=rng_for(g['id']+str(g.get('paraphrase',0)));rng.shuffle(candidates)
    # Nearby literal and register replacements, rather than always replacing with zero.
    def visit(node,path):
        if isinstance(node,dict)and'constant'in node:
            for v in g['pool']:
                if v==node['constant']:continue
                expr=copy.deepcopy(g['spec']['X'])
                if not path:expr={'constant':v}
                else:
                    at=expr
                    for i in path[:-1]:at=at[i]
                    at[path[-1]]={'constant':v}
                candidates.append({**g['spec'],'X':expr,'writes':{r:expr for r in g['spec']['writes']}})
        if isinstance(node,list):
            for i,c in enumerate(node[1:],1):visit(c,path+[i])
    visit(g['spec']['X'],[]);rng.shuffle(candidates)
    for spec in candidates[:35]:
        try:body=compile_spec(spec,g['pool'])
        except (ValueError,ArithmeticError):continue
        if verify(vm,body,g['pool'],g['spec'],g['audit_inputs'])['status']!='FAIL':continue
        raw=assemble(body,g['pool'],'asm')
        if all(vm.execute(raw,x,angle=g['spec']['angle'],max_commands=128,max_frames=1024)[0]['status']=='stopped'for x in g['public_inputs']):return body,True
    return fallback_mutant(g,vm,kind)[1],False


def make_row(g,s,action,origin,correct,body=None,priority=False):
    state=goal_state(g)if s is None else snapshot(s)
    assert not set(state['view'])&{'spec','expected','hidden_tests','reference_code'}
    return {'group_id':g['id'],'state':state,'action':action,'body':list(body or[]),'origin':origin,
        'correctness':int(correct),'target_spec':g['spec'],'reference_body':g['reference_body'],'spec_body':g['spec_body'],
        'simple':op_count(g['spec']['X'])<=2,'family':g['family'],'curriculum':g.get('curriculum','new'),'priority':bool(priority)}


def chunk_lessons(groups):
    vm=FullVM();out=[];counts=collections.Counter()
    for i,g in enumerate(groups):
        bad,plausible=wrong_program(g,vm,['operation','argument','order'][i%3]);counts['plausible_stopped_errors']+=plausible
        assert verify(vm,g['reference_body'],g['pool'],g['spec'],g['audit_inputs'])['status']=='TESTED'
        def add(s,action,origin,correct,body=None,priority=False):
            if action=='done':assert s.eligibility()[0]
            out.append(make_row(g,s,action,origin,correct,body,priority))
        add(None,'write','goal',False)
        for case in [0,1]:
            good=Session(g,g['reference_body'],vm,'hex',start_case=case);add(good,'done','done',True)
            s=Session(g,bad,vm,'hex',start_case=case);add(s,'write','repair',False,priority=True)
            s.apply_action('write',g['reference_body']);add(s,'run','run',True,[1-case]);s.apply_action('run',[1-case]);add(s,'done','done',True)
            t=Session(g,g['reference_body'],vm,'hex',start_case=case);t.apply_action('write',bad)
            add(t,'run','run',False,[1-case]);t.apply_action('run',[1-case]);add(t,'write','repair',False,priority=True)
            t.apply_action('write',g['reference_body']);add(t,'run','run',True,[case]);t.apply_action('run',[case]);add(t,'done','done',True)
        for correct,body in [(True,g['reference_body']),(False,bad)]:
            s=Session(g,body,vm,'hex')
            for _ in range(11):s.apply_action('run',[s.case])
            add(s,'done'if correct else'unsure','done'if correct else'unsure',correct)
    return out,dict(counts)


def main():
    assert not(ROOT/'frozen.json').exists()
    if(ROOT/'lessons-frozen.json').exists():return
    f=read(ROOT/'teacher-frozen.json')
    for n,d in f['files'].items():assert sha(ROOT/n)==d,n
    groups=rows(ROOT/'train-clean.jsonl');build();output=[];counts=collections.Counter()
    chunks=[groups[i:i+24]for i in range(0,len(groups),24)]
    with concurrent.futures.ProcessPoolExecutor(4)as executor:
        for i,(values,c)in enumerate(executor.map(chunk_lessons,chunks)):
            output.extend(values);counts.update(c)
            if i%10==0:print(json.dumps({'chunks':i+1,'of':len(chunks),'lessons':len(output)}),flush=True)
    vm=FullVM();by_id={g['id']:g for g in groups}
    # Short literal-copy tasks explicitly teach value-to-index binding.
    from az_teacher import pool_for
    template=groups[0]
    for i,value in enumerate(TRAIN_NUMBERS):
        for style in [0,1]:
            task=('Возьми число '+value+'.'if style==0 else'Оставь в X число '+value+'; память сохрани и остановись.')
            g={**template,'id':f'ba:binding:{i:03}:{style}','task':task,'pool':pool_for(task),'family':'binding','curriculum':'binding',
                'spec':{'X':{'constant':value},'writes':{},'angle':'RAD'}}
            g['reference_body']=compile_spec(g['spec'],g['pool']);g['spec_body']=encode(g['spec'],g['pool'])
            assert verify(vm,g['reference_body'],g['pool'],g['spec'],g['audit_inputs'])['status']=='TESTED'
            output.append(make_row(g,None,'write','goal',False));counts['literal_binding_goals']+=1
    for g in sorted(by_id.values(),key=lambda x:x['id']):
        partner=by_id.get(g.get('contrast_partner'))
        if partner is None:continue
        p=copy.deepcopy(partner);p['pool']=list(g['pool']);p['reference_body']=compile_spec(p['spec'],p['pool']);p['spec_body']=encode(p['spec'],p['pool'])
        for code,correct_goal,wrong_goal in [(g['reference_body'],g,p),(p['reference_body'],p,g)]:
            assert verify(vm,code,g['pool'],correct_goal['spec'],g['audit_inputs'])['status']=='TESTED'
            assert verify(vm,code,g['pool'],wrong_goal['spec'],g['audit_inputs'])['status']=='FAIL'
            for case in [0,1]:
                a=Session(correct_goal,code,vm,'hex',start_case=case);b=Session(wrong_goal,code,vm,'hex',start_case=case)
                assert a.runs==b.runs and a.body==b.body and a.case==b.case
                pair=[make_row(correct_goal,a,'done','done',True,priority=True),make_row(wrong_goal,b,'write','repair',False,priority=True)]
                for row in pair:row['curriculum']='matched_program_contrast'
                output += pair
                counts['matched_same_program_pairs']+=1
    # Reconstruct real previous failures; the old exam is now explicitly retired.
    previous={g['id']:g for g in rows(PARENT/'closed-clean.jsonl')};old=read(PARENT/'spec/closed.json')
    retired={g['source_id']:g for g in groups if g.get('curriculum')=='retired_exam_error'}
    rng=random.Random(26110826);cohort=[]
    for panel in ['known','novel']:
        candidates=[g for g in previous.values()if g['panel']==panel]
        cohort+=rng.sample(candidates,min(64,len(candidates)))
    cohort_index={g['id']:i for i,g in enumerate(cohort)}
    for record in old['raw']['records']:
        if not(record['finished']and not record['program_correct'])or record['task_id']not in retired:continue
        source=previous[record['task_id']];g=retired[record['task_id']]
        if record['initially_correct']:body=source['reference_body']
        else:
            index=cohort_index[source['id']]
            from az_lessons import mutant as old_mutant
            body=old_mutant(source,vm,['operation','argument','order'][index%3])[1]
        s=Session(source,body,vm,'spec');usable=True
        for h in record['history']:
            v=h.get('generation')
            if not v or v.get('codec_error'):usable=False;break
            if v['action']=='done':break
            try:s.apply_action(v['action'],v['body'])
            except (ValueError,ArithmeticError,RuntimeError):usable=False;break
        if not usable or s.diagnosis:continue
        assert verify(vm,s.body,s.pool,source['spec'],source['audit_inputs'])['status']=='FAIL'
        state=snapshot(s);state['view']['task']=g['task'];state['view']['id']=g['id']
        row=make_row(g,None,'write'if state['remaining']>=3 else'unsure','repair'if state['remaining']>=3 else'unsure',False,priority=True)
        row['state']=state;row['curriculum']='retired_actual_false_DONE';output.append(row);counts['retired_actual_false_DONE']+=1
    for shard in [0,1]:
        f=read(ROOT/f'mined-{shard}.json');assert sha(ROOT/f'mined-{shard}.jsonl')==f['file_sha256']
        values=rows(ROOT/f'mined-{shard}.jsonl');output.extend(values);counts['mined_states']+=len(values)
    for i,row in enumerate(output):row['id']=f'ba:lesson:{i:07}'
    path=ROOT/'lessons.jsonl';save_rows(path,output)
    write(ROOT/'lessons-frozen.json',{'rows':len(output),'counts':dict(collections.Counter(r['origin']for r in output)),
        'details':dict(counts),'sha256':sha(path),'ROM_truth_not_teacher_DONE_opinions':True,
        'same_program_contrasts_and_real_parent_mistakes':True})
    print(json.dumps({'lessons_complete':len(output),'details':dict(counts)}),flush=True)


if __name__=='__main__':main()
