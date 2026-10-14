#!/usr/bin/env python3
"""Exact DA carry/data and final indirect DD source; NOT native reachability.

All symbolic positive states are detached. The native reference sees only
the two existing PC00 keyboard controls, with their program damage explicit.
Arbitrary keys and future incoming ring data conservatively overapproximate
hardware for local UNSAT proofs. They are not keyboard SAT witnesses.
"""
import json
from pathlib import Path
import runpy
import subprocess

from z3 import And,Extract,If,Or,UGE,ULE,ZeroExt,sat

root=Path(__file__).resolve().parent
w=runpy.run_path(str(root/'cache-writer-contract.py'));q=w['q']
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
ip,stack,prove,constant,number=(w[n] for n in ('address','stack','prove','constant','number'))
raw=w['positions']


def decimal_normalizer_guards():
    # Local induction lemmas for the actually observed address normalizer.
    # This list is NOT asserted to be a complete native address-resolution
    # graph. Other reads/constructors may import nondecimal tetras.
    for code in (0x20,0x22,0x2F,0x21,0x23,0x25,0x01,0x02,0x03,0x04,0xBA,0xCB,0x24):
        a=State('da_decimal_guard_%02X'%code);p=base(a,code)
        p.add(*[ULE(a.r[k],9) for k in range(0,27,3)])
        if code==0x24:p.add(a.s==6)
        b=ex(a,code,*keys('da_decimal_guardkeys_%02X'%code))
        prove(p,And(*[ULE(b.r[k],9) for k in range(0,27,3)]),
              'decimal A0..8 guard %02X'%code,False)
        if code==0x20:
            prove(p,ip(b)==0x2F,'20 returns2F',False)
        elif code==0x2F:
            prove(p,Or(ip(b)==0x20,ip(b)==0x21),'2F chooses20/21',False)
    a=State('da_decimal_23_24');p=base(a,0x23)
    b=ex(a,0x23,*keys('da_decimal_23_24keys'))
    p.add(ip(b)==0x24)
    prove(p,b.s==6,'23→24 establishes requiredS6',False)
    a=State('da_decimal_D6');p=base(a,0xD6)
    p.add(*[ULE(a.m[k],9) for k in range(0,27,3)])
    b=ex(a,0xD6,*keys('da_decimal_D6keys'))
    prove(p,And(*[b.r[k]==a.m[k] for k in range(0,27,3)]),
          'D6 imports A0..8 exactly from M1; no manufacture ofF')
    print('PASS13 local decimal guards, including actual2F/20 loop: ANY finite '
          'loop count preserves A0..8 decimal; 23→24 suppliesS6. '
          'Not a complete keyboard/native-path exclusion.',flush=True)


def final_indirect_source():
    a=State('da_final_indirect_dd');p=base(a,0xDD)
    p.add(a.s1==4,stack(a)[0]==0x26,a.r[35]==3,a.r[26]!=0,
          a.r[31]==0,a.r[34]==0)
    b=a
    for j,code in enumerate((0xDD,0xD4,0x26,0x28,0x7E)):
        prove(p,ip(b)==code,'final indirect source step'+str(j),False)
        b=ex(b,code,*keys('da_final_dd_keys'+str(j)))
    prove(p,And(ip(b)==0x73,b.r[33]==a.r[3],b.r[27]==a.r[33],
                b.r[30]==a.r[0],
                *[b.r[3*i]==a.r[(3*i+6)%36] for i in range(12)]),
          'DD/D4/26/28/7E→73: R33=originalDD.R3; all12 A tetras rotated by two')
    for j,code in enumerate((0x73,0x75,0xCA),5):
        prove(p,ip(b)==code,'indirect call00 step'+str(j),False)
        b=ex(b,code,*keys('da_final_dd_keys'+str(j)))
    prove(p,And((ip(b)==0xDA)==(a.r[3]==15),
                (ip(b)==0xDB)==(a.r[3]!=15)),
          'Call00 DA branch IFF original finalDD.R3=F, NOT a numeric sign')
    p.push();p.add(ULE(a.r[3],9))
    prove(p,ip(b)==0xDB,
          'CONDITIONAL decimal sourceDD.R3=0..9 excludes DA on this whole final tail')
    p.pop()
    print('LIMIT: no theorem that every reachable DD.R3 is decimal; malformed '
          'pointers/other entries remain open. No native F construction.',flush=True)


def carry_and_raw_packet():
    a=State('da_call73_packet');p=base(a,0x73)
    p.add(a.r[31]==0,a.r[34]==0,a.r[33]==15,a.r[35]==3,a.s1==14)
    b=a
    for j,code in enumerate((0x73,0x75,0xCA,0xDA)):
        prove(p,ip(b)==code,'DA prefix step'+str(j),False)
        out=[];before=b
        b=ex(b,code,*keys('da_packet_keys'+str(j)),emitted_outputs=out)
        prove(p,And(*[x==y for x,y in zip(out,before.m)],
                    *[b.r[k]==a.r[k] for k in raw]),
              '%02X preserves ALL6 raw tetras; no primary ring write'%code)
    # Hardware adds6 to the A operand as a FOUR-bit operation before the
    # five-bit sum and BCD carry test. Do not silently generalize decimal
    # arithmetic to raw A..F input digits.
    carry0=Extract(4,4,ZeroExt(2,a.r[29])+ZeroExt(2,a.r[30]+q['N4'](6)))
    carry1=Extract(4,4,ZeroExt(2,a.r[32])+ZeroExt(2,a.r[27]+q['N4'](6))+ZeroExt(5,carry0))
    prove(p,And(ip(b)==0xDC,b.r[34]==q['N4'](3)+ZeroExt(3,carry1),
                b.r[26]==15,stack(b)[0]==0x76),
          'Exact DA header3+carry1; depends ONLY on original73 R27/R30/R29/R32')
    p.push();p.add(*[ULE(a.r[k],9) for k in (27,30,29,32)])
    decimal_sum=10*ZeroExt(4,a.r[27])+ZeroExt(4,a.r[30])+10*ZeroExt(4,a.r[32])+ZeroExt(4,a.r[29])
    prove(p,(b.r[34]==4)==UGE(decimal_sum,100),
          'For four DECIMAL address digits only: DA header4 IFF two two-digit addresses sum>=100')
    p.pop()
    p.add(b.r[34]==4);assert p.check()==sat
    writes=[]
    for j,code in enumerate((0xDC,0xDE,0xD4,0xDD,0xD4),4):
        prove(p,ip(b)==code,'DA writer step'+str(j),False)
        out=[];before=b
        b=ex(b,code,*keys('da_packet_keys'+str(j)),emitted_outputs=out)
        if code==0xD4:writes.append((out,before.m))
        else:prove(p,And(*[x==y for x,y in zip(out,before.m)]),'DA packet no other primary write',False)
    prove(p,And(ip(b)==0x76,
                *[writes[0][0][k+3]==a.r[k] for k in raw],
                *[writes[1][0][k]==a.r[k] for k in raw],
                *[out[k]==page[k] for out,page in writes
                  for k in range(42) if k%3!=0 or k>=36]),
          'CONDITIONAL DA/header4 writes exact raw6 twice in M1, holds M2/M3 and returns76')
    print('LIMIT: this is a preserving local packet, not native reader→DA, '
          'not Ms, not physical persistence after76/EE.',flush=True)


def native_source_replays():
    cases=json.loads(subprocess.check_output(
        ['node',str(root/'cache-da-native-topology.cjs'),'--proof-input'],text=True))
    for case in cases:
        es=case['origin'];b=constant(es[0])
        for event,following in zip(es,es[1:]):
            assert number(ip(b))==event['ip']
            b=ex(b,event['ip'],event['keyX'],event['keyY'],
                 serial_inputs=[q['N4'](v) for v in following['m']])
            for group in ('r','st','m'):
                assert [number(v) for v in getattr(b,group)]==following[group]
            for n in ('s','s1','l','t','carry'):
                assert number(getattr(b,n))==following[n]
        assert number(ip(b))==0xDC and number(b.r[34])==3
        assert [e['address'] for e in case['report']['programChanges']]==[38,39]
        print('PASS native finalDD→26→73→DB→DC ALL primary fields:',
              case['report']['pointer'],'; R33 source0, header3, damage38/39.',flush=True)


if __name__=='__main__':
    decimal_normalizer_guards()
    final_indirect_source()
    carry_and_raw_packet()
    native_source_replays()
