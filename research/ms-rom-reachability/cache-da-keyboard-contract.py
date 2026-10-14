#!/usr/bin/env python3
"""Exact keyboard DA source replays and native ALL5-chip baselines.

No detached flag assignments and no native state setters. This confirms
entry with marker-derived FF/FF/90, NOT arbitrary program-cache transport.
The generic raw6 local packet remains conditional on source availability.
"""
import json
from pathlib import Path
import runpy
import subprocess

from z3 import simplify

root=Path(__file__).resolve().parent
engine=runpy.run_path(str(root/'cache-stack-lift-ring.py'))
w,q=engine['w'],engine['q']
primary=runpy.run_path(str(root/'cache-writer-contract.py'))
cases=json.loads(subprocess.check_output(
    ['node',str(root/'cache-da-keyboard.cjs'),'--proof-input'],text=True))


def source_replays():
    for case in cases:
        es=case['sourceEvents'];a=primary['constant'](es[0])
        assert es[0]['ip']==0xD6
        source=es[0]['m'][0:36:3]
        assert source==[int(v,16) for v in reversed(case['report']['pointer'])]
        for event,following in zip(es,es[1:]):
            assert primary['number'](primary['address'](a))==event['ip']
            a=primary['ex'](a,event['ip'],event['keyX'],event['keyY'],
                serial_inputs=[primary['q']['N4'](v) for v in following['m']])
            for field in ('r','st','m'):
                assert [primary['number'](v) for v in getattr(a,field)]==following[field]
            for field in ('s','s1','l','t','carry'):
                assert primary['number'](getattr(a,field))==following[field]
        r=case['report']
        if r['markerKind']=='logical':
            assert r['nativeR33']==15 and r['nativeR27']==9 and r['nativeHeader']==4
            assert r['raw3At73']==[15,15,15,15,0,9]
            assert primary['number'](primary['address'](a))==0x76
            assert r['programChanges']==[]
        else:
            assert r['nativeR33']==0 and not r['nativeDA']
            assert r['programChanges']==[{'address':37,'before':0,'after':247}]
        print('PASS native D6→normalizer→DD→73 source ALL primary fields:',
              r['markerKind'],'phase',r['phaseOffset'],len(es)-1,'macros;',
              'no flag hypothesis, no program-cache export.',flush=True)


def whole_ring_baselines():
    for case in cases:
        entries=case['prefix'];state,tags,j=engine['make'](entries[0])
        for current,following in zip(entries,entries[1:]):
            assert engine['boundary_ip'](state['ik1302'])==current['ip']
            pins={name:(current['state'][name]['keyX'],current['state'][name]['keyY'])
                  for name in engine['models']}
            j,_=engine['step'](state,tags,j,pins)
            for name in engine['names']:
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
        r=case['report']
        print('PASS native ALL5 chips/R/ST/M/scalars/phase/wires:',
              r['markerKind'],'phase',r['phaseOffset'],'64 consecutive transitions.',flush=True)


def previous_A_loss_at_D6():
    a=primary['q']['State']('da_D6_oldA');other=a.copy()
    replacement=primary['q']['State']('da_D6_otherA')
    for k in range(0,36,3):other.r[k]=replacement.r[k]
    p=primary['base'](a,0xD6)
    serial=primary['q']['State']('da_D6_commonserial').m
    signals=primary['keys']('da_D6_commonkeys');outputs=[]
    result=[]
    for entry in (a,other):
        out=[];result.append(primary['ex'](entry,0xD6,*signals,
                        serial_inputs=serial,emitted_outputs=out));outputs.append(out)
    left,right=result
    primary['prove'](p,q['And'](
        *[x==y for field in ('r','st','m')
          for x,y in zip(getattr(left,field),getattr(right,field))],
        *[getattr(left,field)==getattr(right,field) for field in ('s','s1','l','t','carry')],
        *[x==y for x,y in zip(*outputs)],
        *[outputs[0][k]==a.m[k] for k in range(42)]),
        'D6 forgets ALL12 previousA tetras in ALL primary fields and outgoing ring; no new copy')
    print('SCOPE: two states share every other field and ring input. Earlier copies '
          'outsideA are not excluded. This is a local transport barrier, not K2 impossibility.',flush=True)


if __name__=='__main__':
    source_replays()
    whole_ring_baselines()
    # This checks arbitrary raw data only as a LOCAL input contract. The
    # actual keyboard source above supplies fixed marker-derived data.
    packet=runpy.run_path(str(root/'cache-da-data-contract.py'))
    packet['carry_and_raw_packet']()
    previous_A_loss_at_D6()
    print('PASS native DA control metadata is now constructed by keys. '
          'Missing: reader-data transport, arbitrary-code native export and Ms copy.',flush=True)
