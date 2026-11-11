"""Separate harness ablation: reuse a stream only after proving identical input."""
import argparse
import json
from pathlib import Path
from ba_common import ROOT,HERE,read,rows,write,sha
from ba_pools import goal_layout,remap
from ba_lessons import wrong_program
from bb_canonical import request_state,response_body
from az_runtime import Session,snapshot,render,goal_state
from ay_codec import to_program
from ar_spec import verify
from full_isa_vm import FullVM
from ha_protocol import assemble


def main(root):
    assert read(root/'complete.json')['completed'];registration=read(ROOT/'canonical-order-policy.json')
    assert sha(HERE/'bb_canonical.py')==registration['source_sha256']
    assert sha(root/'closed-clean.jsonl')==registration['closed_tasks_sha256']
    goals={g['id']:g for g in rows(root/'closed-clean.jsonl')};vm=FullVM();result={}
    for which in ['parent','spec']:
        report=read(root/which/'closed.json');ordinary={r['id']:r for r in report['primary']['records']};data={}
        for mode in ['extras','full']:
            records=[]
            for probe in report['pool_views'][mode]['records']:
                g=goals[probe['id']];actual=goal_layout(g,mode,g['id']+':exam:'+mode);state=goal_state(actual)
                normalized=request_state(state);old=ordinary[g['id']]
                assert render(normalized,'spec')==old['prompt']
                v=old['generation'];program=[];error=v.get('codec_error')
                if not error:
                    try:
                        mapped=response_body('write',v['body'],state)
                        program,_=to_program(mapped,actual['pool'],actual['spec']['angle'],'spec')
                    except (ValueError,ArithmeticError,RuntimeError)as e:error=str(e)
                check=verify(vm,program,actual['pool'],g['spec'],g['audit_inputs']);passed=check['status']=='TESTED'
                assert passed==old['program_correct']
                if program:assert assemble(program,actual['pool'],'asm')==assemble(old['program'],g['pool'],'asm')
                records.append({'id':g['id'],'passed':passed,'input_prompt_identical':True,'error':error})
            data[mode]={'total':len(records),'passed':sum(r['passed']for r in records),'records':records}
        histories=[]
        for r in report['raw']['records']:
            g=goals[r['task_id']];body=g['reference_body']if r['initially_correct']else wrong_program(g,vm,r['initial'])[0]
            actual=goal_layout(g,'full',g['id']+':canonical-replay');actual_body=remap(body,g['pool'],actual['pool'])
            s=Session(actual,actual_body,vm,'spec',r['declared_spec'],False);prompts=0
            for h in r['history']:
                v=h.get('generation')
                if v is None:raise AssertionError('Missing generation provenance')
                state=snapshot(s);assert render(request_state(state),'spec')==h['prompt'];prompts+=1
                if v.get('codec_error'):s.exhausted=True;break
                try:s.apply_action(v['action'],response_body(v['action'],v['body'],state))
                except (ValueError,ArithmeticError,RuntimeError)as error:
                    s.observation='ERROR '+str(error);s.history.append({'kind':'error','observation':s.observation})
            correct=verify(vm,s.body,s.pool,g['spec'],g['audit_inputs'])['status']=='TESTED'
            assert correct==r['program_correct']and s.finished==r['finished']and s.abstained==r['abstained']
            assert s.eligibility()[0]==r['eligible']
            histories.append({'id':r['id'],'neural_prompts_identical':prompts,'pass':bool(correct and s.finished and s.eligibility()[0]),
                'false_DONE':bool(s.finished and not correct)})
        data['raw_full_table']={'total':len(histories),'passed':sum(r['pass']for r in histories),
            'false_DONE':sum(r['false_DONE']for r in histories),'prompts_identical':sum(r['neural_prompts_identical']for r in histories)}
        result[which]=data;print(json.dumps({'role':which,'canonical_full_primary':data['full']['passed'],'raw':data['raw_full_table']}),flush=True)
    write(root/'canonical-order-eval.json',{'models':result,'middleware_source_sha256':registration['source_sha256'],
       'same_neural_inputs_same_cached_streams_and_real_ROM_replay':True,'no_additional_model_calls':True,
       'not_used_for_weight_selection':True,'diagnostic_harness_ablation_registered_after_training_selection':registration['closed_model_generations_seen'],
       'weights_or_raw_exam_not_modified':True})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();main(a.root.resolve())
