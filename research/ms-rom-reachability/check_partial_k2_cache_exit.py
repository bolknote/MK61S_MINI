#!/usr/bin/env python3
"""Local dataflow barrier for SELECTED exits of the raw program-byte reader.

The individual lemmas allow arbitrary fields, keys and serial ring inputs.
Their observed composition covers the five recorded native continuations,
NOT every future keyboard path, and NOT every possible partial-K2 protocol.
"""
import json
from pathlib import Path
import runpy
import subprocess

from z3 import And, BitVec, sat, unsat

root=Path(__file__).resolve().parent
q=runpy.run_path(str(root/'ik1302_symbolic.py'))
State,execute,base,keys=(q[n] for n in
    ('State','execute_command','base_solver','arbitrary_keys'))
positions=(0,3,9,12,18,21)


def prove(p,claim,label):
    assert p.check()==sat,('empty premises',label)
    p.push();p.add(~claim)
    assert p.check()==unsat,label
    p.pop();print('PASS:',label,flush=True)


def dataflow():
    native=json.loads(subprocess.check_output(
        ['node',str(root/'check_partial_k2_cache_exit.cjs'),'--proof-input'],text=True))
    assert native['initial']['r'][36]+16*native['initial']['r'][39]==0x35
    assert len(native['reports'])==5
    for ip in sorted(native['preEEIps']):
        a=State(f'cache_exit_{ip:02x}');c=a.copy()
        for pos in positions:c.r[pos]=BitVec(f'cache_alternative_{ip:02x}_{pos}',4)
        signals=keys(f'cache_exit_keys_{ip:02x}');serial=State(f'cache_serial_{ip:02x}').m
        outputs=[];other_outputs=[]
        b=execute(a,ip,*signals,serial_inputs=serial,emitted_outputs=outputs)
        d=execute(c,ip,*signals,serial_inputs=serial,emitted_outputs=other_outputs)
        claims=[b.r[pos]==a.r[pos] for pos in positions]
        claims += [b.r[i]==d.r[i] for i in range(42) if i not in positions]
        claims += [x==y for x,y in zip(b.st,d.st)]
        claims += [getattr(b,n)==getattr(d,n) for n in ('s','s1','l','t','carry')]
        claims += [outputs[i]==a.m[i] for i in range(42)]
        prove(base(a,ip),And(*claims),
          f'{ip:02X}: all six raw payload tetras held; no primary ring write; '
          'no dependence/backup outside those six R slots')
    a=State('cache_exit_EE');c=a.copy()
    for pos in positions:c.r[pos]=BitVec(f'cache_EE_alternative_{pos}',4)
    signals=keys('cache_exit_EE_keys');serial=State('cache_exit_EE_serial').m
    outputs=[]
    b=execute(a,0xEE,*signals,serial_inputs=serial,emitted_outputs=outputs)
    d=execute(c,0xEE,*signals,serial_inputs=serial)
    prove(base(a,0xEE),And(
      *[b.r[3*i]==a.m[1+3*i] for i in range(12)],
      *[x==y for field in ('r','m','st')
        for x,y in zip(getattr(b,field),getattr(d,field))],
      *[getattr(b,n)==getattr(d,n) for n in ('s','s1','l','t','carry')],
      *[outputs[i]==a.m[i] for i in range(42)]),
      'EE replaces the entire A word by M2; varying the six old cache tetras '
      'cannot change any resulting primary field on a common incoming stream')
    print('LIMIT: original bytes remain in program memory. These selected exits '
          'do not export the cache; this is no global partial-K2 impossibility proof.',flush=True)


def impossible_paths():
    checker=runpy.run_path(str(root/'verify_c8_recovery_candidate.py'),
                          init_globals={'transport':{'q':q}})
    sequences=['35 45 8B 48 B1','35 B5 83 45 8B 48 B1',
               '35 B5 B7 45 8B 48 B1','7A 7C 75']
    for text in sequences:
        result=checker['verify_sequence']([int(n,16) for n in text.split()])
        assert result['result']==unsat,text
        print('PASS: impossible ROM suffix for arbitrary initial primary state, '
              'physical per-tick key rows and arbitrary incoming ring:',text,flush=True)


if __name__=='__main__':
    dataflow()
    impossible_paths()
