#!/usr/bin/env python3
"""Exact live-tag route to EE -> A8(S1=E); symbolic compatibility check.

The first AC and later A7 calls create the return addresses. Sequential
ring inputs remain arbitrary, so SAT means compatibility, not reachability.
The separate check_a8_seven_source.cjs now reproduces it with native keys.
"""
import runpy
from pathlib import Path
from z3 import And, Or, ZeroExt, sat, unsat

ROUTE='''AC E2 E5 E6 ED EE E3 91 92 93 94 95 98 9A 93 94 95 98 9A
E4 DE D6 E5 E6 E7 AD A7 E5 E6 E8 E7 A8 A8 A8 A9 93 94 95 98 9A
E5 E6 E0 A7 E5 E6 E8 E7 A8 A8 A8 A9 E1 91 92 93 94 95 98 9A
93 94 95 98 9A E2 E5 E6 ED EE E3 91 92 93 94 95 98 9A
93 94 95 98 9A E4 DE D6 E5 E6 EE A8 A9'''


def check(q):
    byte=lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
    address=lambda a:byte(a.r[36],a.r[39])
    stack=lambda a:tuple(byte(a.st[36+i],a.st[39+i]) for i in range(3))
    a=q['State']('a8_single_start');p=q['base_solver'](a,0xAC)
    p.add(Or(a.r[41]==0,a.r[41]==15))
    sequence=[int(ip,16) for ip in ROUTE.split()]
    b=a;entries=[]
    for index,ip in enumerate(sequence):
        p.add(address(b)==ip)
        assert p.check()==sat,('inconsistent route',index,hex(ip))
        b=b.copy();b.r[36]=q['N4'](ip);b.r[39]=q['N4'](ip>>4)
        entries.append(b)
        b=q['execute_command'](b,ip) # Released keys throughout, not exotic pins.
    assert p.check()==sat
    for label,value in [('initial PC high',a.r[34]),('initial PC low',a.r[31]),
                        ('initial ST32',a.st[32]),('initial ST35',a.st[35])]:
        p.push();values=q['possible_values'](value,p,17);p.pop()
        print(label+': '+','.join(f'{v:X}' for v in values),flush=True)
    def prove(claim,label):
        p.push();p.add(~claim);assert p.check()==unsat,label;p.pop()
        print('PASS:',label,flush=True)
    ee,single=entries[-3:-1]
    prove(And(a.r[34]==14,a.st[35]==7,entries[5].m[34]==6,entries[69].m[34]==6),
          'this route requires initial PC high E, saved ST35=7 and two header-6 EE inputs')
    prove(And(ee.s1==14,stack(ee)[0]==0xA8,single.s1==14,
              address(b)==0x93,*[v==n for v,n in zip(stack(single),(0x93,0xE5,0xA8))]),
          'the internally created A8 tag reaches EE, then one A8 and A9 return to 93')
    prove(And(*[single.r[3*i]==ee.m[1+3*i] for i in range(12)]),
          'EE loads all twelve tetras of its M2 word before the single swap')
    prove(And(b.r[30]==a.r[31],b.r[33]==14),
          'A9 replaces the overwritten word exponent with the original PC low and E')
    # Do not infer source identity merely from equal address VALUES in the
    # candidate. Classify the physical stack permutation on arbitrary states.
    kinds={}
    for ip in set(sequence):
        x=q['State']('short_stack_kind_%x'%ip)
        y=q['execute_command'](x,ip,*q['arbitrary_keys']('short_stack_keys_%x'%ip))
        probe=q['base_solver'](x,ip);old=stack(x);new=stack(y)
        push=(ip&0xF0)|((ip+1)&15)
        choices={'same':old,'rotate':old[1:]+old[:1],'push':(push,)+old[:2]}
        for kind,expected in choices.items():
            probe.push();probe.add(~And(*[v==w for v,w in zip(new,expected)]))
            valid=probe.check()==unsat;probe.pop()
            if valid:kinds[ip]=kind;break
        else:raise AssertionError(('unclassified return stack',ip))
    tags=[('initial',i) for i in range(3)]
    for index,ip in enumerate(sequence):
        if index==30:assert tags[0]==(0xA8,26),'first use of the first A7 tag'
        if index==88:assert tags[0]==(0xA8,26),'EE reuses the SAME old A7 tag'
        if kinds[ip]=='rotate':tags=tags[1:]+tags[:1]
        elif kinds[ip]=='push':tags=[((ip&0xF0)|((ip+1)&15),index)]+tags[:2]
    print('PASS: final EE reuses the tag created by the FIRST A7 (index 26), '
          'already returned through at E7 (index 30); the second A7 tag is discarded.',flush=True)
    print('COMPATIBLE with released keys and arbitrary ring input; this symbolic '
          'check alone is NOT native reachability or full K1.',flush=True)
    return {'q':q,'initial':a,'solver':p,'entries':entries,'final':b,'sequence':sequence}


if __name__=='__main__':
    check(runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py'))))
