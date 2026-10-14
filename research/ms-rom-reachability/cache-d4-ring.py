#!/usr/bin/env python3
"""Exact five-chip CONDITIONAL D4 packet/AF escape with fixed key release.

The calculator used for the baseline receives only ordinary keys. The
counterfactual changes R34=4 and B8=D/E/F ONLY in detached symbolic states;
it never injects those fields into the reference emulator. Raw6 and the
original six program tetras vary together. This is NOT native partial K2.
Reuse the previously full-state-validated five-chip engine and original ROMs.
"""
import json
from pathlib import Path
import runpy
import subprocess
import sys

from z3 import BitVec,simplify

root=Path(__file__).resolve().parent
engine=runpy.run_path(str(root/'cache-stack-lift-ring.py'))
w,q=engine['w'],engine['q']
models,names,slots=(engine[n] for n in ('models','names','slots'))
make,step,ring,boundary_ip=(engine[n] for n in ('make','step','ring','boundary_ip'))
native=json.loads(subprocess.check_output(
    ['node',str(root/'cache-d4-native-topology.cjs'),'--proof-input'],text=True))
raw=(0,3,9,12,18,21)
program=(14,17,20,23,26,29)


def validate_baseline():
    entries=native['prefix'];state,tags,j=make(entries[0])
    for current,following in zip(entries,entries[1:]):
        assert boundary_ip(state['ik1302'])==current['ip']
        pins={name:(current['state'][name]['keyX'],current['state'][name]['keyY'])
              for name in models}
        j,_=step(state,tags,j,pins)
        for name in names:
            target=following['state'][name]
            for field in ('input','output'):
                assert simplify(state['_wire'][name][field]).as_long()==target[field],(name,field)
            if name.startswith('ir'):
                assert [simplify(v).as_long() for v in state[name]]==target['m'],name
                assert j==target['tick']
            else:
                for field in ('r','m','st'):
                    assert [simplify(v).as_long() for v in getattr(state[name],field)]==target[field],(name,field)
                for field in ('s','s1','l','t','carry'):
                    assert simplify(getattr(state[name],field)).as_long()==target[field],(name,field)
    print('PASS D4 engine baseline: ALL5 chips/R/ST/M/scalars/phase/wires '
          'at64 consecutive native macro boundaries.',flush=True)


def conditional(sign):
    entry=native['prefix'][0];state,tags,j=make(entry)
    payload=[BitVec(f'd4_ring_sign{sign:X}_raw{k}',4) for k in range(6)]
    primary=state['ik1302']
    assert simplify(primary.r[34]).as_long()==15
    assert simplify(primary.r[25]).as_long()==0
    # Hypotheses ONLY: neither field exists in the observed native inlet.
    primary.r[34]=q['N4'](4);primary.r[25]=q['N4'](sign)
    for k,value in zip(raw,payload):primary.r[k]=value
    for name in names:
        memory=state[name] if name.startswith('ir') else state[name].m
        for k,(slot,nibble) in enumerate(tags[name]):
            if slot=='Y' and nibble in program:
                index=program.index(nibble)
                assert simplify(memory[k]).as_long()==entry['state']['ik1302']['r'][raw[index]]
                memory[k]=payload[index]
    before=ring(state,tags)
    p=q['base_solver'](primary,0xDC)
    pins={name:(entry['state'][name]['keyX'],entry['state'][name]['keyY'])
          for name in models}
    release_at=5*560
    finish_at=7*560  # complete last release frame, then one extra idle frame
    assert 4*560<=entry['command']<release_at
    sequence=[];writes=[];first_idle=None
    for count in range(finish_at-entry['command']):
        released=entry['command']+count>=release_at
        if released:pins['ik1302']=(0,0)
        code=boundary_ip(state['ik1302'],p);sequence.append(code)
        if code==0x35 and released and first_idle is None:first_idle=count
        original=state['ik1302']
        dest=tags['ik1302'][0][0]
        j,emitted=step(state,tags,j,pins,p)
        changed=q['And'](*[emitted['ik1302'][k]==original.m[k] for k in range(42)])
        p.push();p.add(~changed);answer=p.check();p.pop()
        assert answer in (q['sat'],q['unsat'])
        if answer==q['sat']:
            writes.append((count,code,dest))
            print('CONDITIONAL primary write:',f'B8={sign:X}',count,f'{code:02X}',dest,flush=True)
    assert first_idle is not None
    w['prove'](p,w['ip'](state['ik1302'])==0x35,
               f'B8={sign:X}: fixed complete release plus one full idle frame ends at35')
    after=ring(state,tags)
    assert [(code,dest) for _,code,dest in writes]==[(0xD4,'U'),(0xD4,'W')]
    w['prove'](p,w['eq']([after['U'][k+3] for k in raw],payload),
               f'B8={sign:X}: exact raw6 physically retained in ORDINARY P0 at idle35')
    w['prove'](p,w['eq']([after['W'][k] for k in raw],payload),
               f'B8={sign:X}: aligned exact raw6 physically retained in ORDINARY P2 at idle35')
    w['prove'](p,w['eq']([v for slot in slots for k,v in enumerate(after[slot]) if k%3==2],
                       [v for slot in slots for k,v in enumerate(before[slot]) if k%3==2]),
               f'B8={sign:X}: ALL105 original program bytes held in full five-chip model')
    hidden=native['mapping']['hidden']
    w['prove'](p,w['eq']([after[slot][k] for slot,positions in hidden.items() for k in positions],
                       [before[slot][k] for slot,positions in hidden.items() for k in positions]),
               f'B8={sign:X}: ALL56 Ms bytes held, so this is NOT a direct Ms write')
    w['prove'](p,w['eq']([after[slot][k] for slot in slots if slot not in ('U','W')
                        for k in range(0,36,3)],
                       [before[slot][k] for slot in slots if slot not in ('U','W')
                        for k in range(0,36,3)]),
               f'B8={sign:X}: other13 ordinary registers held')
    print('CONDITIONAL full-ring completion:',f'B8={sign:X}',len(sequence),
          'FIXED macros; first idle after',first_idle,'; release at',release_at,
          '; finish at',finish_at,'; all256^3 raw-code triples.',flush=True)
    print('LIMIT: two DETACHED metadata hypotheses, NO native keyboard entry, '
          'NO Ms copy/reverse transfer; primary idle alone is not a workload-retention ABI.',flush=True)


if __name__=='__main__':
    if '--baseline-only' in sys.argv:validate_baseline()
    elif '--signF-only' in sys.argv:conditional(15)
    else:
        validate_baseline()
        for sign in (13,14,15):conditional(sign)
