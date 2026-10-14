#!/usr/bin/env python3
"""DA→D4→76 CONDITIONAL physical continuation, not a keyboard construction.

Native controls and ALL5-chip baseline are untouched. Two detached control
fields at73 (R33=F, R27=2) and six synthetic code tetras are hypotheses.
Original program tetras vary jointly with those six codes, but that does NOT
construct a reader→73 transport. Fixed key release; no controller feedback.
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
    ['node',str(root/'cache-da-native-topology.cjs'),'--proof-input'],text=True))
raw=(0,3,9,12,18,21)
program=(14,17,20,23,26,29)


def validate_baseline():
    for case in native:
        entries=case['prefix'];state,tags,j=make(entries[0])
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
        print('PASS DA engine native baseline:',case['report']['pointer'],
              'ALL5 chips/R/ST/M/scalars/phase/wires at64 consecutive boundaries.',flush=True)


def conditional():
    case=native[0];entry=case['prefix'][0];state,tags,j=make(entry)
    primary=state['ik1302'];assert boundary_ip(primary)==0x73
    assert [simplify(primary.r[k]).as_long() for k in (33,27)]==[0,0]
    primary.r[33]=q['N4'](15);primary.r[27]=q['N4'](2)
    payload=[BitVec(f'da_ring_raw{k}',4) for k in range(6)]
    for pos,value in zip(raw,payload):primary.r[pos]=value
    for name in names:
        memory=state[name] if name.startswith('ir') else state[name].m
        for k,(slot,nibble) in enumerate(tags[name]):
            if slot=='Y' and nibble in program:
                index=program.index(nibble)
                assert simplify(memory[k]).as_long()==(3,10,4,13,5,11)[index]
                memory[k]=payload[index]
    before=ring(state,tags);p=q['base_solver'](primary,0x73)
    pins={name:(entry['state'][name]['keyX'],entry['state'][name]['keyY'])
          for name in models}
    release_at=5*560;finish_at=7*560
    assert 4*560<=entry['command']<release_at
    writes=[];sequence=[];first_idle=None
    for count in range(finish_at-entry['command']):
        released=entry['command']+count>=release_at
        if released:pins['ik1302']=(0,0)
        code=boundary_ip(state['ik1302'],p);sequence.append(code)
        if code==0x35 and released and first_idle is None:first_idle=count
        original=state['ik1302'];dest=tags['ik1302'][0][0]
        j,emitted=step(state,tags,j,pins,p)
        unchanged=w['eq'](emitted['ik1302'],original.m)
        p.push();p.add(~unchanged);answer=p.check();p.pop()
        assert answer in (q['sat'],q['unsat'])
        if answer==q['sat']:
            writes.append((count,code,dest))
            print('CONDITIONAL DA primary write:',count,f'{code:02X}',dest,flush=True)
    assert first_idle is not None
    w['prove'](p,w['ip'](state['ik1302'])==0x35,
               'DA conditional fixed complete release plus one idle frame ends at35')
    assert sequence[:15]==[0x73,0x75,0xCA,0xDA,0xDC,0xDE,0xD4,0xDD,0xD4,
                          0x76,0xE2,0xE5,0xE6,0xED,0xEE]
    after=ring(state,tags)
    for slot,offset in (('Q',3),('P8',0)):
        w['prove'](p,w['eq']([after[slot][k+offset] for k in raw],payload),
                   'DA raw6 physically retained at idle in ordinaryP'+case['mapping']['registerPages'][slot])
    w['prove'](p,w['eq']([after[slot][k] for slot in slots for k in range(42) if k%3==2],
                       [before[slot][k] for slot in slots for k in range(42) if k%3==2]),
               'DA ALL105 original program bytes held after return76/EE and fixed release')
    hidden=case['mapping']['hidden']
    w['prove'](p,w['eq']([after[slot][k] for slot,positions in hidden.items() for k in positions],
                       [before[slot][k] for slot,positions in hidden.items() for k in positions]),
               'DA ALL56 Ms bytes held; NOT an Ms copy')
    w['prove'](p,w['eq']([after[slot][k] for slot in slots if slot not in ('Q','P8')
                        for k in range(0,36,3)],
                       [before[slot][k] for slot in slots if slot not in ('Q','P8')
                        for k in range(0,36,3)]),
               'DA other13 ordinary registers held; formerP3/P5 overwritten, NOT exchanged')
    print('CONDITIONAL DA full-ring finish:',len(sequence),'fixed macros; first idle',first_idle,
          '; all256^3 synthetic code triples; primary writes',writes,flush=True)
    print('LIMIT: detached R33=F/R27=2 and synthetic raw6 at73, NOT native keyboard '
          'entry or reader→73 transfer; destination originals overwritten, NOT exchange.',flush=True)


if __name__=='__main__':
    if '--baseline-only' in sys.argv:validate_baseline()
    elif '--conditional-only' in sys.argv:conditional()
    else:
        validate_baseline()
        conditional()
