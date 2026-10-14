#!/usr/bin/env python3
"""ROM-wide source classification and the complete control-flow island after 85.

All addresses are internal IK1302 ROM addresses. The serial input and keyboard
pins are arbitrary on every tick. SAT is never treated as a physical protocol.
The restricted A3 vector class comes from the prior first-entry fixpoint; see
README.md. The R41 invariant and the post-85 island do not need that assumption.
"""
import runpy
from collections import deque
from pathlib import Path

from z3 import And, BitVecVal, If, Or, UGE, ULE, ZeroExt, sat, unsat

q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State, execute, base, keys = (q[n] for n in
    ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))


def byte(lo, hi):
    return ZeroExt(4, lo) | (ZeroExt(4, hi) << 4)


templates = {}
writers41 = {}
writers38 = []
sources4 = []
pushes = set()
predecessors = {ip: [] for ip in (0x6D, 0x85, 0xE6)}
for ip in range(256):
    a = State(f'source_{ip}')
    b = execute(a, ip, *keys(f'source_keys_{ip}'))
    p = base(a, ip)
    addr = byte(b.r[36], b.r[39])
    templates[ip] = (a, b, addr)

    p.push()
    p.add(Or(a.r[41] == 0, a.r[41] == 15), b.r[41] != 0, b.r[41] != 15)
    assert p.check() == unsat, f'{ip:02X}: R41 Boolean invariant broken'
    p.pop()
    p.push()
    p.add(b.r[41] != a.r[41])
    changes41 = p.check() == sat
    p.pop()
    if changes41:
        p.push()
        writers41[ip] = tuple(q['possible_values'](b.r[41], p))
        p.pop()

    p.push()
    p.add(b.r[38] != a.r[38])
    changes38 = p.check() == sat
    p.pop()
    if changes38:
        writers38.append(ip)
        p.push()
        p.add(b.r[38] == 4)
        if p.check() == sat:
            sources4.append(ip)
        p.pop()

    old = [byte(a.st[36+i], a.st[39+i]) for i in range(3)]
    new = [byte(b.st[36+i], b.st[39+i]) for i in range(3)]
    pushed = (ip & 0xF0) | ((ip+1) & 15)
    choices = {'same': old, 'rotate': old[1:]+old[:1],
               'push': [pushed]+old[:2]}
    kind = None
    for label, expected in choices.items():
        p.push()
        p.add(~And(*[x == y for x, y in zip(new, expected)]))
        proven = p.check() == unsat
        p.pop()
        if proven:
            kind = label
            break
    assert kind is not None, f'{ip:02X}: unclassified stack operation'
    if kind == 'push':
        pushes.add(pushed)

    for target in predecessors:
        p.push()
        p.add(addr == target)
        if p.check() == sat:
            predecessors[target].append(ip)
        p.pop()
    if ip % 64 == 63:
        print(f'checked {ip+1}/256 ROM commands', flush=True)

assert writers41 == {0x29: (15,), 0x6E: (0,), 0x87: (0,), 0x9F: (15,),
                     0xAD: (15,), 0xCF: (0,), 0xEF: (0,), 0xF0: (15,)}
assert writers38 == [0x1F, 0x59, 0x5C, 0x5F, 0x6C, 0x7C,
                     0x85, 0xB3, 0xCD, 0xDD, 0xDE, 0xE6]
assert sources4 == [0x1F, 0x85, 0xDD, 0xE6]
assert not ({0x6D, 0x85, 0xE6} & pushes)
print('PASS: R41 stays in {0,F} from reset under every ROM command and arbitrary keys', flush=True)
print('PASS: only 1F, 85, DD, E6 can assign R38=4; return stack cannot create 6D/85/E6', flush=True)
for ip, pred in predecessors.items():
    print(f'predecessors({ip:02X}):', ' '.join(f'{x:02X}' for x in pred), flush=True)


def prove(ip, label, claim):
    a, b, addr = templates[ip]
    p = base(a, ip)
    p.add(~claim(a, b, addr))
    assert p.check() == unsat, label
    print('PASS:', label, flush=True)


prove(0x82, '82 rejects count 8 via BD; every other count enters 84',
      lambda a, b, addr: addr == If(a.r[26] == 8, BitVecVal(0xBD, 8), BitVecVal(0x84, 8)))
prove(0x84, '84 increments R26, exchanges digit/S1, and copies R41 into S',
      lambda a, b, addr: And(b.r[26] == a.r[26]+1, b.r[30] == a.s1,
                             b.s1 == a.r[30], b.s == a.r[41], b.r[35] == a.r[35]))
prove(0x84, '84 overflows count F into 75; all other counts enter 85',
      lambda a, b, addr: addr == If(a.r[26] == 15, BitVecVal(0x75, 8), BitVecVal(0x85, 8)))
prove(0x85, '85 copies R35 into R38 and selects 89 - [R26=1] - [S!=0]',
      lambda a, b, addr: And(b.r[38] == a.r[35], addr == BitVecVal(0x89, 8)
          - If(a.r[26] == 1, BitVecVal(1, 8), BitVecVal(0, 8))
          - If(a.s != 0, BitVecVal(1, 8), BitVecVal(0, 8))))
prove(0x87, '87 enters A7, clears R41 and prepares the stack-lift call',
      lambda a, b, addr: And(addr == 0xA7, b.r[41] == 0, b.r[32] == a.r[30], b.s1 == 4))
prove(0x88, '88 clears the new-number fields and enters F2',
      lambda a, b, addr: And(addr == 0xF2, b.s1 == 0, b.r[25] == 0,
                             b.r[31] == 0, b.r[34] == 0, b.r[35] == 0))
prove(0x89, '89 enters F2 without changing R38',
      lambda a, b, addr: And(addr == 0xF2, b.r[38] == a.r[38]))
prove(0xA7, 'A7 enters E5 with S1=8',
      lambda a, b, addr: And(addr == 0xE5, b.s1 == 8))
prove(0xE5, 'E5 always prepares S=R41+C and preserves R41',
      lambda a, b, addr: And(b.s == a.r[41]+12, b.r[41] == a.r[41]))
prove(0xE6, 'E6 assigns R38=S+1 while preserving S and R41, including its self-loop',
      lambda a, b, addr: And(b.r[38] == a.s+1, b.s == a.s, b.r[41] == a.r[41]))

# This is the previously proved A3 vector class, not an assumption that every
# arbitrary A3 starting state has it. All other state fields remain arbitrary.
for ip, (a, b, addr) in templates.items():
    if ip in (0xC7, 0xC8):
        continue
    for target, ordinary in [(0x85, (0x68, 0x84)), (0xE6, (0xE5, 0xE6)),
                             (0x6D, (0x07, 0x77))]:
        if ip in ordinary:
            continue
        p = base(a, ip)
        p.add(*[byte(a.st[36+i], a.st[39+i]) != target for i in range(3)])
        if ip == 0xA3:
            p.add(Or(a.r[37] == a.r[40], *[
                byte(a.r[37], a.r[40]) == v for v in (0x90, 0x93, 0xCC, 0xD3, 0xD8)]))
        p.add(addr == target)
        if target == 0x6D:
            p.add(b.r[38] == 4)
        assert p.check() == unsat, (ip, target)
print('PASS under the prior first-entry vector/stack invariants: '
      '85 comes from 68/84; E6 from E5/E6; 6D with selector 4 from 07/77', flush=True)

a, b, addr = templates[0x68]
p = base(a, 0x68)
p.add(addr == 0x85, ~And(a.r[38] == 0, UGE(a.r[29], 7), ULE(a.r[29], 14)))
assert p.check() == unsat
print('PASS: alternative entry 68->85 requires old R38=0 and R29 in 7..E', flush=True)

# Full control-flow closure from 85, stopping BEFORE E6 executes. No concrete
# data, stack, keyboard or number assumptions are used to prune this graph.
todo = deque([0x85])
seen = set()
edges = {}
while todo:
    ip = todo.popleft()
    if ip in seen:
        continue
    seen.add(ip)
    assert ip not in (0x6D, 0x60, 0xC7, 0xC8), f'unexpected escape at {ip:02X}'
    if ip == 0xE6:
        continue
    a, b, addr = templates[ip]
    edges[ip] = tuple(q['possible_values'](addr, base(a, ip)))
    todo.extend(edges[ip])
assert set(writers38) & seen == {0x85, 0xE6}
assert {ip for ip, targets in edges.items() if 0xE6 in targets} == {0xE5}
print('PASS: complete post-85 control-flow island has', len(seen),
      'nodes and cannot reach 6D/60/C7/C8 before E6', flush=True)
for ip in sorted(edges):
    print(f'  {ip:02X} ->', ' '.join(f'{x:02X}' for x in edges[ip]), flush=True)

a = State('last_e5_before_e6')
b = execute(a, 0xE5, *keys('last_e5_keys'))
c = execute(b, 0xE6, *keys('first_e6_keys'))
p = base(a, 0xE5)
p.add(Or(a.r[41] == 0, a.r[41] == 15), byte(b.r[36], b.r[39]) == 0xE6)
assert p.check() == sat
p.add(~Or(c.r[38] == 12, c.r[38] == 13))
assert p.check() == unsat
print('PASS: every E6 reached from the 85 island replaces any selector 4 with C or D', flush=True)
print('CONCLUSION: with the established reset/vector/stack invariants, '
      'the last source of R38=4 before first C7/C8 must be 1F or DD; '
      'neither 85 nor E6 supplies a surviving 4. No physical invocation is claimed.', flush=True)
