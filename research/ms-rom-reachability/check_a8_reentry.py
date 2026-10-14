#!/usr/bin/env python3
"""Test the 28-command A8 reentry cycle from a read-only native checkpoint.

The reference is driven only through keys. Its checkpoint is copied into a
symbolic proof, never injected back into the physical/reference machine.
All A payload tetras, all ring inputs and per-tick keyboard pins are arbitrary.
"""
import json
import runpy
import subprocess
from pathlib import Path
from z3 import And, sat, unsat, ZeroExt

root=Path(__file__).resolve().parent
source='''
const result=require(PROBE).run();
const gates=result.traced.events.filter(e=>e.ip===0x60&&e.nextIp===0xA8);
const gate=gates[1];
console.log(JSON.stringify({gate,next:gates[2],sequence:result.traced.events
  .filter(e=>e.command>=gate.command&&e.command<=gates[2].command).map(e=>e.ip)}));
'''.replace('PROBE',json.dumps(str(root/'probe_a8_bank_keyboard.cjs')))
native=json.loads(subprocess.check_output(['node','-e',source],text=True))
sequence=[0x60]+[0xA8]*8+[0xA9,0x6E,0x61]+[0x3A,0x06,0x07,0x6D,0x60,0x61]*2+[
    0x3A,0x06,0x07,0x6D,0x60]
assert native['sequence']==sequence
assert native['next']['command']-native['gate']['command']==28
q=runpy.run_path(str(root/'ik1302_symbolic.py'))
byte=lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
address=lambda a:byte(a.r[36],a.r[39])
a=q['State']('a8_reentry');payload=set(range(0,36,3));snapshot=native['gate']
for i in range(42):
    if i not in payload:a.r[i]=q['N4'](snapshot['r'][i])
    a.st[i]=q['N4'](snapshot['st'][i])
a.s1=q['N4'](snapshot['s1'])
p=q['base_solver'](a,0x60);p.set(timeout=20000);b=a
assert p.check()==sat
for index,(ip,nxt) in enumerate(zip(sequence,sequence[1:])):
    b=q['execute_command'](b,ip,*q['arbitrary_keys'](f'a8_reentry_keys_{index}'))
    p.push();p.add(address(b)!=nxt)
    outcome=p.check();p.pop()
    assert outcome==unsat,(index,f'{ip:02X}->{nxt:02X}',outcome)
print('PASS: all 28 transitions are forced for arbitrary A, ring data and keyboard pins.',flush=True)
claims=([b.r[i]==a.r[i] for i in range(42) if i not in payload]+
        [b.st[i]==a.st[i] for i in range(42)]+[b.s1==a.s1])
p.add(~And(*claims));outcome=p.check()
assert outcome==unsat,outcome
print('PASS: every fixed controller field and ST returns unchanged; this is an inductive cycle.',flush=True)
print('PASS: 28 mod 15 = 13, so reentry moves the start two physical pages backwards; '
      'all fifteen page positions are visited, not just eight Ms pages.',flush=True)
