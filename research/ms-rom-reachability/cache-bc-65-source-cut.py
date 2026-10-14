#!/usr/bin/env python3
"""Exhaust the DIRECT65 decoder sources under public physical key pins.

ALL reset65 parents are8A/56/68. 8A has only35/C5 andFA physical-key
prefixes; both give operands0..9; their B3 branch gives only8/9.
The5C/5F induction excludes their56
edges, leaving original54/type0 cleanup with type3/flag0 at48. The
separate COMPLETE68 joint induction leaves B2/B9/BB/4E, never BC-C.
This does NOT close every7B/45/8B source, later continuations, limited
BB writes, or partialK2. SAT paths are not native keyboard recipes.
"""
from pathlib import Path
import runpy

from z3 import And, If, Implies, Or, UGE, ULE, sat

root = Path(__file__).resolve().parent
entry = runpy.run_path(str(root / 'cache-bc-68-inlet.py'))
r, w, q, states, edges = (entry[n] for n in ('r', 'w', 'q', 'states', 'edges'))
walk, predecessors = entry['walk'], entry['predecessor_counts']


def complete65_frontier():
    assert sum(a[0] == 0x65 for a in states) == 374
    assert predecessors(0x65) == {0x8A: 328, 0x56: 248, 0x68: 37}
    assert predecessors(0x8A) == {0xC5: 397, 0xFA: 42}
    assert predecessors(0xC5) == {0x35: 806}
    assert predecessors(0x56) == {0x54: 230, 0x5C: 220, 0x5F: 156}
    print('PASS COMPLETE65 frontier:ALL374 classes have only8A/56/68 parents; '
          'ALL8A parents are35/C5 orFA. Graph edges are not native executions.', flush=True)


def physical8a_prefixes():
    check = runpy.run_path(str(root / 'verify_c8_recovery_candidate.py'),
                          init_globals={'transport': {'q': q}})
    for prefix, typ in (((0x35, 0xC5), 5), ((0xFA,), 4)):
        # Stop BEFORE48/B1/B3: filtering on a later B3 branch would hide
        # the perfectly valid operands0..7 that leave through B2 instead.
        seq = (*prefix, 0x8A, 0x65, 0x7B, 0xB7, 0x45, 0x8B)
        result = check['verify_sequence'](seq)
        assert result['result'] == sat
        p, a, b = (result[n] for n in ('solver', 'initial', 'final'))
        # The filter constrains EACH tick to a public matrix pair or no
        # key. It does NOT require fixed keys or a particular timed prefix.
        # Initial controller fields, both modes and serial input stay free.
        w['prove'](p, And(b.r[32] == typ, w['ip'](b) == 0x48, ULE(b.r[29], 9),
            w['eq'](b.r[0:36:3], a.r[0:36:3]),
            w['eq'](b.r[1:36:3], a.r[1:36:3]), w['eq'](b.st[:36], a.st[:36])),
            'ALL-entry/physical-tick8A prefix '+' '.join(f'{n:02X}' for n in prefix)
            +f' gives type{typ}/only operands0..9 BEFORE48, NOT operandC')
        p.push()
        assert q['possible_values'](b.r[29], p, 17) == list(range(10))
        p.pop()
        b = walk(b, p, (0x48, 0xB1), 'bc65_8a_'+f'{prefix[0]:02X}'+'_dispatch')
        w['prove'](p, And(w['ip'](b) == If(UGE(b.r[29], 8), entry['N8'](0xB3),
            entry['N8'](0xB2)), ULE(b.r[29], 9)),
            'original8A/48/B1 exitsB2 orB3, no operandC hidden by a branch filter')
        p.push(); p.add(w['ip'](b) == 0xB3)
        c = walk(b, p, (0xB3,), 'bc65_8a_'+f'{prefix[0]:02X}'+'_high_operand')
        w['prove'](p, Or(w['ip'](c) == 0xB8, w['ip'](c) == 0xB9),
            'ONLY actualB3 subbranch givesB8/B9; lower operands were checked separately')
        p.pop()
    print('PASS both COMPLETE8A source families under public physical key pins. '
          'FA is separately checked, NOT inferred from35/C5. '
          'No complete-ring or keyboard witness is claimed.', flush=True)


def actual56_source_induction():
    # Same original small5-region induction as cache-bc-type-provenance.py,
    # deliberately without its eager native/ALL5 fixture imports.
    parents = {
        0x5A: {0x59: 127, 0x5B: 232, 0x5C: 220, 0x5F: 156},
        0x5B: {0x59: 127, 0x7D: 173, 0x5C: 220, 0x5F: 156},
        0x5C: {0x5A: 336, 0x5C: 220, 0x5F: 156},
        0x5F: {0x59: 127, 0x5C: 220, 0x5F: 156},
    }
    for code, expected in parents.items(): assert predecessors(code) == expected

    def invariant(a, code):
        if code in (0x5A, 0x5B): return Or(a.r[29] & 4 == 0, UGE(a.r[2], 5))
        if code == 0x5C: return a.r[29] & 4 == 0
        if code == 0x5F: return a.r[29] & 5 == 5
        return And()

    sources = sorted({code for row in parents.values() for code in row})
    assert sources == [0x59, 0x5A, 0x5B, 0x5C, 0x5F, 0x7D]
    for code in sources:
        label = f'bc65_5region_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); p.add(invariant(a, code))
        b = w['ex'](a, code, *q['arbitrary_keys'](label+'_keys'))
        targets = [target for target, row in parents.items() if code in row]
        w['prove'](p, And(*[Implies(w['ip'](b) == target, invariant(b, target))
            for target in targets]), f'ALL original{code:02X} preserves COMPLETE5-region invariant')
    for code in (0x5C, 0x5F):
        label = f'bc65_closed56_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); p.add(invariant(a, code))
        b = w['ex'](a, code, *q['arbitrary_keys'](label+'_keys'))
        w['prove'](p, And(w['ip'](b) != 0x54, w['ip'](b) != 0x56),
            f'ALL reset{code:02X} cannot enter54/56, unlimited future keys/serial words')
    a = q['State']('bc65_actual54_gate'); p = w['base'](a, 0x54)
    b = w['ex'](a, 0x54, *q['arbitrary_keys']('bc65_actual54_gate_keys'))
    w['prove'](p, And((w['ip'](b) == 0x56) == (a.r[32] == 0),
        b.r[32] == a.r[32]-1, b.r[2] == 0, b.r[5] == a.r[2], b.r[23] == 0),
        'ALL actual56 reduce to original54/type0; mode saved and flag cleared')

    a = q['State']('bc65_type0_cleanup'); p = w['base'](a, 0x54)
    p.add(a.r[32] == 0, UGE(a.r[29], 3))
    b = walk(a, p, (0x54, 0x56, 0x65, 0x7B, 0xB7, 0x45, 0x8B), 'bc65_type0_cleanup')
    w['prove'](p, And(w['ip'](b) == 0x48, b.r[32] == 3,
        b.r[29] == a.r[29]-3, b.r[2] == a.r[2], b.r[5] == 0, b.r[23] == 0),
        'ALL original54/56/65 cleanup gives type3/operand−3/flag0, ANY old mode')
    b = walk(b, p, (0x48, 0x4A, 0x4C), 'bc65_type0_cleanup_exit')
    w['prove'](p, And(w['ip'](b) == 0x4E, b.r[32] == 3, b.r[23] == 0),
        'ALL actual56/65 prefix exits4E, never DIRECT B1/B3/BC-C')


def complete68_source_induction():
    entry['exact_decoder_gates']()
    entry['low07_number_cut']()
    entry['high77_e_number_cut']()
    entry['joint68_induction']()
    entry['original68_decoder_exits']()


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    complete65_frontier()
    physical8a_prefixes()
    actual56_source_induction()
    complete68_source_induction()
    r['inlet']['immutable_reference']()
    print('PASS GLOBAL DIRECT65→BC-C source cut under public keys: '
          'ALL8A/56/68 parents covered. Other7B/79/54 and later routes/BB remain '
          'open; no full-ring witness, exchange, or general partialK2 prohibition.', flush=True)
