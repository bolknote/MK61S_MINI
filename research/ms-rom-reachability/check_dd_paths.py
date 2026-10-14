#!/usr/bin/env python3
"""DD sources/dispatch and a non-physical type-construction route through 60.

Universal local facts allow arbitrary per-tick keyboard pins and ring input.
The A3 source restriction additionally uses the completed zero-reset fixpoint
from analyze_gates.py --target cd --r38 --check-dd-invariants.
SAT paths below are not keyboard protocols or reset-reachability results.
"""
import runpy
from pathlib import Path

from z3 import And, BitVecVal, If, Or, UGE, ZeroExt, sat, unsat

q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State, execute, base, keys = (q[n] for n in
    ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))


def byte(lo, hi):
    return ZeroExt(4, lo) | (ZeroExt(4, hi) << 4)


def address(a):
    return byte(a.r[36], a.r[39])


def stack(a):
    return [byte(a.st[36+i], a.st[39+i]) for i in range(3)]


def a3_invariant(a):
    vector = byte(a.r[37], a.r[40])
    return Or(And(a.s1 == 0, vector == 0x90),
              And(a.s1 == 9, Or(a.r[37] == a.r[40],
                  *[vector == n for n in (0x93, 0xCC, 0xD8)])),
              And(Or(a.s1 == 11, a.s1 == 13), vector == 0xD3))


count = 0


def prove(ip, label, claim, initial=None):
    global count
    a = State(f'dd_paths_fact_{count}')
    b = execute(a, ip, *keys(f'dd_paths_fact_keys_{count}'))
    p = base(a, ip)
    if initial is not None:
        p.add(initial(a))
    assert p.check() == sat, f'empty fact precondition: {label}'
    p.add(~claim(a, b))
    assert p.check() == unsat, label
    count += 1
    print('PASS:', label, flush=True)


prove(0xDD, 'DD: R38=old R0+1, R0=old R3, next=D0|S1, S1 unchanged',
      lambda a,b: And(b.r[38] == a.r[0]+1, b.r[0] == a.r[3],
                       address(b) == (0xD0|ZeroExt(4,a.s1)), b.s1 == a.s1))
prove(0xDD, 'DD with S1=D cannot leave its self-loop, even with arbitrary keys',
      lambda a,b: And(address(b) == 0xDD, b.s1 == 13), lambda a:a.s1 == 13)
prove(0x0D, '0D enters DD with S1=0 and unchanged R0',
      lambda a,b: And(address(b) == 0xDD, b.s1 == 0, b.r[0] == a.r[0]))
prove(0xDE, 'DE assigns selector F, clears R26 and dispatches through old R34',
      lambda a,b: And(b.r[38] == 15, b.r[26] == 0, b.s1 == a.r[34],
                       address(b) == (0xD0|ZeroExt(4,a.r[34]))))
prove(0xDE, 'DE->DD prepares the non-escaping selector S1=D',
      lambda a,b: Or(address(b) != 0xDD, b.s1 == 13))
prove(0xDC, 'DC pushes the whole return byte DD and enters DE or EA',
      lambda a,b: And(*[v == w for v,w in zip(stack(b),[0xDD]+stack(a)[:2])],
                       Or(address(b) == 0xDE, address(b) == 0xEA)))
for ip, successors in [(0xD0,(0xF2,0xF3)), (0xD1,(0x91,)),
                       (0xD2,(0x30,)), (0xD3,(0x63,0xD5)), (0xD5,(0x9B,)),
                       (0xD7,(0x7F,0xD9)), (0xD8,(0xF2,)), (0xD9,(0xF3,)),
                       (0xDA,(0xDC,)), (0xDB,(0xDC,)), (0xDF,(0x88,))]:
    prove(ip, f'{ip:02X} exact successor set is contained in '+
          '/'.join(f'{v:02X}' for v in successors),
          lambda a,b,successors=successors: Or(*[address(b) == n for n in successors]))
prove(0xD1, 'D1 clears both R2 and R26', lambda a,b:And(b.r[2] == 0,b.r[26] == 0))
prove(0xD4, 'D4 returns through the top stack byte and preserves S1/R35',
      lambda a,b:And(address(b) == stack(a)[0],b.s1 == a.s1,b.r[35] == a.r[35]))
prove(0xD6, 'D6 returns through the top stack byte, restores S1 from R35 and R0 from M0',
      lambda a,b:And(address(b) == stack(a)[0],b.s1 == a.r[35],b.r[0] == a.m[0]))
prove(0xA3, 'A3 uses the vector, not the stack, and increments S1',
      lambda a,b:And(address(b) == byte(a.r[37],a.r[40]), b.s1 == a.s1+1,
                      byte(b.r[37],b.r[40]) == 0xA3))
prove(0xA3, 'under the reset invariant, A3->DD gives S1=A, hence DD->DA',
      lambda a,b:Or(address(b) != 0xDD,b.s1 == 10), a3_invariant)
prove(0x60, '60 selects 61 for unequal counter nibbles, otherwise ((R38+8)<<4)|8',
      lambda a,b:address(b) == If(a.r[25] != a.r[31],BitVecVal(0x61,8),
                                  (ZeroExt(4,a.r[38]+8)<<4)|8))
for ip in (0x38,0x3A,0x55):
    prove(ip,f'{ip:02X} clears the type constructor R32',lambda a,b:b.r[32] == 0)
prove(0x05, '05 pushes return 06, copies R35 to R32 and sets S1=9',
      lambda a,b:And(b.r[32] == a.r[35],b.s1 == 9,
                      *[v == w for v,w in zip(stack(b),[0x06]+stack(a)[:2])]))
prove(0x76, '76 pushes return 77, clears R2/R26, sets S1=D and enters E2',
      lambda a,b:And(b.r[2] == 0,b.r[26] == 0,b.s1 == 13,address(b) == 0xE2,
                      *[v == w for v,w in zip(stack(b),[0x77]+stack(a)[:2])]))
prove(0x07, '07->6D iff R2>=5; R32 is preserved',
      lambda a,b:And((address(b) == 0x6D) == UGE(a.r[2],5),b.r[32] == a.r[32]))
prove(0x77, '77 sets R2=F and preserves R32',
      lambda a,b:And(b.r[2] == 15,b.r[32] == a.r[32]))

# Complete source check. Stack-return alternatives are not discarded: the
# claim is that any remaining source must consume a previously created DD.
pushers = []
for ip in range(256):
    a = State(f'dd_source_{ip}')
    b = execute(a,ip,*keys(f'dd_source_keys_{ip}'))
    p = base(a,ip)
    old,new = stack(a),stack(b)
    pushed = (ip&0xF0)|((ip+1)&15)
    for kind,expected in [('same',old),('rotate',old[1:]+old[:1]),
                           ('push',[pushed]+old[:2])]:
        p.push();p.add(~And(*[v == w for v,w in zip(new,expected)]))
        valid = p.check() == unsat;p.pop()
        if valid:
            break
    else:
        raise AssertionError(f'unclassified address-stack transform at {ip:02X}')
    if kind == 'push' and pushed == 0xDD:
        pushers.append(ip)
    if ip not in (0x0D,0xA3,0xCB,0xDD,0xDE,0xC7,0xC8):
        p.add(*[v != 0xDD for v in old],address(b) == 0xDD)
        assert p.check() == unsat, f'uncovered DD source: {ip:02X}'
assert pushers == [0xDC], pushers
print('PASS: all 256 sources/stack forms checked; DD sources are 0D/A3/CB/DE/self '
      'or a stack return, whose DD tag can only be created by DC',flush=True)

# D1's apparent escape in the joined graph was caused by losing live return
# identities. Its actual body is a fixed double pass: 92 pushes 93, so the
# first 9A returns to 93 and the second one returns to D2, not to an old tag.
# No path assumptions are added below: every transition is proved forced.
forced = [int(v,16) for v in
          'DD D1 91 92 93 94 95 98 9A 93 94 95 98 9A D2'.split()]
a = State('dd_d1_forced');b = a;p = base(a,0xDD)
p.add(a.s1 == 1,a.r[0] == 3)
for i,(ip,nxt) in enumerate(zip(forced,forced[1:])):
    b = execute(b,ip,*keys(f'dd_d1_forced_keys_{i}'))
    p.push();p.add(~And(address(b) == nxt,b.r[38] == 4))
    assert p.check() == unsat,(ip,nxt)
    p.pop()
print('PASS: DD(S1=1,R0=3) necessarily reaches D2 through the exact double-pass '
      '91/92/93/9A body, preserving R38=4; there is no keyboard escape',flush=True)
print('Combine with analyze_1f_lifetime.py --entry at-d2 --expect-excluded: '
      'the continuation starts with arbitrary S1 and excludes the whole DD-1 family.',flush=True)


path_count = 0


def path(text,label,expected,initial=None):
    global path_count
    sequence = [int(v,16) for v in text.split()]
    a = State(f'dd_path_{path_count}')
    p = base(a,sequence[0]); b = a
    if initial is not None:
        p.add(initial(a))
    for i,(ip,nxt) in enumerate(zip(sequence,sequence[1:])):
        b = execute(b,ip,*keys(f'dd_path_{path_count}_keys_{i}'))
        p.add(address(b) == nxt)
    assert p.check() == expected,label
    path_count += 1
    print('PASS:',label,flush=True)
    return a,b,p


prefix = '60 18 1B 1D 2C 2E'
a,b,p = path(prefix,'selector 9 can bypass 1F and construct type 7 from type 5',sat,
             lambda a:a.r[32] == 5)
p.add(b.r[35] != 7)
assert p.check() == unsat

full = (prefix+' 01 02 03 04 BA CB DD D6 2F 21 22 36 25 '
        '01 02 03 04 BA CB DD D4 26 28 7E 77 6D 60 C8')
a,b,p = path(full,'two-DD type-construction route is SAT only in the relaxed model',sat)
p.add(~And(a.r[38] == 9,a.r[32] == 5,a.r[26] == 15,a.r[25] == a.r[31]))
assert p.check() == unsat
print('PASS: that exact candidate requires initial 60 with R38=9, R32=5, '
      'R26=F and R25=R31',flush=True)
path(prefix+' 01 02 03 04 BA CB DD D6 2F 21 22 36 28',
     'shortcut 36->28 in that candidate is contradictory',unsat)
path('DD D1 91 92 93 94 95 98 9A 77 6D 60 C8',
     'joined DD-1 candidate through 9A->77 is contradictory',unsat)

a,b,p = path('E6 E9 AD A9 93 94 95 98 9A E5 E6 E9 AD A3 DD',
             'restoration can enter DD through A3 in the relaxed model',sat)
p.add(~And(b.s1 == 10,b.r[26] == 0))
assert p.check() == unsat
print('PASS: the restoration candidate enters DD with S1=A and R26=0',flush=True)
print(f'PASS: {count} local facts, 256 source/stack checks and {path_count} exact paths. '
      'No SAT path above establishes a physical calculator protocol.',flush=True)
