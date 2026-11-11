"""Diagnostic replay: independent teacher spec, unchanged small actor input.

The teacher is not part of a deployable local PicoCalc agent. The replay isolates
whether a correct external specification suffices to prevent bad completions.
"""
import argparse
import json
import time
from pathlib import Path

from ar_common import HERE,REPO,MODEL,read,write,sha,MAX_TURNS
from ar_common import ROOT as FIRST
from ar_runtime import Session as Base
from as_runtime import Session,view_of
from ar_run import Small,episode_record
from ar_spec import equivalent
from full_isa_vm import FullVM

ROOT=REPO/'.build/mk61-agent-20261106/spec-diagnostic-teacher-spec-v1'


def check_frozen():
    f=read(ROOT/'frozen.json')
    for n,d in f['sources'].items():assert sha(HERE/n)==d,n
    for n,d in f['data'].items():assert sha(ROOT/n)==d,n
    assert sha(MODEL/'model.mkqb')==f['small_packet_sha256']


def prepare():
    assert not(ROOT/'frozen.json').exists()
    original=read(REPO/'.build/mk61-agent-20261106/spec-diagnostic-deepseek-v1/translation.json')
    specs=[{'id':r['id'],'spec':r['spec']}for r in original['records']]
    assert len(specs)==32 and all(x['spec']is not None for x in specs)
    write(ROOT/'teacher-specs.json',specs);write(ROOT/'goals.json',read(FIRST/'goals.json'))
    write(ROOT/'policy.json',{'input':'unchanged AQ natural task prompt','spec':'saved independent DeepSeek semantic translation',
                             'gates':['raw','mechanical'],'goals':32,'initial':['correct','wrong'],'episodes':128,
                             'max_turns':12,'training_updates':0,'new_final_test':False,
                             'runtime_has_hidden_task_answers':False,'external_teacher_spec_not_local_autonomy':True,
                             'translation_sha256':sha(REPO/'.build/mk61-agent-20261106/spec-diagnostic-deepseek-v1/translation.json')})
    sources={p.name:sha(p)for p in HERE.glob('*.py')if not p.name.endswith(('_report.py','_remote.py'))}
    write(ROOT/'frozen.json',{'unix':time.time(),'sources':sources,
                             'data':{n:sha(ROOT/n)for n in ['goals.json','policy.json','teacher-specs.json']},
                             'small_packet_sha256':sha(MODEL/'model.mkqb'),'model_outputs_for_this_replay_seen':False})
    print(json.dumps({'frozen_teacher_specs':len(specs),'same_small_weights':True}))


def run():
    check_frozen();goals=read(ROOT/'goals.json');specs={r['id']:r['spec']for r in read(ROOT/'teacher-specs.json')}
    actor=Small();vm=FullVM();started=time.monotonic();records=[]
    jobs=[(g,initial,gate)for g in goals for initial in ['correct','wrong']for gate in ['raw','mechanical']]
    for at in range(0,len(jobs),16):
        chunk=jobs[at:at+16];sessions=[]
        for g,initial,gate in chunk:
            sessions.append(Session(view_of(g,'natural'),g['reference_body']if initial=='correct'else g['wrong_body'],
                                    vm,specs[g['id']],g['checker_inputs'],gate=='mechanical'))
        for turn in range(MAX_TURNS):
            active=[s for s in sessions if not s.finished and not s.abstained and not getattr(s,'exhausted',False)]
            if not active:break
            prompts=[s.request()for s in active];generated=actor.generate(prompts)
            for s,p,v in zip(active,prompts,generated):
                if v.get('codec_error'):
                    s.history.append({'kind':'generation_error','prompt':p,'generation':v});s.exhausted=True;continue
                try:s.apply_action(v['action'],v['body'])
                except (ValueError,ArithmeticError,RuntimeError)as e:
                    s.observation='ERROR '+str(e);s.history.append({'kind':'error','observation':s.observation})
                s.history[-1].update(prompt=p,generation=v)
        for(g,initial,gate),s in zip(chunk,sessions):
            # The independent plan correctness flag is not an actor generation metric.
            plan={'program_to_task':{'status':'NOT_APPLICABLE'}}
            row=episode_record(g,'natural',initial,gate,s,specs[g['id']],plan)
            row['spec_provider']='DeepSeek semantic translation replay';records.append(row)
        write(ROOT/'status.json',{'phase':'episodes','completed':len(records),'total':128,'seconds':time.monotonic()-started})
        print(json.dumps({'episodes':len(records),'seconds':round(time.monotonic()-started,1)}),flush=True)
    check_frozen();write(ROOT/'results.json',{'records':records,'seconds':time.monotonic()-started,
                                             'source_frozen_sha256':sha(ROOT/'frozen.json'),'training_updates':0})
    write(ROOT/'status.json',{'phase':'complete','episodes':len(records),'seconds':time.monotonic()-started})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run']);a=p.parse_args()
    prepare()if a.action=='prepare'else run()
