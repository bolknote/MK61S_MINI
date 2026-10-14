#!/usr/bin/env python3
"""Exact local dataflow proof for the native F Сx comma bridge.

Six raw payload tetras and ST34 are unconstrained. Other entry fields are
from a keyboard-only native trace. Serial input and physical key signals
are arbitrary on each tick. This proves a conditional local ROM contract,
not keyboard reachability of any invented ST34 value or a partial K2.
"""
import json
from pathlib import Path
import subprocess

from z3 import And, BitVec, Or, Solver, ZeroExt, sat, unsat, simplify
from ik1302_symbolic import State, N4, N1, execute_command, arbitrary_keys, base_solver

root=Path(__file__).resolve().parent
positions=(0,3,9,12,18,21)
route=(0x8C,0x91,0x92,0x93,0x94,0x95,0x98,0x9A,
       0x93,0x94,0x95,0x98,0x9A,0x8D,0x4F,0xAF,0xAE,0xDC)
lanes=(0,0,1,2,2,2,2,2,1,1,1,1,0,0,0,0,0,0)
address=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)


def concrete(e):
    a=State('native_bridge')
    for field in ('r','st','m'):
        setattr(a,field,[N4(v) for v in e[field]])
    for field in ('s','s1'):setattr(a,field,N4(e[field]))
    for field in ('l','t','carry'):setattr(a,field,N1(e[field]))
    return a


def prove(p,claim,label):
    assert p.check()==sat,('empty premises',label)
    p.push();p.add(~claim)
    assert p.check()==unsat,label
    p.pop();print('PASS:',label,flush=True)


def main():
    native=json.loads(subprocess.check_output(
        ['node',str(root/'check_partial_k2_cache_bridge.cjs'),'--proof-input'],text=True))
    events=native['events']
    assert tuple(e['ip'] for e in events)==route
    # Independently validate the symbolic semantics against the passive native
    # stream before generalizing the data and the control field.
    a=concrete(events[0])
    for i,ip in enumerate(route[:-1]):
        e,nxt=events[i:i+2]
        a=execute_command(a,ip,e['keyX'],e['keyY'],
                          serial_inputs=[N4(v) for v in nxt['m']])
        for field in ('r','st','m'):
            assert [simplify(v).as_long() for v in getattr(a,field)]==nxt[field],(ip,field)
        for field in ('s','s1','l','t','carry'):
            assert simplify(getattr(a,field)).as_long()==nxt[field],(ip,field)
    print('PASS: exact concrete replay matches all observed primary fields',flush=True)

    a=concrete(events[0])
    payload=[BitVec(f'bridge_payload_{i}',4) for i in range(6)]
    source=BitVec('bridge_original_ST34',4)
    for pos,value in zip(positions,payload):a.r[pos]=value
    a.st[34]=source
    p=Solver()
    for i,ip in enumerate(route):
        prove(p,And(address(a)==ip,*[a.r[pos+lanes[i]]==value
              for pos,value in zip(positions,payload)]),
              f'{ip:02X}: forced entry with all six raw tetras in lane {"ABC"[lanes[i]]}')
        if ip==0x8D:
            prove(p,a.r[34]==source,'8D receives old numeric ST34 unchanged in R34')
        if i==len(route)-1:break
        emitted=[]
        b=execute_command(a,ip,*arbitrary_keys(f'bridge_keys_{i}'),emitted_outputs=emitted)
        prove(p,And(*[emitted[j]==a.m[j] for j in range(42)]),
              f'{ip:02X}: no primary ring output is replaced')
        a=b
    prove(p,Or(a.r[34]==source,a.r[34]==1,a.r[34]==15),
          'AF may adjust the old header to 1/F, while holding all six raw tetras')
    b=execute_command(a,0xDC,*arbitrary_keys('bridge_DC_keys'))
    prove(p,(address(b)==0xDE)==Or(*[a.r[34]==v for v in range(1,9)]),
          'DC chooses DE exactly for its adjusted header in 1..8')
    p.add(source==15)
    prove(p,Or(a.r[34]==1,a.r[34]==15),
          'baseline ST34=F allows only adjusted header 1 or F, never writer header 4')
    c=execute_command(b,0xDE,*arbitrary_keys('bridge_DE_keys'))
    p.add(a.r[34]==1)
    prove(p,And(address(b)==0xDE,address(c)==0xD1),
          'baseline accepted adjusted header dispatches D1, not D4')
    # The native cancellation is data-preserving, but its flag source is B3,
    # not 78. Keep this distinction explicit in the regression proof.
    for ip in (0xB3,0x78,0x7F):
        a=State(f'cancel_{ip}')
        b=execute_command(a,ip,*arbitrary_keys(f'cancel_keys_{ip}'))
        prove(base_solver(a,ip),And(*[b.r[pos]==a.r[pos] for pos in positions],
          b.r[23]==(N4(0) if ip==0xB3 else a.r[23])),
          f'{ip:02X}: payload held; R23 '+('cleared' if ip==0xB3 else 'held'))
    print('LIMIT: native old ST34 is F. Native DE/D1 is possible for selected data; '
          'no native D4 or persistent Ms cache write is claimed.')


if __name__=='__main__':main()
