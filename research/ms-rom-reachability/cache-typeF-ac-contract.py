#!/usr/bin/env python3
"""Close every AC input, the type-F detour and every subtype of setter9F.

Exact 42-tick source semantics; no calculator state injection or keyboard
recipe. Arbitrary initial non-payload fields, per-tick keys and serial input.
Paired runs may differ in all14 current/future M3 cells and in rawA6. Other
initial state/serial inputs are shared: an already-existing reserve is NOT
excluded. The E5 exit models any eventually completed marker search, not a
fixed real timing. Original program-lane differences remain unmodified.
"""
from pathlib import Path
import runpy

from z3 import And,UGE,ULE

root=Path(__file__).resolve().parent
w=runpy.run_path(str(root/'cache46-writer-contracts.py'))
q=w['q']
State,ex,base,keys=(q[n] for n in
                  ('State','execute_command','base_solver','arbitrary_keys'))
ip,eq,A,prove,stack=(w[n] for n in ('ip','eq','A','prove','stack'))
raw=(0,3,9,12,18,21)
program=tuple(range(2,42,3))
numeric=tuple(j for j in range(42) if j not in program)
restore=(0xE3,0x91,0x92,0x93,0x94,0x95,0x98,0x9A,
         0x93,0x94,0x95,0x98,0x9A)


def common_except(a,b,excluded_raw=()):
    return And(*[a.r[j]==b.r[j] for j in range(42) if j not in excluded_raw],
               eq(a.st,b.st),*[a.m[j]==b.m[j] for j in numeric],
               *[getattr(a,n)==getattr(b,n) for n in ('s','s1','l','t','carry')])


def marker_wait():
    a=State('typeF_ac_wait');p=base(a,0xE5);out=[]
    b=ex(a,0xE5,*keys('typeF_ac_wait_keys'),emitted_outputs=out)
    prove(p,And(eq(out,a.m),eq(b.st,a.st),b.s1==a.s1,
                *[a.r[j]==b.r[j] for j in range(42) if j not in (36,39)],
                q['Or'](ip(b)==0xE5,ip(b)==0xE6)),
          'E5 induction: all non-IP R/ST/S1 held, no write during any finite marker wait')


def case(label,constraints,prefix):
    a=State('setter9f_'+label);other=State('setter9f_other_'+label)
    paired=a.copy()
    for j in raw:paired.r[j]=other.r[j]
    for j in program:paired.m[j]=other.m[j]
    p=base(a,prefix[0]);p.add(*constraints(a))
    b,c=a,paired
    for j,code in enumerate(prefix):
        if code==0xE5:p.add(b.m[22]==15)
        prove(p,And(ip(b)==code,ip(c)==code),f'{label} forced{code:02X}',False)
        before_b,before_c=b,c
        serial=State(f'setter9f_serial_{label}_{j}').m
        next_other=State(f'setter9f_other_serial_{label}_{j}').m
        paired_serial=[next_other[k] if k in program else serial[k] for k in range(42)]
        pins=keys(f'setter9f_keys_{label}_{j}');ob=[];oc=[]
        b=ex(b,code,*pins,serial_inputs=serial,emitted_outputs=ob)
        c=ex(c,code,*pins,serial_inputs=paired_serial,emitted_outputs=oc)
        prove(p,And(eq(ob,before_b.m),eq(oc,before_c.m)),
              f'{label} {code:02X} no outgoing writes even of original M3',False)
        if code!=0xEE:
            prove(p,And(common_except(b,c,raw),
                        *[b.r[k]==a.r[k] for k in raw],
                        *[c.r[k]==paired.r[k] for k in raw],
                        b.r[41]==(a.r[41] if prefix[0]==0xAC else 15)),
                  f'{label} {code:02X} no new raw6 reserve in R/ST/scalars/non-M3',False)
        else:
            prove(p,And(common_except(b,c),eq(A(b),before_b.m[1:36:3]),
                        eq(A(c),before_c.m[1:36:3])),
                  f'{label}: EE loses ALL prior rawA6; paired primary working state agrees, M3 only passes')
            if label in ('F','AC(any)'):
                prove(p,ip(b)==0xE3,f'{label} EE returns naturally to nested E3')
    print('PASS subtype',label,'forced',' '.join(f'{v:02X}' for v in prefix),
          '; E5 may repeat; no export/reserve BEFORE EE.',flush=True)
    if label not in ('F','AC(any)'):return
    new_numeric=A(b)
    for j,code in enumerate(restore):
        prove(p,And(ip(b)==code,ip(c)==code),f'typeF restore forced{code:02X}',False)
        serial=State(f'typeF_restore_serial_{j}').m
        next_other=State(f'typeF_restore_other_serial_{j}').m
        paired_serial=[next_other[k] if k in program else serial[k] for k in range(42)]
        pins=keys(f'typeF_restore_keys_{j}');ob=[];oc=[]
        before_b,before_c=b,c
        b=ex(b,code,*pins,serial_inputs=serial,emitted_outputs=ob)
        c=ex(c,code,*pins,serial_inputs=paired_serial,emitted_outputs=oc)
        prove(p,And(eq(ob,before_b.m),eq(oc,before_c.m),common_except(b,c)),
              f'typeF restore{code:02X} no new data from differing original M3, no write',False)
    prove(p,And(ip(b)==0xE4,ip(c)==0xE4,eq(A(b),new_numeric)),
          f'{label} AC detour reaches E4 with NEW M2 word, NOT saved program codes')
    before_b,before_c=b,c
    ob=[];oc=[];serial=State('typeF_e4_serial').m
    next_other=State('typeF_e4_other_serial').m
    paired_serial=[next_other[k] if k in program else serial[k] for k in range(42)]
    pins=keys('typeF_e4_keys')
    b=ex(b,0xE4,*pins,serial_inputs=serial,emitted_outputs=ob)
    c=ex(c,0xE4,*pins,serial_inputs=paired_serial,emitted_outputs=oc)
    prove(p,And(eq(b.r[1:36:3],new_numeric),eq(ob,before_b.m),eq(oc,before_c.m),
                common_except(b,c)),
          f'{label} E4 copies the reread numeric word into B; old rawA6 does NOT reappear')


if __name__=='__main__':
    marker_wait()
    case('0..3',lambda a:[ULE(a.r[33],3)],
         (0x9F,0xA0,0xE5,0xE6,0xED,0xEE))
    case('4..E',lambda a:[UGE(a.r[33],4),ULE(a.r[33],14)],
         (0x9F,0xAA,0xE5,0xE6,0xED,0xEE))
    case('F',lambda a:[a.r[33]==15],
         (0x9F,0xAA,0xAC,0xE2,0xE5,0xE6,0xED,0xEE))
    # AC itself permits no free choice of the eventual writer selector:
    # E2 always sets S1=D, regardless of AC's incoming S1/type/lift flag.
    case('AC(any)',lambda a:[],(0xAC,0xE2,0xE5,0xE6,0xED,0xEE))
    print('PASS: all16 constructor subtypes covered. Conditional9F can set '
          'liftF but makes no new raw6 reserve before the forced EE. Original '
          'M3/earlier encoded reserves/other setters remain open. ANY AC '
          'entry forces the same EE read; no alternate writer selector. Not a global '
          'partial-K2 impossibility theorem or keyboard recipe.',flush=True)
