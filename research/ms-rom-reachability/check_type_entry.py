#!/usr/bin/env python3
"""Sources of the new 60->18 candidate and the final 77->6D->60 gate.

Prior results: zero-reset first-entry A3 vector classes, R38 domains at
F8/FC/68, and R41 in {0,F}. All local facts below use exact 42-tick semantics
with arbitrary per-tick keyboard and ring inputs. Live return tags are
handled by closed call/return protocols, not by assuming an empty stack.
"""
import runpy
from pathlib import Path

from z3 import And, Or, ZeroExt, sat, unsat

q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State, execute, base, keys = (q[n] for n in
    ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))


def byte(lo,hi):
    return ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)


def address(a):
    return byte(a.r[36],a.r[39])


def vector(a):
    return byte(a.r[37],a.r[40])


def stack(a):
    return [byte(a.st[36+i],a.st[39+i]) for i in range(3)]


templates = {}
pushers = {n:[] for n in (0x06,0x07,0x60,0x6D,0x77,0xA2,0xA3)}
sources_with_selector = {0x06:{0x38,0x3A,0x55},0x07:{0x06},0x60:{0x6D},
                         0x6D:{0x07,0x77},0x77:{0x7E,0xA3}}
vector_sources = {0xA2:{0x96,0xA0,0xA2,0xAD},0xA3:{0xA2,0xAD}}
for ip in range(256):
    a = State(f'bootstrap_{ip}')
    b = execute(a,ip,*keys(f'bootstrap_keys_{ip}'))
    p = base(a,ip); old,new = stack(a),stack(b)
    pushed = (ip&0xF0)|((ip+1)&15)
    for kind,expected in [('same',old),('rotate',old[1:]+old[:1]),
                           ('push',[pushed]+old[:2])]:
        p.push();p.add(~And(*[v == w for v,w in zip(new,expected)]))
        valid = p.check() == unsat;p.pop()
        if valid:
            break
    else:
        raise AssertionError(f'unclassified stack at {ip:02X}')
    templates[ip] = a,b,kind
    if kind == 'push' and pushed in pushers:
        pushers[pushed].append(ip)
    if ip in (0xC7,0xC8):
        continue
    if ip == 0xA3:
        p.add(Or(a.r[37] == a.r[40],
                 *[vector(a) == n for n in (0x90,0x93,0xCC,0xD3,0xD8)]))
    if ip in (0xF8,0xFC,0x68):
        p.add(Or(*[a.r[38] == n for n in (7,8,14)]))
    for required_selector,source_map in [(4,sources_with_selector),
                                         (9,sources_with_selector),(None,vector_sources)]:
        for target,ordinary in source_map.items():
            if ip in ordinary:
                continue
            p.push()
            p.add(*[v != target for v in old],address(b) == target)
            if required_selector is not None:
                p.add(b.r[38] == required_selector)
            assert p.check() == unsat,(ip,target,required_selector)
            p.pop()
assert pushers == {0x06:[0x05],0x07:[],0x60:[],0x6D:[],0x77:[0x76],
                   0xA2:[0xA1],0xA3:[]},pushers
print('PASS: all 256 sources/stack forms; only 05/76/A1 create tags 06/77/A2; '
      'no return tags 07/60/6D/A3 exist',flush=True)

count = 0


def prove(ip,label,claim,condition=None):
    global count
    a,b,_ = templates[ip]
    p = base(a,ip)
    if condition is not None:
        p.add(condition(a))
    assert p.check() == sat,f'empty precondition: {label}'
    p.add(~claim(a,b))
    assert p.check() == unsat,label
    count += 1
    print('PASS:',label,flush=True)


def expect_stack(ip,kind):
    assert templates[ip][2] == kind,(ip,kind)


# Live tag 06. The body cannot recurse into 05 or branch out of the helper.
expect_stack(0x05,'push')
prove(0x05,'05 starts the tag-06 protocol with S1=9',
      lambda a,b:And(address(b) == 0x01,b.s1 == 9))
for ip,successors in [(0x01,(0x01,0x02)),(0x02,(0x02,0x03)),(0x03,(0x04,)),
                      (0x04,(0xBA,)),(0xBA,(0xCC,)),(0xCC,(0xCD,)),(0xCD,(0xC9,))]:
    expect_stack(ip,'same')
    prove(ip,f'live 06: {ip:02X} preserves S1=9 and stays inside the helper',
          lambda a,b,successors=successors:And(b.s1 == 9,
              Or(*[address(b) == n for n in successors])),lambda a:a.s1 == 9)
prove(0xCD,'CD assigns R38=8 before the 06 return',lambda a,b:b.r[38] == 8)
expect_stack(0xC9,'rotate')
prove(0xC9,'C9 returns to 06 without changing selector 8',
      lambda a,b:And(address(b) == 0x06,b.r[38] == 8),
      lambda a:And(stack(a)[0] == 0x06,a.r[38] == 8))
expect_stack(0x06,'same');expect_stack(0x07,'push')
prove(0x06,'06 immediately enters 07 and preserves R32/R38',
      lambda a,b:And(address(b) == 0x07,b.r[32] == a.r[32],b.r[38] == a.r[38]))
print('PASS: [x,y,z] --05--> [06,x,y] --C9--> [x,y,06] --07--> [08,x,y]; '
      'the tag is ejected before it could be reused',flush=True)

# Tag 77 is NOT a direct-return protocol: E2 makes a nested call. Keep this
# path open rather than silently treating the first EE return as a return 77.
expect_stack(0x76,'push')
prove(0x76,'76 starts the tag-77 protocol through E2 with S1=D',
      lambda a,b:And(address(b) == 0xE2,b.s1 == 13))
expect_stack(0xE2,'push')
prove(0xE2,'E2 pushes the nested return E3 and enters E5 with S1=D',
      lambda a,b:And(address(b) == 0xE5,b.s1 == 13),lambda a:a.s1 == 13)
for ip,successors in [(0xE5,(0xE5,0xE6)),(0xE6,(0xED,)),(0xED,(0xEE,))]:
    expect_stack(ip,'same')
    prove(ip,f'live 77: {ip:02X} preserves S1=D and stays inside the helper',
          lambda a,b,successors=successors:And(b.s1 == 13,
              Or(*[address(b) == n for n in successors])),lambda a:a.s1 == 13)
a = State('bootstrap_e5_e6');p = base(a,0xE5)
p.add(Or(a.r[41] == 0,a.r[41] == 15))
b = execute(a,0xE5,*keys('bootstrap_e5'))
p.add(address(b) == 0xE6)
b = execute(b,0xE6,*keys('bootstrap_e6'))
assert p.check() == sat
p.add(~Or(b.r[38] == 12,b.r[38] == 13))
assert p.check() == unsat
print('PASS: every E5->E6 completion under R41 in {0,F} assigns R38 in {C,D}',flush=True)
prove(0xED,'ED preserves R38',lambda a,b:b.r[38] == a.r[38])
expect_stack(0xEE,'rotate')
prove(0xEE,'EE returns to the nested tag E3, not to 77, with its selector unchanged',
      lambda a,b:And(address(b) == 0xE3,b.r[38] == a.r[38]),lambda a:stack(a)[0] == 0xE3)
expect_stack(0xE3,'push')
prove(0xE3,'E3 starts another nested call at 91',lambda a,b:address(b) == 0x91)
expect_stack(0x77,'push')
print('PASS: [x,y,z] --76--> [77,x,y] --E2--> [E3,77,x] --EE--> [77,x,E3] '
      '--E3--> [E4,77,x]. Tag 77 survives; no exclusion of its later return is claimed.',flush=True)

# Live tag A2. A1 fixes vector D3; after its return A2 loops or transfers via
# A3 to D3. D3's push ejects the old A2 tag regardless of its selected branch.
expect_stack(0xA1,'push')
prove(0xA1,'A1 enters E5 with vector D3 and S1=9',
      lambda a,b:And(address(b) == 0xE5,vector(b) == 0xD3,b.s1 == 9))
for ip,successors in [(0xE5,(0xE5,0xE6)),(0xE6,(0xE9,))]:
    expect_stack(ip,'same')
    prove(ip,f'live A2: {ip:02X} preserves vector/S1 and stays inside the call',
          lambda a,b,successors=successors:And(vector(b) == vector(a),b.s1 == 9,
              Or(*[address(b) == n for n in successors])),lambda a:a.s1 == 9)
expect_stack(0xE9,'rotate')
prove(0xE9,'E9 returns to A2 with the vector unchanged',
      lambda a,b:And(address(b) == 0xA2,vector(b) == vector(a)),lambda a:stack(a)[0] == 0xA2)
expect_stack(0xA2,'same')
prove(0xA2,'A2 only waits or enters A3, preserving vector, R32 and R26',
      lambda a,b:And(Or(address(b) == 0xA2,address(b) == 0xA3),
                      vector(b) == vector(a),b.r[32] == a.r[32],b.r[26] == a.r[26]))
expect_stack(0xA3,'same');expect_stack(0xD3,'push')
prove(0xA3,'A3 dispatches through the vector and preserves R32 and R26',
      lambda a,b:And(address(b) == vector(a),b.r[32] == a.r[32],b.r[26] == a.r[26]))
print('PASS: [x,y,z] --A1--> [A2,x,y] --E9--> [x,y,A2] --D3--> [D4,x,y]; '
      'returned A2 has vector D3 and cannot be reused with vector 77',flush=True)
for ip,v in [(0xA0,0xD3),(0x96,0x90)]:
    prove(ip,f'{ip:02X} supplies vector {v:02X}, never 77',lambda a,b,v=v:vector(b) == v)
for nxt,constructor in [(0xA2,2),(0xA3,3)]:
    prove(0xAD,f'AD->{nxt:02X} leaves R32={constructor} and R26=0',
          lambda a,b,nxt=nxt,constructor=constructor:Or(address(b) != nxt,
              And(b.r[32] == constructor,b.r[26] == 0)))
print('PASS by source coverage and tag lifetime: any first-entry A3->77 has '
      'R32 in {2,3}, never 5, and R26=0',flush=True)
print('PASS by the same complete source/tag coverage: at A2/A3, any vector '
      'outside {90,D3} comes from AD. A2 then has R32=2/R26=0; '
      'A3 has R32 in {2,3}/R26=0. The statement is not limited to vector 77.',flush=True)

for ip in (0x38,0x3A,0x55):
    prove(ip,f'{ip:02X}->06 clears R32',lambda a,b:And(address(b) == 0x06,b.r[32] == 0))
for ip in (0x07,0x77,0x6D):
    prove(ip,f'{ip:02X} preserves R32, R38 and R26',
          lambda a,b:And(b.r[32] == a.r[32],b.r[38] == a.r[38],b.r[26] == a.r[26]))
prove(0x77,'77 unconditionally enters 6D',lambda a,b:address(b) == 0x6D)
prove(0x6D,'6D enters 60 iff R26 is nonzero; otherwise it enters 6F',
      lambda a,b:And((address(b) == 0x60) == (a.r[26] != 0),
                      (address(b) == 0x6F) == (a.r[26] == 0)))
prove(0x7E,'7E enters 77 only with the already-prepared operation type R35=7',
      lambda a,b:And((address(b) == 0x77) == (a.r[35] == 7),
                      b.r[32] == a.r[32],b.r[38] == a.r[38]))
print(f'PASS: {count} local facts, the E5/E6 pair, and 256 source/stack checks. '
      'CONCLUSION under the stated prior reset invariants: reaching 60 with '
      'R32=5/R38=9 requires 77->6D->60, with entry to 77 either from '
      '7E(R35=7) or from the return tag created by 76. The 07 and A3 alternatives '
      'are excluded for these fields. In addition, A3->77 can never continue '
      'directly through 6D to 60: it has R26=0. The nested 76/77 return is '
      'audited separately by analyze_return77.py. '
      'This is not a general proof that C7/C8 are unreachable.',flush=True)
