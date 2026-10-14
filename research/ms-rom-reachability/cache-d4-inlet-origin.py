#!/usr/bin/env python3
"""Exact upstream sources of the CONDITIONAL D4 metadata and first-AF barrier.

Native snapshots are keyboard-only negative controls. Altered ST24/ST34
belong only to detached symbolic primary states, never the calculator.
The source prefix preserves every raw tetra but does not construct either
missing native field. Whole-ring conditional persistence is tested separately.
"""
import json
from pathlib import Path
import runpy
import subprocess

from z3 import And,If,UGE,ULE

root=Path(__file__).resolve().parent
w=runpy.run_path(str(root/'cache46-writer-contracts.py'))
q=w['q']
State,ex,base,keys,ip,eq,prove=(w[n] for n in
                              ('State','ex','base','keys','ip','eq','prove'))
restore=(0x8C,0x91,0x92,0x93,0x94,0x95,0x98,0x9A,
         0x93,0x94,0x95,0x98,0x9A,0x8D,0x4F)
sequence=restore+(0xAF,0xAE)


def prefix_sources():
    a=State('d4_inlet_source');p=base(a,0x8C);p.add(a.s1==10)
    b=a
    for j,code in enumerate(restore):
        prove(p,ip(b)==code,f'8C source prefix{j}',False)
        out=[];before=b
        b=ex(b,code,*keys(f'd4_inlet_source_keys{j}'),emitted_outputs=out)
        prove(p,eq(out,before.m),f'8C prefix{j} no outgoing write',False)
    prove(p,And(ip(b)==0xAF,b.r[25]==a.st[24],b.r[26]==a.st[25],
                b.r[34]==a.st[34],
                eq([b.r[k] for k in w['raw']],[a.r[k] for k in w['raw']])),
          'Before firstAF: B8=oldST24, R26=oldST25, header=oldST34; ALL raw6 held')
    p.add(a.st[25]==0)
    out=[];before=b
    b=ex(b,0xAF,*keys('d4_inlet_first_af'),emitted_outputs=out)
    prove(p,And(ip(b)==0xAE,eq(out,before.m),
                b.r[34]==If(UGE(a.r[21],13),q['N4'](1),a.st[34])),
          'FIRST AF barrier: with oldST25=0, ANY oldST34 is replaced by1 '
          'iff original third-code high tetra is D/E/F')
    before=b;out=[]
    b=ex(b,0xAE,*keys('d4_inlet_ae'),emitted_outputs=out)
    prove(p,And(ip(b)==0xDC,eq(out,before.m),b.r[25]==a.st[24],
                b.r[26]==0,b.r[34]==If(UGE(a.r[21],13),q['N4'](1),a.st[34]),
                eq([b.r[k] for k in w['raw']],[a.r[k] for k in w['raw']])),
          'DC inlet: exact two metadata sources, firstAF gate, ALL raw6 held')
    p.push();p.add(a.st[34]==4,UGE(a.st[24],13),ULE(a.r[21],12))
    prove(p,And(b.r[34]==4,UGE(b.r[25],13)),
          'CONDITIONAL upstream ST34=4/ST24 D..F reaches the D4 escape class '
          'ONLY for third-code high tetra0..C at oldST25=0')
    p.pop()
    p.push();p.add(UGE(a.r[21],13))
    for j,code in enumerate((0xDC,0xDE)):
        prove(p,ip(b)==code,f'firstAF header1 tail{j}',False)
        before=b;out=[]
        b=ex(b,code,*keys(f'd4_inlet_header1_keys{j}'),emitted_outputs=out)
        prove(p,eq(out,before.m),'header1 tail no outgoing write',False)
    prove(p,ip(b)==0xD1,
          'Third-code high tetraD..F forces DC DE D1, NOT D4, '
          'regardless of originalST34 in this prefix')
    p.pop()


def paired_metadata():
    a=State('d4_inlet_pair');other=a.copy()
    other.st[24]=q['N4'](15);other.st[34]=q['N4'](4)
    p=base(a,0x8C);p.add(a.s1==10,a.st[25]==0)
    b,c=a,other
    for j,code in enumerate(sequence):
        prove(p,And(ip(b)==code,ip(c)==code),f'metadata pair route{j}',False)
        pins=keys(f'd4_inlet_pair_keys{j}');serial=State(f'd4_inlet_pair_serial{j}').m
        out_b=[];out_c=[]
        b=ex(b,code,*pins,serial_inputs=serial,emitted_outputs=out_b)
        c=ex(c,code,*pins,serial_inputs=serial,emitted_outputs=out_c)
        prove(p,eq(out_b,out_c),f'metadata pair outgoing{j}',False)
    claims=[eq(b.st,c.st),eq(b.m,c.m),
            eq([b.r[k] for k in range(42) if k not in (25,34)],
               [c.r[k] for k in range(42) if k not in (25,34)])]
    claims.extend(getattr(b,n)==getattr(c,n) for n in ('s','s1','l','t','carry'))
    prove(p,And(*claims),
          'Changing oldST24/ST34 changes ONLY DC.B8/header; all other '
          'R/ST/M/scalars and outgoing ring are identical')


def native_negative_control():
    observed=json.loads(subprocess.check_output(
        ['node',str(root/'cache-d4-native-topology.cjs'),'--proof-input'],text=True))
    inlet=observed['inlet']['state']['ik1302']
    dc=observed['prefix'][0]['state']['ik1302']
    assert inlet['s1']==10
    assert [inlet['st'][k] for k in (24,25,34)]==[0,0,15]
    assert dc['r'][25]==inlet['st'][24]==0
    assert dc['r'][26]==inlet['st'][25]==0
    assert dc['r'][34]==inlet['st'][34]==15
    assert [dc['r'][k] for k in w['raw']]==[inlet['r'][k] for k in w['raw']]
    assert not observed['report']['nativeD4']
    print('PASS native keyboard-only NEGATIVE control: oldST24/25/34=0/0/F; '
          'DC.B8=0/headerF; no D4, no injected hypotheses.',flush=True)


if __name__=='__main__':
    prefix_sources()
    paired_metadata()
    native_negative_control()
    print('LIMIT: no native preparation of ST24 D..F or ST34=4; '
          'no full-range upstream entry, Ms copy or reverse transfer.',flush=True)
