#!/usr/bin/env python3
"""Audit the sole AD context in the completed C9/no-EE control cut.

Exact detached source contracts, not a native entry or keyboard recipe.
R35=6 suffices for the AD constructor examined here; other AD types remain
outside this local theorem. Paired runs differ in six raw A tetras and all
current/future M3 tetras, but share other initial state and numeric inputs.
An already-existing independent/encoded reserve is therefore NOT excluded.
Marker-loop lemmas cover any finite wait; completion is conditional, not
a claim about physical timing. The original M3 stream is never rewritten.
"""
from collections import deque
from pathlib import Path
import runpy

from z3 import And, Or

root=Path(__file__).resolve().parent
w=runpy.run_path(str(root/'cache46-writer-contracts.py'))
q=w['q']
State,ex,base,keys=(q[n] for n in
                  ('State','execute_command','base_solver','arbitrary_keys'))
ip,eq,A,prove,stack=(w[n] for n in ('ip','eq','A','prove','stack'))
raw=w['raw']
program=tuple(range(2,42,3))
numeric=tuple(j for j in range(42) if j not in program)


def paired(a,label,positions,scalar_s=False):
    other=State(label+'_other');b=a.copy()
    for j in positions:b.r[j]=other.r[j]
    for j in program:b.m[j]=other.m[j]
    if scalar_s:b.s=other.s
    return b


def common_except(a,b,positions=(),scalars=()):
    return And(*[a.r[j]==b.r[j] for j in range(42) if j not in positions],
               eq(a.st,b.st),*[a.m[j]==b.m[j] for j in numeric],
               *[getattr(a,n)==getattr(b,n)
                 for n in ('s','s1','l','t','carry') if n not in scalars])


def pair_step(b,c,code,label):
    serial=State(label+'_serial').m
    different=State(label+'_other_serial').m
    other_serial=[different[j] if j in program else serial[j] for j in range(42)]
    pins=keys(label+'_keys');ob=[];oc=[]
    bb=ex(b,code,*pins,serial_inputs=serial,emitted_outputs=ob)
    cc=ex(c,code,*pins,serial_inputs=other_serial,emitted_outputs=oc)
    return bb,cc,ob,oc


def no_writes(p,b,c,ob,oc,label):
    prove(p,And(eq(ob,b.m),eq(oc,c.m)),label,False)


def closed_ad_context():
    # The imported inventory validates schema, exact source fingerprints,
    # options, complete/pending0 and every edge before exposing this graph.
    g=runpy.run_path(str(root/'cache-numeric-export-gates.py'))
    states,edges=g['states'],g['edges']
    reached={j for j,s in enumerate(states) if s[0]==0xC9}
    assert len(reached)==146
    todo=deque(sorted(reached))
    while todo:
        j=todo.popleft()
        if states[j][0]==0xEE:continue
        for k in edges[j]:
            if k not in reached:reached.add(k);todo.append(k)
    assert len(reached)==10695
    contexts=[states[j] for j in sorted(reached) if states[j][0]==0xAD]
    assert contexts==[[0xAD,[0xAC,0x71,0xBA],0x93,[6],0,[8],None,[15],None]]
    # S1=6 and S1-R35=0 give R35=6, independently of untracked payload.
    print('PASS closed C9/noEE cut:146 starts,10695 states,pending0; '
          'the sole AD context necessarily has R35=6.',flush=True)


def wait_induction():
    for code,selector,locations in ((0x01,6,raw),(0x02,6,raw),(0xE5,8,(38,))):
        label=f'ad6_wait_{code:02X}'
        a=State(label);c=paired(a,label,locations)
        p=base(a,code);p.add(a.s1==selector)
        b,d,ob,oc=pair_step(a,c,code,label)
        no_writes(p,a,c,ob,oc,label+' no outgoing writes')
        next_codes=(code,code+1)
        excluded=(29,36,39) if code in (0x01,0x02) else (36,39)
        prove(p,And(Or(*[ip(b)==n for n in next_codes]),b.s1==selector,
                    *[b.r[j]==a.r[j] for j in range(42) if j not in excluded],
                    eq(b.st,a.st),common_except(b,d,locations)),
              f'{code:02X} induction: any finite wait holds A/control/stack, '
              'makes no reserve or write and introduces no paired dependence')


def d6_reader_loss():
    # Covers the whole post-DD A, incoming S and the surviving R38, not
    # merely one composed trace or a fixed number of preceding waits.
    label='ad6_d6_local';a=State(label)
    c=paired(a,label,tuple(range(0,36,3))+(38,),scalar_s=True)
    p=base(a,0xD6)
    p.add(a.r[41]==15,a.s1==6,stack(a)[0]==0xA7)
    b,d,ob,oc=pair_step(a,c,0xD6,label)
    no_writes(p,a,c,ob,oc,'D6 no write')
    prove(p,And(ip(b)==0xA7,b.s1==a.r[35],eq(A(b),a.m[0:36:3]),
                b.r[38]==a.r[38],d.r[38]==c.r[38],
                common_except(b,d,(38,))),
          'D6 reads all12 M1 tetras into A and clears EVERY prior A/S '
          'difference; only the incoming R38 tetra survives')


def pre_reader_tail():
    # Fresh, unconstrained counter/control states: these proofs do not
    # inherit the one-pass marker conditions of the composed example.
    for code,nxt in ((0x03,0x04),(0x04,0xBA),(0xBA,0xCB),
                     (0xCB,0xDD),(0xDD,0xD6)):
        label=f'ad6_pre_reader_{code:02X}'
        a=State(label);c=paired(a,label,raw)
        p=base(a,code);p.add(a.s1==6)
        b,d,ob,oc=pair_step(a,c,code,label)
        no_writes(p,a,c,ob,oc,'pre-reader no write')
        claim=And(ip(b)==nxt,b.s1==6,eq(stack(b),stack(a)),
                  b.r[32]==a.r[32],b.r[35]==a.r[35],b.r[41]==a.r[41])
        if code==0xDD:
            shifted=(33,0,6,9,15,18)
            claim=And(claim,eq(A(b),A(a)[1:]+A(a)[:1]),
                      b.r[38]==a.r[0]+1,b.s==a.r[0],
                      common_except(b,d,shifted+(38,),('s',)))
        else:claim=And(claim,eq(A(b),A(a)),common_except(b,d,raw))
        prove(p,claim,f'ANY S1=6 entry{code:02X}→{nxt:02X}: '
              'payload/paired invariant held, no write')


def remaining_control_loss():
    # Independent of the original R32/R35 or the number of 01/02 passes:
    # D6's result has shared A/ST/scalars and only R38 can still differ.
    a=State('ad6_last_control');c=paired(a,'ad6_last_control',(38,))
    p=base(a,0xA7);p.add(a.r[41]==15)
    b=a
    for j,code in enumerate((0xA7,0xE5,0xE6,0xE8,0xE7)):
        prove(p,And(ip(b)==code,ip(c)==code),'last-control forced source',False)
        if code==0xE5:p.add(b.m[22]==15)
        before_b,before_c=b,c
        b,c,ob,oc=pair_step(b,c,code,f'ad6_last_control_{j}')
        if code!=0xE7:no_writes(p,before_b,before_c,ob,oc,'last-control no write')
        excluded=(38,) if code in (0xA7,0xE5) else ()
        prove(p,And(common_except(b,c,excluded),
                    eq(A(b),before_b.m[1:36:3] if code==0xE7 else A(a))),
              'last-control paired invariant',False)
        if code==0xE7:
            prove(p,And(eq(ob[1:36:3],A(a)),*[ob[k]==oc[k] for k in numeric]),
                  'A7 E5* E6 E8 E7: ANY lone R38 difference is erased '
                  'before the first write; numeric export cannot encode it')


def ad6_route():
    a=State('ad6_route');c=paired(a,'ad6_route',raw)
    p=base(a,0xAD);p.add(a.r[35]==6)
    b=a;encoded=[a.r[0]+14]+[a.r[j] for j in raw[1:]]
    encoded_other=[c.r[0]+14]+[c.r[j] for j in raw[1:]]
    sequence=(0xAD,0xA6,0x01,0x02,0x03,0x04,0xBA,0xCB,0xDD,
              0xD6,0xA7,0xE5,0xE6,0xE8,0xE7)
    new_numeric=None
    for j,code in enumerate(sequence):
        prove(p,And(ip(b)==code,ip(c)==code),f'AD6 source{code:02X}',False)
        if code==0xE5:p.add(b.m[22]==15)
        before_b,before_c=b,c
        b,c,ob,oc=pair_step(b,c,code,f'ad6_route_{j}')
        if code!=0xE7:no_writes(p,before_b,before_c,ob,oc,f'AD6{code:02X} no write')
        if code==0xAD:
            prove(p,And(ip(b)==0xA6,b.r[41]==15,b.r[26]==0,
                        eq([b.r[k] for k in raw],[a.r[k] for k in raw]),
                        common_except(b,c,raw)),
                  'AD/R35=6 sets flagF and calls A6 with raw6 intact')
        elif code in (0xA6,0x01,0x02,0x03,0x04,0xBA,0xCB):
            prove(p,And(eq([b.r[k] for k in raw],encoded),
                        eq([c.r[k] for k in raw],encoded_other),
                        b.r[32]==a.r[32],b.r[41]==15,common_except(b,c,raw)),
                  f'AD6{code:02X}: reversible R0-2 encoding held, no other reserve',False)
            if code in (0x01,0x02):
                # One completed pass represents the exit; wait_induction
                # proves inserting any number of self-loops cannot change
                # the payload/paired/control invariant used below.
                p.add(ip(b)==code+1,ip(c)==code+1)
        elif code==0xDD:
            shifted=(33,0,6,9,15,18)
            prove(p,And(ip(b)==0xD6,eq([b.r[k] for k in shifted],encoded),
                        b.r[38]==a.r[0]+15,b.s==a.r[0]+14,
                        b.r[35]==a.r[32],b.r[32]==a.r[32],b.s1==6,
                        common_except(b,c,shifted+(38,),('s',))),
                  'DD rotates the encoded raw6 without loss; R38=originalR0-1; '
                  'still no outgoing reserve')
        elif code==0xD6:
            new_numeric=before_b.m[0:36:3]
            prove(p,And(eq(A(b),new_numeric),b.r[38]==a.r[0]+15,
                        common_except(b,c,(38,))),
                  'Composed D6 discards five raw tetras; just originalR0-1 '
                  'remains in controlR38, not a three-byte reserve')
        elif code in (0xA7,0xE5):
            prove(p,And(eq(A(b),new_numeric),common_except(b,c,(38,))),
                  'M1 word held while onlyR38 can still differ',False)
        elif code in (0xE6,0xE8):
            prove(p,And(eq(A(b),new_numeric),common_except(b,c)),
                  f'{code:02X}: last raw-dependent R38 erased before any numeric write')
        else:
            prove(p,And(ip(b)==0xA8,eq(ob[1:36:3],new_numeric),
                        *[ob[k]==before_b.m[k] for k in range(42)
                          if k not in range(1,36,3)],
                        *[ob[k]==oc[k] for k in numeric],common_except(b,c)),
                  'First E7 writes reread M1, NOT any of the original raw6; '
                  'primary and outgoing numeric states agree in paired runs')
    print('PASS forced completed AD6 route:',
          ' '.join(f'{n:02X}' for n in sequence),
          '; 01/02/E5 may wait arbitrarily long; no EE is needed for this loss.',flush=True)


if __name__=='__main__':
    closed_ad_context()
    wait_induction()
    pre_reader_tail()
    d6_reader_loss()
    remaining_control_loss()
    ad6_route()
    print('LIMIT: conditional AD6 tail/data-loss contracts, not native '
          'AD reachability. Other AD types, reserves made BEFORE the setter, '
          'other writers and an eventual partial K2 remain outside this '
          'exclusion. Original M3 differences remain in the program lane.',flush=True)
