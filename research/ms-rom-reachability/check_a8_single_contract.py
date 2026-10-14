#!/usr/bin/env python3
"""Local contracts for the two admitted EE -> A8 -> A9 return classes."""
import runpy
from pathlib import Path
from z3 import And, sat, unsat, ZeroExt


def check(q):
    byte=lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
    address=lambda a:byte(a.r[36],a.r[39])
    for target in (0x93,0xDD):
        a=q['State']('short_contract_%x'%target);p=q['base_solver'](a,0xEE)
        p.add(a.s1==14,a.r[35]==14,
              *[byte(a.st[36+i],a.st[39+i])==v
                for i,v in enumerate((0xA8,target,0xE5))])
        assert p.check()==sat
        page=q['State']('short_contract_page_%x'%target).m
        b=q['execute_command'](a,0xEE,*q['arbitrary_keys']('short_ee_%x'%target),
                               serial_inputs=page)
        output=[]
        c=q['execute_command'](b,0xA8,*q['arbitrary_keys']('short_a8_%x'%target),
                               emitted_outputs=output)
        d=q['execute_command'](c,0xA9,*q['arbitrary_keys']('short_a9_%x'%target))
        claims=[address(b)==0xA8,b.s1==14,address(c)==0xA9,c.s1==0,
                address(d)==target,d.s1==0,d.r[33]==14,d.r[30]==a.r[32]]
        claims += [output[1+3*i]==a.m[1+3*i] for i in range(12)]
        claims += [output[i]==page[i] for i in range(42) if i%3!=1 or i>=37]
        claims += [d.r[3*i]==page[1+3*i] for i in range(10)]
        p.push();p.add(~And(*claims));assert p.check()==unsat;p.pop()
        print(f'PASS: EE -> one A8 -> A9 -> {target:02X}: copies the first M2 '
              'number to the next M2 page, keeps ten tetras of the overwritten '
              'number in A, sets R30=old R32 and R33=E.',flush=True)
        if target==0xDD:
            e=q['execute_command'](d,0xDD,*q['arbitrary_keys']('short_return_dd'))
            p.add(address(e)!=0xD0);assert p.check()==unsat
            print('PASS: the DD return has S1=0 and must enter D0, not the D4 store.',flush=True)


if __name__=='__main__':
    check(runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py'))))
