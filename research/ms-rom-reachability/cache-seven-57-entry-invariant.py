#!/usr/bin/env python3
"""Closed reset-controller proof: native57 cannot construct a new A7/F.

The immutable exact primary semantics discharge a small inductive invariant
over every incoming edge of the completed conservative reset graph. Keys and
future serial inputs remain arbitrary. Detached positive entries are clearly
conditional and are never installed in the reference calculator.
"""
from collections import Counter
from pathlib import Path
import runpy

from z3 import And, BitVecVal, If, Implies, Or, UGE, ULE, sat, unsat

root = Path(__file__).resolve().parent
w = runpy.run_path(str(root / 'cache46-writer-contracts.py'))
q = w['q']
g = runpy.run_path(str(root / 'cache-numeric-export-gates.py'))
states, edges, graph = g['states'], g['edges'], g['graph']

# These are ALL incoming words in the completed reset overapproximation.
# Possible graph edges may be spurious; absence is used only after provenance,
# closure and the exact local transfer checks below, never as a positive path.
predecessors = {
    0x57: {0x5C, 0x5F},
    0x5A: {0x59, 0x5B, 0x5C, 0x5F},
    0x5B: {0x59, 0x7D, 0x5C, 0x5F},
    0x5C: {0x5A, 0x5C, 0x5F},
    0x5F: {0x59, 0x5C, 0x5F},
}


def invariant(a, code):
    if code in (0x5A, 0x5B):
        return Or(a.r[29] != 7, UGE(a.r[2], 5))
    if code == 0x5C:
        return a.r[29] != 7
    if code == 0x5F:
        return Or(a.r[29] != 7, a.l == 0)
    if code == 0x57:
        return a.l == 0
    return And()


def provenance_and_predecessors():
    assert graph['metadata']['complete'] and graph['metadata']['pending'] == 0
    assert graph['metadata']['terminal'] is None
    # The imported graph loader has checked all six source hashes and argv.
    assert len(states) == 52416 and sum(map(len, edges)) == 95731
    actual = {target: set() for target in predecessors}
    counts = {target: Counter() for target in predecessors}
    for source, row in enumerate(edges):
        for target in row:
            code = states[target][0]
            if code in actual:
                actual[code].add(states[source][0])
                counts[code][states[source][0]] += 1
    assert actual == predecessors
    assert all(states[index][0] == 0 for index in graph['indexes']['roots'])
    assert not set(predecessors).intersection(
        states[index][0] for index in graph['indexes']['roots'])
    fused = graph['metadata']['fusedCommands']
    assert fused == {'93': ['93', '94'], '12': ['12', 'C6']}
    assert not {0x93, 0x12}.intersection(set.union(*predecessors.values()))
    # Internal boundaries of the only fused words do not enter the region.
    for first, second in ((0x93, 0x94), (0x12, 0xC6)):
        a = q['State'](f'seven57_fused_{first:02X}')
        p = w['base'](a, first)
        b = w['ex'](a, first, *q['arbitrary_keys'](f'seven57_fused_keys_{first:02X}'))
        w['prove'](p, w['ip'](b) == second,
                   f'fused {first:02X} internal boundary is only{second:02X}, not a57-region entry')
    print('PASS complete52416/95731 graph, all6 immutable source hashes, '
          'roots/closure/fused boundaries and all16 incoming word-pairs.', flush=True)
    for target, row in counts.items():
        print('ALL PREDECESSORS', f'{target:02X}',
              {f'{code:02X}': count for code, count in sorted(row.items())}, flush=True)


def exact_gate_contracts():
    for code in (0x59, 0x5A, 0x5B, 0x5C, 0x5D, 0x5F, 0x7D):
        a = q['State'](f'seven57_gate_{code:02X}')
        p = w['base'](a, code)
        outputs = []
        b = w['ex'](a, code, *q['arbitrary_keys'](f'seven57_gate_keys_{code:02X}'),
                    emitted_outputs=outputs)
        contracts = {
            0x59: And(w['ip'](b) == w['byte'](a.r[29] | 10, q['N4'](5)),
                      b.l == 0, b.r[23] == 0),
            0x5A: And(w['ip'](b) == If(ULE(a.r[2], 4), BitVecVal(0x5C, 8),
                                        BitVecVal(0x4E, 8)),
                      b.l == If(ULE(a.r[2], 4), q['N1'](0), q['N1'](1))),
            0x5B: And(w['ip'](b) == 0x5A, b.r[23] == 2),
            0x5C: And(w['ip'](b) == w['byte'](a.r[29], q['N4'](5)),
                      b.r[35] == a.r[29],
                      b.l == If(ULE(a.r[26], 8), q['N1'](0), q['N1'](1))),
            0x5D: And(w['ip'](b) == 0xB8, b.l == 1, b.r[23] == 2),
            0x5F: And(w['ip'](b) == w['byte'](a.r[29], q['N4'](5)), b.l == a.l),
            0x7D: And(w['ip'](b) == If(ULE(a.r[2], 4), BitVecVal(0x7F, 8),
                                        BitVecVal(0x5B, 8))),
        }
        w['prove'](p, And(contracts[code], w['eq'](w['A'](b), w['A'](a)),
                         b.r[2] == a.r[2], b.r[29] == a.r[29],
                         w['eq'](outputs, a.m)),
                   f'{code:02X} exact gate/flags; holds R2/R29/A12 and outgoing ring')


def inductive_entry_proof():
    # No field constraints at the external inlets59 and7D. Other words use
    # only their incoming invariant. Each theorem covers ALL possible next
    # entries at once, not just the shortest graph or one keyboard sample.
    sources = sorted(set.union(*predecessors.values()))
    assert sources == [0x59, 0x5A, 0x5B, 0x5C, 0x5F, 0x7D]
    for code in sources:
        a = q['State'](f'seven57_induction_{code:02X}')
        p = w['base'](a, code)
        p.add(invariant(a, code))
        b = w['ex'](a, code, *q['arbitrary_keys'](f'seven57_induction_keys_{code:02X}'))
        goals = [target for target, previous in predecessors.items() if code in previous]
        claim = And(*[Implies(w['ip'](b) == target, invariant(b, target))
                      for target in goals])
        w['prove'](p, claim, f'{code:02X} preserves ALL outgoing region invariants: '
                   + '/'.join(f'{target:02X}' for target in goals))
        if code == 0x5C:
            p.push(); p.add(w['ip'](b) == 0x57)
            assert p.check() == unsat
            p.pop()
    # Induction: reset is outside the region; every entry comes from one of
    # the audited pairs; the two outside inlets establish the invariants and
    # every inside predecessor preserves them. Hence ALL reset57 entries L0.
    a = q['State']('seven57_native_L0')
    p = w['base'](a, 0x57); p.add(a.l == 0)
    outputs = []
    b = w['ex'](a, 0x57, *q['arbitrary_keys']('seven57_native_L0_keys'),
                emitted_outputs=outputs)
    w['prove'](p, And(b.r[21] == a.r[21], w['ip'](b) == 0x55,
                     w['eq'](outputs, a.m)),
               '57/L0 holds arbitrary A7, exits55 and writes nothing; '
               'no C/mask premise needed (NOT preservation of whole A12)')
    print('CLOSED IN THIS RESET MODEL: ALL reachable57 entries have L0; '
          '57 cannot construct NEW A7=F from7 or any nonF. It can retain '
          'an ALREADY present F. Other F constructors and partialK2 remain open.', flush=True)


def conditional_but_unreachable_constructor():
    a = q['State']('seven57_unreachable_5A')
    p = w['base'](a, 0x5A)
    p.add(a.r[29] == 7, ULE(a.r[2], 4), UGE(a.r[26], 9), a.r[21] == 7,
          *[a.r[3*index] == 15 for index in range(7)],
          *[a.r[3*index+2] == 8 for index in range(1, 7)])
    b = a
    for index, code in enumerate((0x5A, 0x5C, 0x57)):
        w['prove'](p, w['ip'](b) == code, f'CONDITIONAL5A→5C→57 stage{index}', False)
        outputs = []
        old = b
        b = w['ex'](b, code, *q['arbitrary_keys'](f'seven57_unreachable_keys_{index}'),
                    emitted_outputs=outputs)
        w['prove'](p, w['eq'](outputs, old.m), 'CONDITIONAL chain no write', False)
    w['prove'](p, And(b.r[21] == 15, w['ip'](b) == 0x55),
               'CONDITIONAL5A/R29=7/R2<=4/R26>=9 makesF via5C→57; '
               'entry premise contradicts the proved reset5A invariant')
    p.push(); p.add(invariant(a, 0x5A)); assert p.check() == unsat; p.pop()
    # The other entry is genuinely compatible with the inlets, but loses L.
    a = q['State']('seven57_59_chain')
    p = w['base'](a, 0x59); p.add(a.r[29] == 7)
    b = a
    for index, code in enumerate((0x59, 0x5F, 0x57)):
        w['prove'](p, w['ip'](b) == code, 'forced59/7→5F→57', False)
        b = w['ex'](b, code, *q['arbitrary_keys'](f'seven57_59_chain_keys_{index}'))
    w['prove'](p, And(b.r[21] == a.r[21], w['ip'](b) == 0x55),
               '59/R29=7→5F→57 holds ANY A7, even when incoming59 L1; '
               'R2/R26/C/key timing cannot rescue this constructor')


if __name__ == '__main__':
    provenance_and_predecessors()
    exact_gate_contracts()
    inductive_entry_proof()
    conditional_but_unreachable_constructor()
