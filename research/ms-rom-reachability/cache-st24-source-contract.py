#!/usr/bin/env python3
"""Upstream ST24 source, exact native replays and labelled causal hypotheses.

Original ROMs and keyboard-only native snapshots. Modified R26 exists ONLY
in detached primary symbolic states, never the reference calculator. The
recorded-word pair theorem is not a native construction of its initial flag.
"""
import json
from pathlib import Path
import runpy
import subprocess

from z3 import And,BitVec,If,UGE

root=Path(__file__).resolve().parent
w=runpy.run_path(str(root/'cache-writer-contract.py'))
q=w['q']
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
ip,stack,prove,constant,number=(w[n] for n in ('address','stack','prove','constant','number'))
eq=lambda xs,ys:And(*[x==y for x,y in zip(xs,ys)])


def actual_ab6_source():
    a=State('st24_ab_gate');p=base(a,0xAB)
    b=ex(a,0xAB,*keys('st24_ab_gate_keys'))
    prove(p,And(ip(b)==If(UGE(a.r[35],7),q['BitVecVal'](0xA5,8),q['BitVecVal'](0xAD,8)),
                b.r[26]==15,stack(b)[0]==0xAC),
          'AB creates native F/returnAC; type0..6 goesAD, type7..F bypassesAD viaA5')
    p.add(a.r[35]==6)
    sequence=(0xAD,0xA6,0x01,0x02,0x03,0x04,0xBA,0xCB,0xDD,
              0xD6,0xA7,0xE5,0xE6,0xE8,0xE7,0xA8,0xA8,0xA8,0xA9)
    for j,code in enumerate(sequence):
        prove(p,ip(b)==code,f'AB6 completion{j}',False)
        if code==0xE5:p.add(b.m[22]==15)
        b=ex(b,code,*keys(f'st24_ab6_completion_keys{j}'))
        if code in (0x01,0x02):p.add(ip(b)==code+1)
        prove(p,b.r[26]==0,f'AD6 R26 remainszero{j}',False)
    prove(p,And(ip(b)==0xAC,b.r[26]==0),
          'Whole AB/type6→AD→M1 read→four-page lift returnsAC with R26=0')
    # Loop counts are not fixed by the preceding representative exit pass.
    # These universal hold lemmas allow any number of admitted waits.
    for code in (0x01,0x02,0xE5):
        a=State(f'st24_wait_{code:02X}');p=base(a,code)
        b=ex(a,code,*keys(f'st24_wait_keys_{code:02X}'))
        prove(p,b.r[26]==a.r[26],f'ANY finite {code:02X} wait preservesR26',False)
    # A different AC constructor is also blocked, but it is NOT the source
    # of the native AC in the companion protocols (that source is A9).
    a=State('st24_normal_typeF');p=base(a,0x9F);p.add(a.r[33]==15);b=a
    for j,code in enumerate((0x9F,0xAA)):
        prove(p,ip(b)==code,'normal typeF source',False)
        b=ex(b,code,*keys(f'st24_normal_typeF_keys{j}'))
    prove(p,And(ip(b)==0xAC,b.r[26]==0),
          'Separate normal9F/typeF→AA→AC constructor also forces R26=0')


def sources_and_pair(events):
    a=State('st24_upstream_original');newflag=BitVec('st24_upstream_changed_R26',4)
    c=a.copy();c.r[26]=newflag;b=a;p=base(a,0xAC)
    for j,event in enumerate(events[:-1]):
        code=event['ip'];signals=keys(f'st24_upstream_keys{j}')
        serial=State(f'st24_upstream_serial{j}').m
        ob=[];oc=[]
        b=ex(b,code,*signals,serial_inputs=serial,emitted_outputs=ob)
        c=ex(c,code,*signals,serial_inputs=serial,emitted_outputs=oc)
        prove(p,And(ip(b)==ip(c),eq(ob,oc)),f'st24 causal dispatch/output{j}',False)
    prove(p,b.st[24]==a.r[26],
          'Exact recorded AC→C8 operator sequence: C8.ST24 comes from initialAC.R26')
    claims=[eq(b.r,c.r),eq(b.m,c.m),
            eq([b.st[k] for k in range(42) if k!=24],[c.st[k] for k in range(42) if k!=24])]
    claims.extend(getattr(b,n)==getattr(c,n) for n in ('s','s1','l','t','carry'))
    prove(p,And(*claims,c.st[24]==newflag),
          'UNIVERSAL paired recorded sequence: changing ONLY initialAC.R26 '
          'changes ONLY C8.ST24; all dispatches and outgoing42-tetra words agree')


def native_replay_and_hypotheses(observed):
    for case in observed:
        events=case['acToC8'];assert events[0]['ip']==0xAC and events[-1]['ip']==0xC8
        assert events[0]['r'][26]==events[-1]['st'][24]==0
        b=constant(events[0])
        for j,event in enumerate(events[:-1]):
            following=events[j+1]
            assert number(ip(b))==event['ip']
            b=ex(b,event['ip'],event['keyX'],event['keyY'],
                 serial_inputs=[q['N4'](n) for n in following['m']])
            for group in ('r','st','m'):
                assert [number(v) for v in getattr(b,group)]==following[group],(j,group)
            for n in ('s','s1','l','t','carry'):
                assert number(getattr(b,n))==following[n],(j,n)
        print('PASS exact primary native replay:',case['report']['recall'],
              len(events)-1,'consecutive macros; allR/ST/M/scalars matched.',flush=True)
    events=observed[0]['acToC8']
    for flag in (13,14,15):
        baseline=constant(events[0]);b=baseline.copy();b.r[26]=q['N4'](flag)
        for j,event in enumerate(events[:-1]):
            following=events[j+1];serial=[q['N4'](n) for n in following['m']]
            assert number(ip(b))==event['ip'],'hypothesis must stop at its first changed dispatch'
            ob=[];oc=[]
            baseline=ex(baseline,event['ip'],event['keyX'],event['keyY'],
                        serial_inputs=serial,emitted_outputs=ob)
            b=ex(b,event['ip'],event['keyX'],event['keyY'],
                 serial_inputs=serial,emitted_outputs=oc)
            assert [number(v) for v in ob]==[number(v) for v in oc]
        assert number(ip(b))==0xC8 and number(b.st[24])==flag
        for group in ('r','m'):assert [number(v) for v in getattr(b,group)]==events[-1][group]
        assert [number(v) for k,v in enumerate(b.st) if k!=24]==[
            n for k,n in enumerate(events[-1]['st']) if k!=24]
        for n in ('s','s1','l','t','carry'):assert number(getattr(b,n))==events[-1][n]
        print(f'CONDITIONAL detached AC.R26={flag:X}: same complete native macro route '
              'and outgoing words untilC8; ONLY finalST24 changes.',flush=True)
    print('LIMIT: these hypotheses do NOT construct AC.R26 D/E/F by keys; '
          'the real direct/indirect recalls reset it. Other AC constructors '
          'or ST24 repair after the reader remain open.',flush=True)


if __name__=='__main__':
    actual_ab6_source()
    observed=json.loads(subprocess.check_output(
        ['node',str(root/'cache-st24-native-source.cjs'),'--proof-input'],text=True))
    sources_and_pair(observed[0]['acToC8'])
    native_replay_and_hypotheses(observed)
