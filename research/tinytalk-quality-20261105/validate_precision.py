#!/usr/bin/env python3
"""Recheck every observed development gate with actual FP16 KV before the fresh audit."""
import argparse
import json
from pathlib import Path

from common import core, load_model, quantize
from evaluate import assess, SCENARIOS, TEST_SCENARIOS
from grade import calibrate


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',required=True)
    p.add_argument('--packed',required=True)
    p.add_argument('--suite',default='suite')
    p.add_argument('--output',required=True)
    p.add_argument('--device',default='cuda')
    p.add_argument('--seed',type=int,default=84119)
    args=p.parse_args()
    out=Path(args.output);assert not out.exists();out.mkdir(parents=True)
    model,tokenizer,device=load_model(args);model.eval().requires_grad_(False)
    quantize.roundtrip(model)
    expected={name:v.detach().clone() for name,v in model.named_parameters()}
    quantize.restore(model,args.packed)
    error=max(float((expected[name]-v).abs().max()) for name,v in model.named_parameters());assert error==0
    del expected
    paths=[Path(args.suite)/(name+'.jsonl') for name in ['dev','test','opened-audit2']]
    parts=[core.read_rows(path) for path in paths]
    extra=Path(args.suite)/'opened-audit2-scenarios.json'
    scenarios=SCENARIOS+TEST_SCENARIOS+json.loads(extra.read_text())
    calibration=calibrate(out/'grade-cache')
    result=assess(model,tokenizer,device,sum(parts,[]),None,out/'grade-cache','fp16-development',scenarios,fp16_kv=True)
    rates=[];contexts=[];at=0
    contextual={'remember_name','follow_hobby','correction','decline_idea','follow_story','name','pet','correct','reject','project'}
    for part in parts:
        grades=result['direct']['details'][at:at+len(part)];at+=len(part)
        rates.append(sum(v['pass'] for v in grades)/len(grades))
        group=[g for c,g in zip(part,grades) if c.get('family') in contextual]
        assert group;contexts.append(sum(v['pass'] for v in group)/len(group))
    multi=[];at=0
    sizes=[sum(len(s) for s in SCENARIOS),sum(len(s) for s in TEST_SCENARIOS),3*len(json.loads(extra.read_text()))]
    for size in sizes:
        grades=result['multi_turn']['details'][at:at+size];at+=size
        assert len(grades)==size;multi.append(sum(v['pass'] for v in grades)/size)
    goal=result['goal_met'] and min(rates)>=.8 and min(contexts)>=.72 and min(multi)>=.78
    result['unpartitioned_goal_met']=result['goal_met']
    result['goal_met']=goal
    result['development_partitions']={'previous_dev_direct':rates[0],'opened_audit_direct':rates[1],
        'opened_audit2_direct':rates[2],'context_rates':contexts,'multi_turn_rates':multi,
        'new_reserved_audit_opened':False}
    report={'raw_checkpoint_sha256':core.digest(Path(args.model)/'model.safetensors'),
        'packed_sha256':core.digest(args.packed),'packed_reload_max_abs_error':error,
        'suite_sha256':{path.name:core.digest(path) for path in paths},'extra_scenarios_sha256':core.digest(extra),
        'fp16_kv':True,'goal_met':goal,'direct_rates':rates,'context_rates':contexts,'multi_turn_rates':multi,
        'calibration':calibration,'result':result,'reserved_audit3_opened':False,'native_runtime_measured':False}
    core.save(out/'validation.json',report)
    print(json.dumps({k:report[k] for k in ['goal_met','direct_rates','context_rates','multi_turn_rates','fp16_kv']}),flush=True)


if __name__=='__main__':main()
