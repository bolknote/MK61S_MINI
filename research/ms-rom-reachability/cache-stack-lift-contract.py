#!/usr/bin/env python3
"""Exact digit-stack-lift inlet: conditional export, never native entry.

The enabled flag is a symbolic hypothesis, NOT written into a calculator.
All six payload tetras and remaining ring/keyboard inputs are free. The
native negative controls are separate, with unchanged five-chip reference.
"""
from pathlib import Path
import json
import runpy
import subprocess

from z3 import And, BitVecVal, If, Or, UGE, ULE, sat, unsat

root=Path(__file__).resolve().parent
w=runpy.run_path(str(root/'cache46-writer-contracts.py'))
q=w['q']
State,ex,base,keys=(q[n] for n in
                  ('State','execute_command','base_solver','arbitrary_keys'))
ip,eq,A,prove=(w[n] for n in ('ip','eq','A','prove'))
raw=(0,3,9,12,18,21)


def gate_contracts():
    a=State('cache_stack_gate84');p=base(a,0x84)
    b=ex(a,0x84,*keys('cache_stack_gate84_keys'))
    prove(p,And(b.s==a.r[41],b.r[26]==a.r[26]+1,
                *[b.r[j]==a.r[j] for j in raw]),
          '84 holds raw6, increments R26 and copies the lift flag R41 into S')
    a=State('cache_stack_gate85');p=base(a,0x85)
    b=ex(a,0x85,*keys('cache_stack_gate85_keys'))
    target=BitVecVal(0x89,8)-If(a.r[26]==1,BitVecVal(1,8),BitVecVal(0,8)) \
        -If(a.s!=0,BitVecVal(1,8),BitVecVal(0,8))
    prove(p,And(ip(b)==target,*[b.r[j]==a.r[j] for j in raw]),
          '85 holds raw6; next89-[R26=1]-[S!=0], so native S=0 selects88')
    a=State('cache_stack_wait');p=base(a,0xE5);out=[]
    b=ex(a,0xE5,*keys('cache_stack_wait_keys'),emitted_outputs=out)
    prove(p,And(eq(out,a.m),eq(b.st,a.st),b.s1==a.s1,
                *[b.r[j]==a.r[j] for j in range(42) if j not in (36,39)],
                ip(b)==If(a.m[22]==15,BitVecVal(0xE6,8),BitVecVal(0xE5,8))),
          'E5 induction: any finite marker wait holds all non-IP R/ST/S1, no ring write')


def conditional_export():
    a=State('cache_enabled_lift');p=base(a,0x8D)
    # A canonical new-digit entry. No constraints on the payload, all other
    # A metadata, B/C, ST, scalars or serial ring. These are NOT native facts.
    p.add(a.r[26]==0,a.r[41]==15,ULE(a.s1,9))
    b=a
    sequence=[int(v,16) for v in
              '8D 8F 81 82 84 85 87 A7 E5 E6 E8 E7 A8 A8 A8 A9'.split()]
    first_write=None
    for j,code in enumerate(sequence):
        if code==0xE5:p.add(b.m[22]==15)
        prove(p,ip(b)==code,f'enabled lift forced{code:02X}',False)
        before=b;out=[]
        b=ex(b,code,*keys(f'cache_enabled_lift_keys_{j}'),emitted_outputs=out)
        if first_write is None:
            if code==0xE7:
                first_write=out
                prove(p,And(*[out[k+1]==a.r[k] for k in raw],
                            eq(out[1:36:3],A(before)),
                            *[out[k]==before.m[k] for k in range(42)
                              if k not in range(1,36,3)]),
                      'enabled lift E7 exports ALL6 raw tetras in one exact M2 word; M1/M3 held')
            else:
                prove(p,And(eq(out,before.m),
                            *[b.r[k]==a.r[k] for k in raw]),
                      f'enabled lift{code:02X} holds raw6, no ring write',False)
    assert first_write is not None
    prove(p,ip(b)==0x88,
          'four-page lift returns naturally to88; no EE or E4 needed BEFORE first export')
    print('LIMIT: R41=F entry is only a hypothesis; physical destination and '
          'later survival, EE reread, Ms exchange and reverse program write '
          'are not proved by this primary-only contract.',flush=True)


def ordinary_setter():
    a=State('cache_lift_setter9f');p=base(a,0x9F)
    # The native control has type5. The local source theorem covers4..E,
    # but NOT F: wrapping the constructor changes AA's next address.
    p.add(UGE(a.r[33],4),ULE(a.r[33],14))
    b=a
    for j,code in enumerate((0x9F,0xAA,0xE5,0xE6,0xED)):
        if code==0xE5:p.add(b.m[22]==15)
        prove(p,ip(b)==code,f'ordinary setter forced{code:02X}',False)
        before=b;out=[]
        b=ex(b,code,*keys(f'cache_lift_setter9f_keys_{j}'),emitted_outputs=out)
        prove(p,And(eq(out,before.m),b.r[41]==15,
                    *[b.r[k]==a.r[k] for k in raw]),
              f'ordinary setter{code:02X} holds raw6/R41=F, no ring write',False)
    prove(p,ip(b)==0xEE,
          '9F/R33=4..E sets R41=F, but its whole forced inlet reaches EE without export')


def wrapped_setter():
    a=State('cache_lift_setter_typeF');p=base(a,0x9F);p.add(a.r[33]==15)
    b=a
    for j,code in enumerate((0x9F,0xAA)):
        prove(p,ip(b)==code,f'typeF setter forced{code:02X}',False)
        before=b;out=[]
        b=ex(b,code,*keys(f'cache_lift_setter_typeF_keys_{j}'),emitted_outputs=out)
        prove(p,And(eq(out,before.m),b.r[41]==15,
                    *[b.r[k]==a.r[k] for k in raw]),
              f'typeF setter{code:02X} holds raw6/R41=F, no ring write',False)
    prove(p,And(ip(b)==0xAC,b.r[35]==15,b.s1==13),
          '9F/R33=F wraps AA to AC with R35=F/S1=D, NOT a direct D4 or EE entry')
    print('LIMIT: typeF is a nonstandard hypothetical constructor, not a '
          'native keyboard/program entry. This short prefix does not prove '
          'its continuation; cache-typeF-ac-contract.py separately proves '
          'ANY AC forces EE and loses the current raw6 without a new reserve.',flush=True)


def native_disabled_prefix():
    native=json.loads(subprocess.check_output(
        ['node',str(root/'cache-stack-lift-native.cjs'),'--proof-input'],text=True))
    inlet=native['inlet']
    a=State('cache_native_digit_prefix');p=base(a,0x8D)
    # These non-payload fields describe ONE observed native inlet. Raw6 and
    # all serial/scalar inputs remain free, not fixed to the sample bytes.
    p.add(*[getattr(a,group)[j]==value for group in ('r','st')
            for j,value in enumerate(inlet[group])
            if group!='r' or j not in raw],a.s1==inlet['s1'])
    b=a
    for j,event in enumerate(native['prefix']):
        code=event['ip']
        prove(p,ip(b)==code,f'disabled native prefix forced{code:02X}',False)
        if code==0x46:
            prove(p,eq(A(b),[q['N4'](v) for v in event['r'][0:36:3]]),
                  'disabled native digit1 inlet has ONLY digit1 before46, for all256^3 raw payloads')
            break
        before=b;out=[]
        b=ex(b,code,*keys(f'cache_native_digit_prefix_keys_{j}'),emitted_outputs=out)
        prove(p,eq(out,before.m),f'disabled prefix{code:02X} no ring write',False)
    else:raise AssertionError('missing formatter call46')
    # Marker timing is not forced by an arbitrary future ring. First prove
    # the data before waiting; the E5 induction above covers any finite wait.
    for j,code in enumerate((0x46,0xE5,0xE6,0xE8,0xE7)):
        if code==0xE5:p.add(b.m[22]==15)
        prove(p,ip(b)==code,f'disabled writer suffix forced{code:02X}',False)
        before=b;out=[]
        b=ex(b,code,*keys(f'cache_native_digit_writer_keys_{j}'),emitted_outputs=out)
        if code==0xE7:
            prove(p,eq(out[1:36:3],[q['N4'](v) for v in event['r'][0:36:3]]),
                  'after any finite E5 wait, disabled digit1 inlet writes ONLY digit1, not raw codes')
        else:prove(p,eq(out,before.m),f'disabled writer suffix{code:02X} no ring write',False)
    print('LIMIT: fixed digit1/non-payload inlet, arbitrary raw6; not all '
          'digit protocols or preparations, and original program is still '
          'in M3. No global partial-K2 exclusion.',flush=True)


if __name__=='__main__':
    gate_contracts()
    conditional_export()
    ordinary_setter()
    wrapped_setter()
    native_disabled_prefix()
    print('PASS: conditional lift export, ordinary-setter barrier and '
          'raw-free disabled-inlet negative contract.',flush=True)
