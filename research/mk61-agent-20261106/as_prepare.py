"""Freeze a controlled repeat on the already opened diagnostic conditions."""
import json
import time
from as_common import ROOT,HERE,REPO,MODEL,read,write,sha
from ar_common import ROOT as FIRST


def main():
    assert not(ROOT/'frozen.json').exists()
    goals=read(FIRST/'goals.json');write(ROOT/'goals.json',goals)
    policy=read(FIRST/'policy.json')
    policy.update({'diagnostic_repeat_not_fresh_test':True,
                   'reason':'v1 introduced a short goal prompt, unfamiliar symbolic input and overlong counterexamples',
                   'goal_prompt':'exact AQ full empty-program state; forced WRITE',
                   'actor_prompt':'exact AQ full state before gate rejection; spec kept outside context',
                   'formal_input':'deterministically rendered unambiguous Russian expression tree',
                   'gate_feedback':'compact numeric witness relative to declared spec; no hidden task answer',
                   'weights':'unchanged; all 32 conditions reused for paired protocol control',
                   'claims':'no new held-out quality claim, no checkpoint/threshold selection'})
    write(ROOT/'policy.json',policy)
    sources={p.name:sha(p)for p in HERE.glob('*.py')if not p.name.endswith(('_report.py','_remote.py'))}
    write(ROOT/'frozen.json',{'unix':time.time(),'sources':sources,'goals_sha256':sha(ROOT/'goals.json'),
                             'policy_sha256':sha(ROOT/'policy.json'),'small_packet_sha256':sha(MODEL/'model.mkqb'),
                             'source_experiment_sha256':sha(FIRST/'frozen.json'),
                             'model_outputs_for_this_protocol_seen':False,'original_pilot_opened':True,
                             'training_updates':0})
    print(json.dumps({'frozen_repeat':32,'same_weights':True,'new_final_test':False}))


if __name__=='__main__':main()
