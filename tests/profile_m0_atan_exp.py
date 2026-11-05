#!/usr/bin/env python3
"""MPFR-checked atan/exp ARM instruction comparison, with all adverse rows retained."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import time

from unicorn import UC_HOOK_CODE
from native_eabi_m0_arm_self_test import Machine,bits,real,nan
from m0_mpfr_oracle import Oracle
from profile_m0_math import profile_corpus


def pin(path):
    path=Path(path).resolve();b=path.read_bytes()
    return dict(path=str(path),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())


def corpora(samples,atan_profile):
    groups=[];rng=random.Random(0xA7AEF005)
    if atan_profile:
        prior=json.loads(atan_profile.read_text())
        for g in prior['groups']:
            if g['operation']=='atan':groups.append(('atan','saved_'+g['stream'],[int(r['a'],16) for r in g['cases']]))
    else:
        groups += [('atan','reduced',[bits(rng.uniform(-1,1)) for _ in range(512)]),
                   ('atan','ordinary',[bits(rng.uniform(-32,32)) for _ in range(512)])]
    groups.append(('atan','previous_slow',[0x3FB97996F4E5F9F0,0xBFDD440162570130]))
    groups += [(op,stream,values) for op,stream,values in profile_corpus() if op=='exp']
    for op,limit in [('atan',1.),('atan',64.),('exp',8.),('exp',700.)]:
        groups.append((op,'random_'+str(limit),[bits(rng.uniform(-limit,limit)) for _ in range(samples)]))
    return groups


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline-elf',type=Path,required=True)
    p.add_argument('--elf',type=Path,required=True)
    p.add_argument('--qfplib-elf',type=Path,required=True)
    p.add_argument('--atan-profile',type=Path)
    p.add_argument('--samples',type=int,default=2048)
    p.add_argument('--output-dir',type=Path,required=True)
    a=p.parse_args();assert 0<=a.samples<=20000;a.output_dir.mkdir(parents=True,exist_ok=False)
    paths=dict(base=a.baseline_elf,next=a.elf,qfp=a.qfplib_elf)
    machines={r:Machine(f,True,stack_bytes=16384,instruction_budget=20000000) for r,f in paths.items()}
    assert 'audit_atan' in machines['qfp'].elf.symbols,'Use an actual unary Thumb adapter to qfp_datan2(x,1)'
    oracle=Oracle();groups=corpora(a.samples,a.atan_profile);hits={r:Counter() for r in machines}
    helpers=('atan_round_correct','atan_refine','mk61_m0_cr_atan','exp_round_decide','exp_refine','mk61_m0_cr_exp')
    for role,m in machines.items():
        for name in helpers:
            addresses={address&~1 for symbol,address in m.elf.symbols.items()
                       if symbol==name or symbol.startswith(name+'.')}
            for pc in addresses:
                def hook(uc,address,size,data):hits[data[0]][data[1]]+=1
                m.uc.hook_add(UC_HOOK_CODE,hook,(role,name),begin=pc,end=pc)
    prepared=dict(ELFs={r:pin(f) for r,f in paths.items()},operator=pin(__file__),
        atan_profile=pin(a.atan_profile) if a.atan_profile else None,
        samples=a.samples,cases=sum(len(v) for _,_,v in groups),wall_seconds=600,hardware_IO=0,pow_calls=0)
    (a.output_dir/'PREPARED.json').write_text(json.dumps(prepared,indent=2)+'\n')
    summary=[];start=time.monotonic();allwrong=0
    with gzip.open(a.output_dir/'records.jsonl.gz','xt') as f:
        for op,stream,values in groups:
            rows=[];counts={r:[] for r in paths};eligible={r:[] for r in paths};wrong=Counter();delta=Counter()
            for x in values:
                assert time.monotonic()-start<600
                expected=oracle.reference(op,x);actual={}
                for role,m in machines.items():
                    symbol=('audit_atan' if op=='atan' else 'qfp_dexp') if role=='qfp' else '_ZN12compact_math'+str(len(op))+op+'Ed'
                    before=hits[role].copy();got,_,n=m.call(symbol,x,count=True)
                    good=(nan(got) and bool(got&(1<<51))) if nan(expected) else got==expected
                    actual[role]=dict(result=f'{got:016X}',instructions=n,correct=good,entries=dict(hits[role]-before))
                    counts[role].append(n);wrong[role]+=not good
                comparable=actual['qfp']['correct'] and math.isfinite(real(x)) and (op!='atan' or abs(real(x))<=1024)
                if comparable:
                    for role in paths:eligible[role].append(actual[role]['instructions'])
                diff=actual['next']['instructions']-actual['base']['instructions']
                delta['faster' if diff<0 else 'slower' if diff>0 else 'equal']+=1
                row=dict(operation=op,stream=stream,input=f'{x:016X}',expected=f'{expected:016X}',eligible=comparable,actual=actual)
                rows.append(row);f.write(json.dumps(row,separators=(',',':'))+'\n')
            item=dict(operation=op,stream=stream,cases=len(rows),wrong=dict(wrong),vs_base=dict(delta),
                raw_mean_instructions={r:statistics.mean(c) for r,c in counts.items()},
                correct_reference_cases=len(eligible['base']),
                correct_reference_means={r:statistics.mean(c) if c else None for r,c in eligible.items()},
                largest_regressions=sorted((r for r in rows if r['actual']['next']['instructions']>r['actual']['base']['instructions']),key=lambda r:r['actual']['next']['instructions']-r['actual']['base']['instructions'],reverse=True)[:8])
            summary.append(item);allwrong+=wrong['base']+wrong['next'];print(op,stream,item['raw_mean_instructions'],item['vs_base'],'wrong',dict(wrong),flush=True)
    for r,pth in paths.items():assert pin(pth)==prepared['ELFs'][r]
    report=dict(status='FAIL' if allwrong else 'PASS_FINITE_ATAN_EXP_ARM_COMPARISON',prepared=prepared,groups=summary,
        owned_wrong=allwrong,entries={r:dict(c) for r,c in hits.items()},MPFR_version=oracle.version,
        elapsed_seconds=time.monotonic()-start,hardware_IO=0,pow_calls=0,
        scope='Executed standalone ARM instructions, with functional SIO divider model. Actual unary Qfplib atan2 adapter included. MPFR-matching references in the common finite domain alone enter primary averages; all wrong references and own regressions remain in raw records. Not ROM/SDK cache placement, physical cycles, all-input RNE or universal speed proof.')
    (a.output_dir/'RESULT.json').write_text(json.dumps(report,indent=2)+'\n')
    print(report['status'],'cases',prepared['cases'],'ownwrong',allwrong,flush=True)
    if allwrong:raise SystemExit(1)


if __name__=='__main__':main()
