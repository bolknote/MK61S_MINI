#!/usr/bin/env python3
"""ROM contracts behind the native saved-seven construction and its exit.

The final continuation is a conditional symbolic theorem, paired with the
complete keyboard tests. Arbitrary future ring inputs alone are not a recipe.
"""
import runpy
from pathlib import Path
from z3 import And, BitVecVal, If, ZeroExt, sat, unsat

ROOT=Path(__file__).resolve().parent


def check(q):
    byte=lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
    address=lambda a:byte(a.r[36],a.r[39])

    def local(ip,label,claim):
        a=q['State']('seven_fact_%x'%ip)
        b=q['execute_command'](a,ip,*q['arbitrary_keys']('seven_keys_%x'%ip))
        p=q['base_solver'](a,ip)
        p.add(~claim(a,b))
        assert p.check()==unsat,label
        print('PASS:',label,flush=True)

    local(0xAA,'AA saves opcode low/high in R32/R35',
          lambda a,b:And(b.r[32]==a.r[30],b.r[35]==a.r[33]))
    local(0xAD,'AD swaps the saved opcode fields and dispatches on its old high',
          lambda a,b:And(b.r[32]==a.r[35],b.r[35]==a.r[32],
                        address(b)==(0xA0|ZeroExt(4,a.r[35]))))
    local(0xE5,'E5 waits for M22=F, preserving selector and saved tail',
          lambda a,b:And(address(b)==If(a.m[22]==15,BitVecVal(0xE6,8),BitVecVal(0xE5,8)),b.s1==a.s1,
                        b.r[35]==a.r[35],*[b.st[i]==a.st[i] for i in range(36)]))
    local(0xE6,'E6 dispatches E0|S1 and preserves S1, hence S1=6 loops for any keys',
          lambda a,b:And(address(b)==(0xE0|ZeroExt(4,a.s1)),b.s1==a.s1))

    # Check the connected restore schedule, rather than replacing saved ST
    # with independently chosen values. Its control constraints are feasible.
    a=q['State']('seven_restore');p=q['base_solver'](a,0x91);b=a
    schedule=[0x91,0x92]+[0x93,0x94,0x95,0x98,0x9A]*2
    for i,ip in enumerate(schedule):
        p.add(address(b)==ip)
        assert p.check()==sat,('restore route',i)
        b=b.copy();b.r[36]=q['N4'](ip);b.r[39]=q['N4'](ip>>4)
        b=q['execute_command'](b,ip,*q['arbitrary_keys']('seven_restore_keys_%d'%i))
    p.add(~And(b.st[33]==a.r[34],b.st[34]==a.r[35],b.st[35]==a.st[34]))
    assert p.check()==unsat
    print('PASS: connected double restoration yields ST33..35 = old R34, R35, ST34.',flush=True)

    route=runpy.run_path(str(ROOT/'check_a8_single_route.py'))['check'](q)
    a,p,b=route['initial'],route['solver'],route['final']
    suffix='''93 94 95 98 9A E5 E6 E0 A7 E5 E6 E8 E7 A8 A8 A8 A9
E1 91 92 93 94 95 98 9A 93 94 95 98 9A E2 E5 E6 ED EE E3
91 92 93 94 95 98 9A 93 94 95 98 9A E4 DE D6 E5 E6'''
    for i,ip in enumerate(int(s,16) for s in suffix.split()):
        p.add(address(b)==ip)
        assert p.check()==sat,('short continuation',i,hex(ip))
        b=b.copy();b.r[36]=q['N4'](ip);b.r[39]=q['N4'](ip>>4)
        b=q['execute_command'](b,ip)
    p.push();p.add(b.s1!=a.r[35]);assert p.check()==unsat;p.pop()
    p.push();p.add(address(b)!=(0xE0|ZeroExt(4,a.r[35])))
    assert p.check()==unsat;p.pop()
    for reg,target in ((4,0xE4),(6,0xE6)):
        p.push();p.add(a.r[35]==reg);assert p.check()==sat
        p.add(address(b)!=target);assert p.check()==unsat;p.pop()
    print('PASS: compatible continuation dispatches E0|initial R35: '
          'register 4 selects E4, register 6 selects the E6 self-loop.',flush=True)
    return route


if __name__=='__main__':
    check(runpy.run_path(str(ROOT/'ik1302_symbolic.py')))
