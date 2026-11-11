"""Verify saved Q4 weights and native RUN00/RUN01 streams after the exam."""
import argparse
from pathlib import Path
import ay_native as base

original_choose=base.choose


def choose(report):
    probes=original_choose(report);seen={p['prompt']for p in probes}
    for case in [0,1]:
        candidates=[h for r in report['navigation']['records']if r['needed_case']==case
           for h in r['history']if h.get('generation',{}).get('action')=='run'
           and h['generation'].get('body')==[case]and not h['generation'].get('codec_error')]
        if candidates:
            h=candidates[0]
            if h['prompt']not in seen:
                probes.append({'prompt':h['prompt'],'generation':h['generation'],'forced_action':None});seen.add(h['prompt'])
    regression=report['regression'];v=regression['generation']
    if not v.get('codec_error')and regression['prompt']not in seen:
        probes.append({'prompt':regression['prompt'],'generation':v,'forced_action':'write'})
    return probes


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);a=parser.parse_args()
    base.choose=choose;base.main(a.root.resolve())
