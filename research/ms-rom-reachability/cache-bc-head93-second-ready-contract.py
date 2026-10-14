#!/usr/bin/env python3
"""Local ROM contracts for the spurious SWAP-ready selector.

Only observed control contexts, free numerical marker/header data. No
state import into a calculator and no global/arbitrary-bank completion.
"""
from pathlib import Path
import runpy
import sys
from z3 import And,BitVec,BitVecVal,If,Or,UGE

root=Path(__file__).resolve().parent
causal=runpy.run_path(str(root/'cache-bc-head93-second-swap-causal-all5.py'))
num=causal['num'];r,w,q=(num[n] for n in ('r','w','q'))
data=causal['read_evidence'](sys.argv[1])
rows=data['windows']['packet-reopen-control-swap']


def execute(v,code,replace):
    a=r['concrete_primary'](v['fullBefore']['ik1302'])
    for j,value in replace.items():a.m[j]=value
    p=w['base'](a,code);out=[]
    b=w['ex'](a,code,*num['prior']['all5']['pins'](v)['ik1302'],
        serial_inputs=[q['N4'](n) for n in v['fullAfter']['ik1302']['m']],emitted_outputs=out)
    return a,p,b,out


def run():
    scan=next(v for v in rows if v['word']==2889671)
    assert scan['ip']==0x9B and scan['numericOwner']==['unclassified:aux0']
    flag=BitVec('ready_scan_M22',4)
    a,p,b,out=execute(scan,0x9B,{22:flag})
    w['prove'](p,And(w['ip'](b)==If(flag==15,BitVecVal(0x9C,8),BitVecVal(0x9B,8)),
        *[out[1+3*j]==a.m[1+3*j] for j in range(12)]),
        'conditional 9B chooses NEXT physical header at ANY F marker; arbitrary M22, numeric lane held')
    check=next(v for v in rows if v['word']==2889672)
    assert check['ip']==0x9C and check['numericOwner']==['unclassified:aux1']
    low,high=BitVec('ready_header_low',4),BitVec('ready_header_high',4)
    a,p,b,out=execute(check,0x9C,{31:low,34:high})
    accepted=Or(And(low==15,UGE(high,1)),And(low!=15,UGE(high,7)))
    w['prove'](p,And(w['ip'](b)==If(accepted,BitVecVal(0x9E,8),BitVecVal(0x9D,8)),
        *[out[1+3*j]==a.m[1+3*j] for j in range(12)]),
        'conditional 9C accepts lowF/high>=1 or nonF/high>=7; all256 control bytes, numeric lane held')
    print('PASS LOCAL ROM CAUSE: pending14 at W is not accepted; old1F at aux1 '
        'is accepted. 9B follows the encountered F marker, not an outstanding '
        'request identity. Observed other controls/pins only; NOT native aux0 constructor/K1/K2.',flush=True)


if __name__=='__main__':run()
