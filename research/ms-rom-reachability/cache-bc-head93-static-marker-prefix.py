#!/usr/bin/env python3
"""CONDITIONAL static marker compatibility with BOTH earlier E5 and later A2.

Do not infer a native Ms write from the isolated A2 table. A persistent F in
the same numeric field also changes E5 earlier in the REAL prefix. Replay
the original E4/DE/D6/E5/E6/ED/EE/twoAD/A2/A3/CC/BB/BC words, tracking
the actual15-carrier calendar and every return, with a consistent marker
predicate at each carrier visit. The initial working/control packet is a
read-only native E4 observation; all ring/serial hypotheses stay symbolic.
No hypothesis is loaded into a calculator. Constructor, marker survival
through other chips, later E7/inverse/control safety remain unproved.
"""
from pathlib import Path
import json
import runpy
import subprocess

from z3 import And, sat

root = Path(__file__).resolve().parent
replay = runpy.run_path(str(root/'cache-bc-head93-native-replay.py'))
m, r, w, q, eq = (replay[n] for n in ('m','r','w','q','eq'))
A, B = m['A'], m['B']


def check(native, marker):
    entry = next(e for e in native['records'] if e['word'] == 1228)
    assert entry['ip'] == 0xE4
    calendar = native['report']['carrierCycle']
    initial = replay['observed'](entry['before'], 'static_marker_working_'+marker.replace(':','_'))
    initial.m = q['State']('static_marker_ring_'+marker.replace(':','_')).m
    b = initial; p = w['base'](initial,0xE4); word = entry['word']
    marked = {marker,'unclassified:aux0'}
    visits = []; cache = None; cache_owner = None

    def execute(code):
        nonlocal b,word,cache,cache_owner
        owner = calendar[word%15]
        p.add(b.m[22] == 15 if owner in marked else b.m[22] != 15)
        assert p.check() == sat
        w['prove'](p,w['ip'](b) == code,'static marker true nextIP',False)
        if code == 0xEE:
            cache = b.m[1:36:3]; cache_owner = owner
        if code == 0xA3:
            w['prove'](p,m['m']['match'](b,11376),'static marker actual A3class11376',False)
        before = b; output = []
        b = w['ex'](b,code,*q['arbitrary_keys'](f'static_{marker}_{word}_keys'),
            serial_inputs=q['State'](f'static_{marker}_{word}_serial').m,emitted_outputs=output)
        if code == 0xA3:
            w['prove'](p,And(eq(output[28:35:3],A(before)[9:]),
                *[output[j] == before.m[j] for j in range(42) if j not in (28,31,34)]),
                'static marker preliminary upper3 side write',False)
        elif code == 0xBC:
            w['prove'](p,And(w['ip'](b) == 0x93,
                eq(output[1:42:3],[*A(initial),q['N4'](3),q['N4'](10)]),
                *[output[j] == before.m[j] for j in range(42) if j%3!=1]),
                'static marker full BC14 original source/true93',False)
        else:
            w['prove'](p,eq(output,before.m),'static marker prefix ring neutral',False)
        visits.append({'word':word,'ip':f'{code:02X}','owner':owner});word += 1

    for code in (0xE4,0xDE,0xD6): execute(code)
    while True:
        stop = calendar[word%15] in marked
        execute(0xE5)
        if stop: break
    for code in (0xE6,0xED,0xEE,0xAD,0xAD): execute(code)
    while True:
        stop = calendar[word%15] in marked
        execute(0xA2)
        if stop: break
    assert cache is not None
    w['prove'](p,And(eq(B(b),A(initial)),eq(A(b)[:10],cache[:10])),
        'static marker source intact and cache lower10 from actual earlier EE',False)
    for code in (0xA3,0xCC,0xBB,0xBC): execute(code)
    last = lambda code: next(v for v in reversed(visits) if v['ip'] == code)
    row = {'staticAdditionalMarker':marker,'baselineAux0MarkerRetained':True,
        'E5waits':sum(v['ip']=='E5' for v in visits),'E5last':last('E5'),
        'secondEEcacheOwner':cache_owner,
        'A2waits':sum(v['ip']=='A2' for v in visits),'A2last':last('A2'),
        'preliminaryA3':last('A3'),'BCtarget':last('BC'),
        'words':len(visits),'nativeMarkerConstructed':False,'conditionalOnly':True}
    print(json.dumps(row,ensure_ascii=False),flush=True)
    return row


def run():
    r['inlet']['immutable_reference']()
    native = json.loads(subprocess.check_output(['node',
        str(root/'cache-bc-head93-native-carriers.cjs'),'--proof-input'],text=True))
    calendar = native['report']['carrierCycle']
    # The10 single additional marker carriers seen BEFORE the native aux0
    # E5 exit; plus the original aux0-only baseline. Finite local domain,
    # not a keyboard sweep or global reachability exclusion.
    rows = [check(native,owner) for owner in calendar[1:12]]
    useful = [v for v in rows if v['BCtarget']['owner'].startswith('Ms:')]
    assert len(useful)==1
    candidate = useful[0]
    assert candidate['staticAdditionalMarker']=='Ms:Q'
    assert candidate['E5waits']==6 and candidate['A2waits']==10
    assert candidate['secondEEcacheOwner']=='Ms:P9'
    assert candidate['preliminaryA3']['owner']=='Ms:P7'
    assert candidate['BCtarget']['owner']=='Ms:P10'
    assert candidate['BCtarget']['word']==1255
    r['inlet']['immutable_reference']()
    print('PASS11 CONDITIONAL static marker prefix cases, original E5 andA2 both included. '
          'Single Q marker is the only Ms-target candidate in this local domain: '
          'E5 exitsQ, A2 skips existingaux0 and returnsQ, BC writesMsP10; '
          'EE cachesMsP9 and preliminaryA3 damagesMsP7 upper3.')
    print('LIMIT not native marker/header/phase coexistence, general firstF uniqueness, '
          'marker survival through other chips, inverse or safe exit; no injected calculator state.')


if __name__=='__main__': run()
