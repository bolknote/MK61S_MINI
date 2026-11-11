"""Local public-only CLI for comparing the simulated harness modes."""
import argparse
import json
from ad_common import ROOT,MODEL
from ad_inference import Bank
from ad_features import Critic
from ad_experiment import rank
from ac_runtime import Session
from ha_protocol import constants,encode,assemble


def main():
    ap=argparse.ArgumentParser();ap.add_argument('question');ap.add_argument('--angle',choices=['RAD','DEG','GRAD'],required=True)
    ap.add_argument('--inputs',default='{}');ap.add_argument('--tests');ap.add_argument('--initial-hex')
    ap.add_argument('--mode',choices=['greedy_guard','best4_likelihood','nonzero_statistics','feedback'],default='greedy_guard');a=ap.parse_args()
    inputs=json.loads(a.tests)if a.tests else[json.loads(a.inputs)]
    task={'id':'local-user','task':a.question,'angle':a.angle,'constants':constants(a.question),
        'public_tests':[{'segments':[{'inputs':i}]}for i in inputs],'max_commands':128,'max_frames':1024}
    selection=json.loads((ROOT/'nonzero-selection.json'if a.mode=='nonzero_statistics'else ROOT/'selection.json').read_text())
    critic=Critic(selection['config']['prior']);bank=Bank();s=Session(task,'asm',gate=True);s.initial_history=0;warned=set()
    if a.initial_hex:s.body=encode(list(bytes.fromhex(a.initial_hex)),s.pool,'asm');s.run(0)
    else:
        g=bank.compiler([task])[0]
        if g.get('codec_error')or g.get('action')!='write':print(json.dumps(g,ensure_ascii=False));return
        s.apply_action('write',g['body']);print(json.dumps(s.history[-1],ensure_ascii=False),flush=True)
    for _ in range(10-len(s.history)):
        p=s.request();g=bank.actions([p])[0]
        if g.get('codec_error'):print(json.dumps(g,ensure_ascii=False));break
        if g['action']=='write'and a.mode!='greedy_guard':
            rows=bank.candidates([p],[g])[0];config={'weight':0.,'repeat':0.,'unreachable':0.}if a.mode=='best4_likelihood'else selection['config']
            index,_=rank(rows,critic,s.pool,config);g=rows[index]
        if a.mode=='feedback'and g['action']=='done'and s.eligibility()[0]:
            body=tuple(s.body or[]);note=critic.note(critic.inspect(body,tuple(s.pool)),selection['feedback_low_prior_threshold'])
            if note and body not in warned:
                warned.add(body);s.observation=note;s.history.append({'kind':'critic_rejected_DONE','observation':note})
                print(json.dumps(s.history[-1],ensure_ascii=False),flush=True);continue
        kind=s.apply_action(g['action'],g['body'])
        if a.mode=='feedback'and kind=='write':
            note=critic.note(critic.inspect(tuple(s.body),tuple(s.pool)),selection['feedback_low_prior_threshold'])
            if note:s.observation=note
        print(json.dumps(s.history[-1],ensure_ascii=False),flush=True)
        if s.finished or s.abstained:break
    try:code=assemble(s.body,s.pool,'asm')if s.body else None
    except ValueError:code=None
    print(json.dumps({'mode':a.mode,'model_declared_DONE':s.finished,'model_abstained':s.abstained,'program':code,
        'verified_task_success':None,'trusted_expected_result_supplied':False,'physical_device_used':False},ensure_ascii=False))


if __name__=='__main__':main()
