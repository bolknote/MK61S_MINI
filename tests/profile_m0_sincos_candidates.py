#!/usr/bin/env python3
"""Compare only sin/cos ARM instructions and exact MPFR-directed answers."""
import argparse,collections,gzip,hashlib,json,time
from pathlib import Path
from native_eabi_m0_arm_self_test import Machine,nan
from m0_mpfr_oracle import Oracle
from profile_m0_trig import corpora


def pin(p):
    p=Path(p).resolve();b=p.read_bytes()
    return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('baseline','candidate','qfplib'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--per-stream',type=int,default=5,help='0 runs every frozen stream input')
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    assert 0<=a.per_stream<=10000;a.output.mkdir(parents=True,exist_ok=False)
    paths=dict(base=a.baseline,next=a.candidate,qfp=a.qfplib)
    inputs=[]
    for op,stream,values in corpora():
        if op not in ('sin','cos'):continue
        selected=values if not a.per_stream else values[::max(1,len(values)//a.per_stream)]
        inputs.extend((op,stream,x) for x in selected)
    assert len(inputs)<=10000
    prepared=dict(ELFs={k:pin(v) for k,v in paths.items()},operator=pin(__file__),
        corpus=pin(Path(__file__).with_name('profile_m0_trig.py')),
        oracle=pin(Path(__file__).with_name('m0_mpfr_oracle.py')),
        cases=len(inputs),ARM_call_cap=3*len(inputs),wall_seconds=300,pow_calls=0,
        instructions_are_not_Pico_timings=True)
    (a.output/'PREPARED.json').write_text(json.dumps(prepared,indent=2)+'\n')
    machines={k:Machine(v,True) for k,v in paths.items()};oracle=Oracle()
    groups={};changes=collections.Counter();start=time.monotonic();wrong=[];fatal=None;calls=0
    try:
        with gzip.open(a.output/'records.jsonl.gz','xt') as f:
            for op,stream,x in inputs:
                assert time.monotonic()-start<300 and calls<prepared['ARM_call_cap']
                expected=oracle.reference(op,x);r=dict(operation=op,stream=stream,input=f'{x:016X}',
                    expected=f'{expected:016X}',values={})
                for role,m in machines.items():
                    symbol='qfp_d'+op if role=='qfp' else '_ZN12compact_math3'+op+'Ed'
                    got,_,cost=m.call(symbol,x,count=True);calls+=1
                    good=(nan(got) and bool(got&(1<<51))) if nan(expected) else got==expected
                    r['values'][role]=dict(result=f'{got:016X}',instructions=cost,correct=good)
                    if role!='qfp' and not good:wrong.append(dict(role=role,**r))
                g=groups.setdefault((op,stream),dict(operation=op,stream=stream,cases=0,
                    sums=collections.Counter(),correct_reference_cases=0,
                    correct_reference_sums=collections.Counter(),reference_wrong=0))
                g['cases']+=1
                for k in machines:g['sums'][k]+=r['values'][k]['instructions']
                if r['values']['qfp']['correct']:
                    g['correct_reference_cases']+=1
                    for k in machines:g['correct_reference_sums'][k]+=r['values'][k]['instructions']
                else:g['reference_wrong']+=1
                delta=r['values']['next']['instructions']-r['values']['base']['instructions']
                changes['faster' if delta<0 else 'slower' if delta>0 else 'equal']+=1
                f.write(json.dumps(r,separators=(',',':'))+'\n')
    except Exception as e:fatal=repr(e)
    for g in groups.values():
        g['means']={k:v/g['cases'] for k,v in g['sums'].items()}
        n=g['correct_reference_cases'];g['correct_reference_means']={k:v/n for k,v in g['correct_reference_sums'].items()} if n else None
        print(g['operation'],g['stream'],g['cases'],{k:round(v,1) for k,v in g['means'].items()},flush=True)
    for k,p in paths.items():assert pin(p)==prepared['ELFs'][k]
    result=dict(status='FAIL' if wrong or fatal else 'PASS_FINITE_SINCOS_ARM_COMPARISON',
        prepared=prepared,groups=list(groups.values()),cases=len(inputs),completed_ARM_calls=calls,
        wrong=wrong,fatal=fatal,changes_vs_BASE=dict(changes),elapsed_seconds=time.monotonic()-start,
        new_hardware_IO=0,pow_calls=0,physical_timing=False,all_input_RNE_proof=False)
    (a.output/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'],dict(changes),'seconds',result['elapsed_seconds'],flush=True)
    if wrong or fatal:raise SystemExit(1)


if __name__=='__main__':main()
