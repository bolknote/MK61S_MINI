#!/usr/bin/env python3
"""Post-76 numeric-read frontier and conditional header7 exit.

This audits local ROM operators, not a native cleanup repair. The full-ring
signF control retains two code copies but has no idle35 in its1656-step run.
A guarded type6 controller round is inductive; different future ring words
can still choose other exits. A type7 M2 read forces a finite D7/7F exit
to33, then quiet35. Neither local proof constructs a native repair.
"""
from pathlib import Path
import runpy

from z3 import And, If, ZeroExt

root = Path(__file__).resolve().parent
w = runpy.run_path(str(root / 'cache-writer-contract.py'))
q = w['q']
State, ex, base, keys = (q[n] for n in
                        ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))
ip, prove = (w[n] for n in ('address', 'prove'))
eq = lambda xs, ys: And(*[x == y for x, y in zip(xs, ys)])
restore = (0x91, 0x92, 0x93, 0x94, 0x95, 0x98, 0x9A,
           0x93, 0x94, 0x95, 0x98, 0x9A)


def wait_contract():
    a = State('digit_cleanup_E5_wait')
    p = base(a, 0xE5)
    out = []
    b = ex(a, 0xE5, *keys('digit_cleanup_E5_wait_keys'), emitted_outputs=out)
    prove(p, And(ip(b) == If(a.m[22] == 15, q['BitVecVal'](0xE6, 8),
                            q['BitVecVal'](0xE5, 8)),
                 eq(out, a.m), eq(b.st, a.st), b.s1 == a.s1),
          'E5 only waits for incomingM[22]=F; arbitrary keys do not change '
          'that gate, ST/S1 or outgoing ring. Finite waits preserve the contract')
    prove(p, And(*[b.r[k] == a.r[k] for k in range(42) if k not in (36, 39)]),
          'E5 also preserves ALL non-IP R fields, including '
          'the type6-round invariant fields R35/R41')


def reread_dispatch():
    a = State('digit_cleanup_E2_source')
    p = base(a, 0xE2)
    b = a
    loaded_type = None
    sequence = (0xE2, 0xE5, 0xE6, 0xED, 0xEE, 0xE3) + restore + (0xE4, 0xDE)
    for j, code in enumerate(sequence):
        if code == 0xE5:
            p.add(b.m[22] == 15)
        if code == 0xEE:
            loaded_type = b.m[34]
        prove(p, ip(b) == code, f'cleanup reread step{j}', False)
        out = []
        before = b
        b = ex(b, code, *keys(f'digit_cleanup_reread_keys{j}'), emitted_outputs=out)
        prove(p, eq(out, before.m), 'cleanup reread prefix no outgoing write', False)
    assert loaded_type is not None
    prove(p, And(ip(b) == (q['BitVecVal'](0xD0, 8) | ZeroExt(4, loaded_type)),
                 b.s1 == loaded_type),
          '76 cleanup: EE M2[34] becomes E4/DE header exactly; '
          'dispatch D0|loadedType, independently of all initial metadata/keys')
    return a, b, p, loaded_type


def type6_and_type7():
    a, b, p, loaded_type = reread_dispatch()
    p.push()
    p.add(loaded_type == 6)
    prove(p, ip(b) == 0xD6,
          'EE type6 forces another numeric M1 reloadD6, not idle or D7')
    p.pop()
    p.add(loaded_type == 7)
    for j, code in enumerate((0xD7, 0x7F)):
        prove(p, ip(b) == code, f'cleanup type7 suffix{j}', False)
        before = b
        out = []
        b = ex(b, code, *keys(f'digit_cleanup_type7_suffix_keys{j}'),
               emitted_outputs=out)
        prove(p, eq(out, before.m), 'type7 suffix no outgoing write', False)
    prove(p, ip(b) == 0x33,
          'CONDITIONAL EE type7 forces D7/7F→33; no outgoing primary writes '
          'in the whole cleanup prefix/suffix')
    # A physical pressed key at33 may leave by its scanner branch. Only the
    # released/quiet step is asserted to finish at the usual idle35.
    b = ex(b, 0x33)
    prove(p, ip(b) == 0x35, 'Quiet33 finishes conditional type7 cleanup at35')
    print('LIMIT: a different native/full-ring M2 type7 source must coexist '
          'with C8 data and the signF inlet. This local exit neither prepares '
          'that source nor proves physical copy retention during changed '
          'cleanup. The original bounded run is NOT an all-keys/infinite-loop '
          'exclusion of cleanup.', flush=True)


def guarded_type6_round():
    # This is NOT a periodic complete-ring state. E7 and A8 write the working
    # stack; the numeric read words may change between rounds. The induction
    # asserts controller repetition only while each FIRST EE reads type6.
    a = State('digit_cleanup_type6_round')
    p = base(a, 0xE2)
    p.add(a.st[34] == 15, a.st[35] == 5, a.r[35] == 5, a.r[41] == 0)
    b = a
    sequence = ((0xE2, 0xE5, 0xE6, 0xED, 0xEE, 0xE3) + restore +
                (0xE4, 0xDE, 0xD6, 0xE5, 0xE6, 0xEF, 0xE5, 0xE6,
                 0xED, 0xEE, 0xE0, 0xA7, 0xE5, 0xE6, 0xE8, 0xE7,
                 0xA8, 0xA8, 0xA8, 0xA9, 0xE1) + restore)
    reads = 0
    for j, code in enumerate(sequence):
        if code == 0xE5:
            p.add(b.m[22] == 15)
        if code == 0xEE:
            if reads == 0:
                p.add(b.m[34] == 6)
            reads += 1
        prove(p, ip(b) == code, f'guarded type6 round step{j}', False)
        b = ex(b, code, *keys(f'digit_cleanup_type6_round_keys{j}'))
    assert reads == 2 and len(sequence) == 51
    prove(p, And(ip(b) == 0xE2, b.st[34] == 15, b.st[35] == 5,
                 b.r[35] == 5, b.r[41] == 0),
          'Guarded first-EE type6 / ST34=F / type5 / R41=0 round: '
          '51 macros return E2 and preserve the invariant class, for all '
          'keys/other ring data; any finite E5 waits can be inserted')
    print('SCOPE: no35 while this class and first-read type6 persist. '
          'This is controller induction under a ring-source guard, NOT an '
          'unconditional all-native-path exclusion or a full-state period. '
          'Type7 deliberately violates the guard and has the other exit.',
          flush=True)


if __name__ == '__main__':
    wait_contract()
    type6_and_type7()
    guarded_type6_round()
    print('PASS cleanup-source/type7 local audit. No native repair or partialK2.',
          flush=True)
