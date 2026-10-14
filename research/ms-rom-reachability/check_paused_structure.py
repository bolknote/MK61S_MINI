#!/usr/bin/env python3
"""Keyboard scanner closure and exact continuation from a native checkpoint.

All negative proofs allow arbitrary per-tick keys and fresh serial input.
Native checkpoints are read from keyboard-only preparation, never injected
back into the emulator. A hypothetical selector change is explicitly marked.
"""
import json
import runpy
import subprocess
from pathlib import Path

from z3 import And, Or, UGE, ZeroExt, sat, unsat

root = Path(__file__).resolve().parent
q = runpy.run_path(str(root / 'ik1302_symbolic.py'))
State, execute, base, keys = (q[n] for n in
    ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))


def address(a):
    return ZeroExt(4, a.r[36]) | (ZeroExt(4, a.r[39]) << 4)


def constrain_snapshot(p, a, data, skip_r=()):
    for name in ('r','m','st'):
        p.add(*[value == n for i,(value,n) in
            enumerate(zip(getattr(a,name), data[name]))
            if name != 'r' or i not in skip_r])
    p.add(*[getattr(a,name) == data[name]
            for name in ('s','s1','l','t','carry')])


facts = 0


def prove(ip, label, claim):
    global facts
    a = State(f'paused_fact_{facts}')
    b = execute(a,ip,*keys(f'paused_fact_keys_{facts}'))
    p = base(a,ip)
    assert p.check() == sat
    p.add(~claim(a,b))
    assert p.check() == unsat, label
    facts += 1
    print('PASS:',label,flush=True)


# This finite island has no other outgoing edge, independently of the stack,
# ring contents, scan count, or held/released/changing keyboard signals.
scanner = {0x35:{0x35,0x45,0xB5,0xC5}, 0xC5:{0x8A}, 0x8A:{0x65},
           0x65:{0x7B}, 0x7B:{0xB7}, 0xB7:{0x45}, 0xB5:{0x83,0xB7},
           0x83:{0x45}, 0x45:{0x8B}}
for ip, exits in scanner.items():
    prove(ip,f'{ip:02X}: scanner closure and preservation of R2/R5/counter/marker/selector',
          lambda a,b,exits=exits: And(Or(*[address(b)==v for v in exits]),
              *[a.r[i]==b.r[i] for i in (2,5,25,26,31,34,38)]))
prove(0x8B,'8B always enters 48 and swaps R2/R5 exactly',
      lambda a,b: And(address(b)==0x48,b.r[2]==a.r[5],b.r[5]==a.r[2],
          *[a.r[i]==b.r[i] for i in (25,26,31,34,38)]))

native = json.loads(subprocess.check_output(
    ['node',str(root/'probe_paused_paths.cjs'),'F','ВП'],text=True))
initial = native['initial']
assert initial['r'][2] == 8 and initial['r'][5] == 0
a = State('paused_scanner_native')
p = base(a,0x35)
constrain_snapshot(p,a,initial)
b = a
scan_path = [0x35,0xC5,0x8A,0x65,0x7B,0xB7,0x45,0x8B,0x48]
for i,(ip,nxt) in enumerate(zip(scan_path,scan_path[1:])):
    b = execute(b,ip,*keys(f'paused_scanner_native_keys_{i}'))
    p.add(address(b)==nxt)
assert p.check() == sat
p.add(UGE(b.r[2],5))
assert p.check() == unsat
print('PASS: full native 35 checkpoint has a nonempty scanner path but cannot '
      'carry high R2 through 8B. The nine-node closure extends this result '
      'to all scanner branches and any number of 35 waits.',flush=True)

prove(0x7C,'7C unconditionally assigns selector 8',lambda a,b:b.r[38]==8)
prove(0x77,'77 sets R2=F and enters 6D without changing selector/marker/counter',
      lambda a,b: And(address(b)==0x6D,b.r[2]==15,
          *[a.r[i]==b.r[i] for i in (25,26,31,34,38)]))

checkpoint = next(c['snapshot'] for c in native['checkpoints'] if c['fields']['ip']==0x77)
aligned = next(c for c in native['checkpoints'] if c['fields']['ip']==0x60)
assert [aligned['snapshot']['r'][i] for i in (2,25,26,31,32,34,38)] == [15,7,1,7,0,13,8]

# Prove the whole known-state continuation, not only existence of the path.
# Future physical-ring values are not fixed; UNSAT therefore also excludes
# changing keys or another ring stream as a way to divert this short suffix.
prefix = [0x77,0x6D,0x6F,0x62,0x6E,0x61]
cycle = [0x3A,0x06,0x07,0x6D,0x60,0x61]
sequence = prefix + cycle*2 + [0x3A,0x06,0x07,0x6D,0x60,0x08]
a = State('paused_77_native')
p = base(a,0x77)
constrain_snapshot(p,a,checkpoint)
b = a
for i,(ip,nxt) in enumerate(zip(sequence,sequence[1:])):
    b = execute(b,ip,*keys(f'paused_77_native_keys_{i}'))
    p.push()
    p.add(address(b)!=nxt)
    assert p.check() == unsat, ('native forced continuation',i,ip,nxt)
    p.pop()
assert p.check() == sat
print('PASS: all '+str(len(sequence)-1)+' transitions from the full native 77 '
      'checkpoint are forced even with arbitrary future keys/ring. The three '
      'increments restore D7 and enter 60->08, never 18 or C8.',flush=True)

def addresses(text):
    return [int(n,16) for n in text.split()]


# Change only a symbolic assumption, NOT the physical emulator checkpoint.
# This is a diagnostic positive control, not a way to execute the primitive.
read_prefix = sequence[:-1] + addresses('18 1B 1D 2E 01 02 02 02 03 04 BA CB DD')
long = read_prefix + addresses('D6 2F 21 22 36 27 38 06 07 6D 60') + \
       addresses('61 3A 06 07 6D 60')*9 + [0xC8]


def build_path(sequence,label,data=None,selector=None,released=False):
    a = State(label)
    p = base(a,sequence[0])
    if data is not None:
        constrain_snapshot(p,a,data,skip_r=(38,) if selector is not None else ())
    if selector is not None:
        p.add(a.r[38]==selector)
    b, states = a, [a]
    for i,(ip,nxt) in enumerate(zip(sequence,sequence[1:])):
        b = execute(b,ip,*((0,0) if released else keys(f'{label}_keys_{i}')))
        p.add(address(b)==nxt)
        states.append(b)
    return a,b,p,states


a,b,p,_ = build_path(read_prefix,'paused_exponent_provenance')
assert p.check() == sat
p.add(b.r[0]!=a.r[27])
assert p.check() == unsat
print('PASS: on the selected 77/three-increment/read prefix, DD receives '
      'R0=the initial R27, for arbitrary chip data, future keys, and ring. '
      'The digit is not freely supplied by the later serial read.',flush=True)

_,b,p,_ = build_path(read_prefix,'paused_zero_hypothesis',checkpoint,9,True)
assert p.check() == sat
p.add(b.r[0]!=15)
assert p.check() == unsat
_,_,p,_ = build_path(long,'paused_zero_long_hypothesis',checkpoint,9,True)
assert p.check() == unsat
print('PASS: with the original native checkpoint, hypothetical selector 9 '
      'alone still cannot complete this path: DD gets R0=F and writes 0, '
      'not the required 4.',flush=True)

exponent_native = json.loads(subprocess.check_output(['node',
    str(root/'probe_paused_paths.cjs'),'Сx','1','ВП','1','3','F','ВП'],text=True))
exponent_checkpoint = next(c['snapshot'] for c in exponent_native['checkpoints']
                          if c['fields']['ip']==0x77)
assert exponent_checkpoint['r'][27] == 3
a,b,p,states = build_path(long,'paused_exp13_long_hypothesis',
                         exponent_checkpoint,9,True)
assert p.check() == sat
dd = states[long.index(0xDD)]
p.add(~And(dd.r[0]==3,b.r[38]==4,b.r[2]==15))
assert p.check() == unsat
print('PASS: after actual keyboard entry of 1E13, the '+str(len(long)-1)+
      '-transition C8 path is SAT with all native IK1302 fields fixed EXCEPT '
      'the hypothetical selector 9. Keys are released; future ring inputs '
      'remain arbitrary. No physical selector-setting mechanism is supplied.',flush=True)
print(f'PASS: {facts} universal facts and exact native-checkpoint checks.',flush=True)
