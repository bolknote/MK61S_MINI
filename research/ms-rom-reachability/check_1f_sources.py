#!/usr/bin/env python3
"""Complete first-entry source reduction for 1F and the live A5 return tag.

Uses the earlier zero-reset A3-vector invariant and the completed selector
bounds at 68. Those bounds are checked by analyze_gates.py --target cd --r38
--check-1f-invariants. All local claims permit arbitrary tick-level keys/ring.
"""
import runpy
from pathlib import Path
from z3 import And, Or, ZeroExt, sat, unsat

q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,execute,base,keys=(q[n] for n in
    ('State','execute_command','base_solver','arbitrary_keys'))


def byte(lo,hi):
    return ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)


def address(a):
    return byte(a.r[36],a.r[39])


def stack(a):
    return [byte(a.st[36+i],a.st[39+i]) for i in range(3)]


templates={}
pushers={0x1F:[],0xA5:[]}
for ip in range(256):
    a=State(f'source_1f_{ip}')
    b=execute(a,ip,*keys(f'source_1f_keys_{ip}'))
    p=base(a,ip)
    old,new=stack(a),stack(b)
    pushed=(ip&0xF0)|((ip+1)&15)
    forms=[('same',old),('rotate',old[1:]+old[:1]),('push',[pushed]+old[:2])]
    for kind,expected in forms:
        p.push();p.add(~And(*[x==y for x,y in zip(new,expected)]))
        valid=p.check()==unsat;p.pop()
        if valid:
            break
    else:
        raise AssertionError(f'unclassified stack at {ip:02X}')
    if kind=='push' and pushed in pushers:
        pushers[pushed].append(ip)
    templates[ip]=(a,b,kind)
    if ip in (0xC7,0xC8):
        continue
    for target,ordinary in [(0x1F,(0x1F,0x4F,0xA5)),(0xA5,(0xAB,0xAD))]:
        if ip in ordinary:
            continue
        p=base(a,ip)
        p.add(*[v!=target for v in old])
        if ip==0xA3:
            p.add(Or(a.r[37]==a.r[40],*[
                byte(a.r[37],a.r[40])==v for v in (0x90,0x93,0xCC,0xD3,0xD8)]))
        if ip==0x68:
            p.add(Or(*[a.r[38]==v for v in (7,8,14)]))
        p.add(address(b)==target)
        assert p.check()==unsat,(ip,target)
    if ip%64==63:
        print(f'checked {ip+1}/256 source and stack transitions',flush=True)

assert pushers=={0x1F:[],0xA5:[0xA4]}
print('PASS: no return address 1F can be created; only A4 creates return A5',flush=True)
print('PASS under prior first-entry invariants: 1F comes only from 4F/A5/self; '
      'A5 comes only from AB/AD or its A4-created return tag',flush=True)


def prove(ip,label,claim,condition=None):
    a,b,_=templates[ip]
    p=base(a,ip)
    if condition:
        p.add(condition(a))
    p.add(~claim(a,b))
    assert p.check()==unsat,label
    print('PASS:',label,flush=True)


prove(0xA4,'A4 sets type R35=4 and S1=4, then enters 01',
      lambda a,b:And(b.r[35]==4,b.s1==4,address(b)==0x01))
assert templates[0xA4][2]=='push'
for ip,successors in [(0x01,(0x01,0x02)),(0x02,(0x02,0x03)),(0x03,(0x04,)),
                      (0x04,(0xBA,)),(0xBA,(0xCB,)),(0xCB,(0xDD,)),(0xDD,(0xD4,))]:
    assert templates[ip][2]=='same'
    prove(ip,f'live A5 tag: {ip:02X} preserves R35=4/S1=4 and stays inside the call',
          lambda a,b,successors=successors:And(b.r[35]==4,b.s1==4,
              Or(*[address(b)==n for n in successors])),
          lambda a:And(a.r[35]==4,a.s1==4))
assert templates[0xD4][2]=='rotate'
prove(0xD4,'D4 returns to the live A5 tag with R35=4',
      lambda a,b:And(address(b)==0xA5,b.r[35]==4),
      lambda a:And(stack(a)[0]==0xA5,a.r[35]==4))
assert templates[0xA5][2]=='same'
prove(0xA5,'that A5 return selects S1=4 for 1F',
      lambda a,b:And(address(b)==0x1F,b.s1==4),lambda a:a.r[35]==4)
assert templates[0x1F][2]=='same'
prove(0x1F,'the live return continues to 14, independently of the operand',
      lambda a,b:address(b)==0x14,lambda a:a.s1==4)
assert templates[0x14][2]=='push'

# Stack byte algebra, justified by the universal transforms above:
# [x,y,z] --A4--> [A5,x,y] --D4--> [x,y,A5] --14--> [15,x,y].
# The intervening loops preserve the whole address stack and cannot re-enter
# A4. Starting from reset (no A5), induction therefore gives: no A5 tag exists
# outside this protocol, and every actual A5 return carries type R35=4.
print('PASS: 14 pushes 15 and ejects the rotated A5 tag; it cannot be reused later',flush=True)
print('CONCLUSION: every reset-reachable 1F source is covered by the AB, store, '
      'format, AD, or non-escaping self-loop families. Combine the lifetime fixpoints '
      'with check_1f_paths.py; this script alone does not claim C7/C8 unreachable.',flush=True)
