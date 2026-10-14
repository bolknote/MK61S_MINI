#!/usr/bin/env python3
"""Origin of the BC bridge operand/type, not a native exchange witness.

All positive paths are detached universal primary-chip contracts. Reset
graph absence is used only with verified coverage/source hashes. Per-tick
pins/serial pages are arbitrary. No ROM edits, state setters, free return
addresses or reference dispatch overrides are used.
"""
from collections import Counter
from pathlib import Path
import runpy

from z3 import And, BitVec, If, Or, UGE, ULE, sat

root = Path(__file__).resolve().parent
old = runpy.run_path(str(root / 'cache-reader-return-contract.py'))
r, w, q = old['r'], old['w'], old['q']
states, edges, double = old['states'], old['edges'], old['double']
raw = w['raw']


def scan_initializers():
    for code in (0x35, 0xFA):
        a = q['State'](f'decoder_scan_{code:02X}'); p = w['base'](a, code)
        out = []; b = w['ex'](a, code,
            *q['arbitrary_keys'](f'decoder_scan_keys_{code:02X}'), emitted_outputs=out)
        w['prove'](p, And(b.r[32] == 15, b.s1 == 0,
            b.r[2] == a.r[2], b.r[5] == a.r[5],
            *[b.r[j] == a.r[j] for j in raw], r['ready'](b) == r['ready'](a),
            w['eq'](out, a.m)),
            f'{code:02X} universally initializes typeF/S1zero, holds mode/raw6/readiness/ring')


def keyboard_prefixes():
    check = runpy.run_path(str(root / 'verify_c8_recovery_candidate.py'),
                          init_globals={'transport': {'q': q}})
    cases = (
        ('35 45 8B 48', 0),
        ('35 B5 B7 45 8B 48', 1),
        ('35 B5 83 45 8B 48', 0),
        ('35 C5 8A 65 7B B7 45 8B 48 B1 B3', None),
    )
    for seq, expected_type in cases:
        v = check['verify_sequence']([int(n, 16) for n in seq.split()])
        assert v['result'] == sat
        p, b = v['solver'], v['final']
        claim = (And(w['ip'](b) == 0x4A, b.r[32] == expected_type)
                 if expected_type is not None else
                 And(Or(w['ip'](b) == 0xB8, w['ip'](b) == 0xB9),
                     Or(b.r[29] == 8, b.r[29] == 9)))
        w['prove'](p, claim, 'ALL-entry/physical-tick keyboard prefix: '+seq)
    # Repeating35 any finite number does not preserve a custom old type.
    # The initializer proof resets it on EVERY scan, not just on first press.
    print('LIMIT: four exact decoder families, not all future keyboard paths. '
          'Internal54/56,28 and68 sources are NOT excluded by these prefixes.', flush=True)


def source_frontier():
    expected = {
        0x7A: {0xFA: 42, 0x7C: 266, 0x7E: 98},
        0x7C: {0x7A: 170, 0x7C: 266, 0x7E: 98},
        0x7E: {0x7C: 266, 0x7E: 98, 0x28: 53},
        0x79: {0x7C: 266, 0x7E: 98},
        0xB5: {0x35: 806, 0xB3: 30},
        0x83: {0xB5: 400},
        0xB7: {0xB5: 400, 0x7B: 551, 0xB3: 30, 0x54: 230, 0x0A: 21},
        0x0A: {0xFA: 42},
        0x28: {0x60: 37, 0x1D: 4, 0x26: 38, 0x36: 3},
    }
    for target, parents in expected.items():
        actual = Counter(states[i][0] for i, row in enumerate(edges)
                         for child in row if states[child][0] == target)
        assert actual == parents
    graph = r['inlet']['g']['graph']
    roots = graph['indexes']['roots']
    assert all(states[i][0] == 0 for i in roots)
    assert len(states) == 52416 and sum(map(len, edges)) == 95731
    assert graph['metadata']['fusedCommands'] == {'93': ['93', '94'], '12': ['12', 'C6']}
    for first, second in ((0x93, 0x94), (0x12, 0xC6)):
        a = q['State'](f'decoder_fused_{first:02X}'); p = w['base'](a, first)
        b = w['ex'](a, first, *q['arbitrary_keys'](f'decoder_fused_keys_{first:02X}'))
        w['prove'](p, w['ip'](b) == second,
                   'fused internal boundary does not enter the decoder-source region', False)
    # 7A/7C/7E/79 do not change type. FA establishes F. Their sole OTHER
    # external entry is28. Therefore any non-F79 must have entered this
    # region through28 since the last FA, including arbitrary internal loops.
    for code in (0x7A, 0x7C, 0x7E, 0x79, 0xB5, 0x83, 0x0A):
        a = q['State'](f'decoder_hold_type_{code:02X}'); p = w['base'](a, code)
        b = w['ex'](a, code, *q['arbitrary_keys'](f'decoder_hold_keys_{code:02X}'))
        w['prove'](p, b.r[32] == a.r[32], f'{code:02X} universally holds type', False)
    # The old complete B3 induction rules out its artificial lower dispatches
    # B5/B7. Recheck the local induction, not just a hardcoded edge deletion.
    a = q['State']('decoder_B1_guard'); p = w['base'](a, 0xB1)
    b = w['ex'](a, 0xB1, *q['arbitrary_keys']('decoder_B1_guard_keys'))
    w['prove'](p, And((w['ip'](b) == 0xB3) == UGE(a.r[29], 8),
                     b.r[29] == a.r[29]), 'B1/B3 original high-operand guard')
    a = q['State']('decoder_B3_guard'); p = w['base'](a, 0xB3)
    p.add(UGE(a.r[29], 8))
    b = w['ex'](a, 0xB3, *q['arbitrary_keys']('decoder_B3_guard_keys'))
    w['prove'](p, And(UGE(w['ip'](b), 0xB8), ULE(w['ip'](b), 0xBF),
                     b.r[29] == a.r[29]), 'reset B3 cannot feed B5/B7')
    predecessors_b3 = Counter(states[i][0] for i, row in enumerate(edges)
                              for child in row if states[child][0] == 0xB3)
    assert predecessors_b3 == {0xB1: 149, 0xB3: 30} and states[0][0] != 0xB3
    # Hence ALL resetB5/83 typeF follows from35 and the holder transfers.
    for code in (0x83, 0x79, 0x0A):
        a = q['State'](f'decoder_typeF_{code:02X}'); p = w['base'](a, code)
        p.add(a.r[32] == 15)
        sequence = ((0x0A, 0xB7, 0x45, 0x8B, 0x48) if code == 0x0A else
                    (code, 0x45, 0x8B, 0x48))
        b = old['walk'](a, p, sequence, f'decoder_typeF_{code:02X}')
        w['prove'](p, w['ip'](b) == 0x4A,
                   f'{code:02X}/typeF cannot enter the BC bridge via B1')
    print('PASS COMPLETE source frontier: ALL reset83 have typeF; '
          'FA-origin79 has typeF across any internal loop; a non-F79 '
          'requires the OTHER inlet28. FA/0A also cannot open B1. '
          'B7 still has original54 and7B/65/68 sources: NOT globally closed.', flush=True)


def exact_internal_gates():
    contracts = {
        0x28: lambda a, b: And(b.s1 == 14,
            w['ip'](b) == If(a.r[26] == 0, q['BitVecVal'](0x2A, 8),
                                             q['BitVecVal'](0x7E, 8))),
        0x7E: lambda a, b: w['ip'](b) == (q['BitVecVal'](0x70, 8) | q['ZeroExt'](4, a.r[35])),
        0x79: lambda a, b: And(b.s1 == 6, w['ip'](b) == 0x45),
        0x54: lambda a, b: And(b.r[32] == a.r[32]-1, b.r[2] == 0,
            b.r[5] == a.r[2], b.r[23] == 0, b.s1 == 7,
            w['ip'](b) == If(a.r[32] == 0, q['BitVecVal'](0x56, 8),
                                              q['BitVecVal'](0xB7, 8))),
        0x56: lambda a, b: w['ip'](b) == If(ULE(a.r[29], 2),
             q['BitVecVal'](0x58, 8), q['BitVecVal'](0x65, 8)),
        0x62: lambda a, b: And(b.r[26] == a.r[1]+1,
            w['eq'](b.r[0:36:3], a.r[0:36:3])),
        0x6F: lambda a, b: And(w['ip'](b) == 0x62, b.r[26] == a.r[1]+1,
            b.r[22] == a.r[25], w['eq'](b.r[0:36:3], a.r[0:36:3])),
    }
    for code, claim in contracts.items():
        a = q['State'](f'decoder_gate_{code:02X}'); p = w['base'](a, code); out = []
        b = w['ex'](a, code, *q['arbitrary_keys'](f'decoder_gate_keys_{code:02X}'),
                    emitted_outputs=out)
        w['prove'](p, And(claim(a, b), w['eq'](out, a.m)),
                   f'exact internal gate{code:02X}/no outgoing write')
    for low in (True, False):
        a = q['State']('decoder_54_zero_type_'+str(low)); p = w['base'](a, 0x54)
        p.add(a.r[32] == 0, ULE(a.r[29], 2) if low else UGE(a.r[29], 3))
        sequence = ((0x54, 0x56, 0x58) if low else
                    (0x54, 0x56, 0x65, 0x7B, 0xB7, 0x45, 0x8B, 0x48,
                     0x4A, 0x4C, 0x4E))
        b = old['walk'](a, p, sequence, 'decoder_54_zero_type_'+str(low))
        w['prove'](p, And(b.r[2] == a.r[2], b.r[5] == 0,
            w['ip'](b) == (0x4E if low else 0x97),
            *[b.r[j] == a.r[j] for j in raw]),
            '54/type0 '+('operands0..2 via58' if low else 'operands3..F via65')+
            ' restore OLD active mode; no idle/B1/BC before4E/97')


def earlier_internal_bridges():
    for source in (0x28, 0x54):
        for selector in (10, 11, 12):
            tag = f'{selector:X}'; label = f'decoder_from{source:02X}_park_{tag}'
            a = q['State'](label); p = w['base'](a, source)
            p.add(UGE(a.r[32], 3), ULE(a.r[32], 14), r['ready'](a))
            if source == 0x28:
                p.add(a.r[26] != 0, a.r[35] == 9, a.r[29]-a.r[2] == selector-5)
                prefix = (0x28, 0x7E, 0x79)
                end_active = a.r[5]
            else:
                p.add(a.r[29] == selector-6)
                prefix = (0x54, 0xB7)
                end_active = a.r[2]
            branch = {10: (0xBA, 0xCC, 0xBB), 11: (0xBB,), 12: ()}[selector]
            sequence = (*prefix, 0x45, 0x8B, 0x48, 0xB1, 0xB3, *branch,
                        0xBC, 0x49, 0xBD, *double, 0xBE, 0xB0, 0x33)
            b = old['walk'](a, p, sequence, label, only_ring_writer=0xBC)
            w['prove'](p, And(w['ip'](b) == 0x35, b.r[2] == end_active, b.r[5] == 0,
                w['eq'](b.st[0:27:3], a.r[0:27:3])),
                f'CONDITIONAL original{source:02X}/{tag} bridge: '
                'ALL256^3 raw codes inST0, savedR5zero; ANY original mode pair')
            print('CONDITIONAL EARLIER ENTRY:', f'{source:02X}', tag,
                  len(sequence), 'original ROM words; no native inlet claimed.', flush=True)
    print('LIMIT:28 needs nonzeroR26/type9 and (R29-R2)=5/6/7; '
          '54 needs operand4/5/6. BOTH still need type3..E and a ready '
          'numericST1. All native fields must coexist at the actual entry. '
          'BC writes services/does not read the overwritten word: no safe '
          'physical destination, full-ring entry, inverse or partialK2.', flush=True)


def counter_ready_packet_and_forced_return():
    a = q['State']('decoder_counter_ready'); p = w['base'](a, 0x6F)
    p.add(r['ready'](a), a.r[1] == 7, a.r[4] == 7, a.r[25] == 7, a.r[28] == 7)
    b = old['walk'](a, p, (0x6F, 0x62), 'decoder_counter_ready')
    w['prove'](p, And(b.r[26] == 8, r['ready'](b),
        w['eq'](b.r[0:36:3], a.r[0:36:3]),
        b.r[2] == a.r[2], b.r[5] == a.r[5]),
        '6F/62 can jointly retain ALL A12/readiness/counter8 for arbitrary other fields')
    # The literal/counter does NOT supply a new return address. Select the
    # ORIGINAL6D->6F branch, with all future pins/pages arbitrary. Both
    # executions vary six raw tetras independently; no calculator mutation.
    a = q['State']('decoder_forced6E'); other = a.copy()
    for j in raw: other.r[j] = BitVec(f'decoder_forced6E_other{j}', 4)
    p = w['base'](a, 0x6D)
    first_pins = q['arbitrary_keys']('decoder_forced6D_pins')
    first_serial = q['State']('decoder_forced6D_serial').m
    ob, oc = [], []
    b = w['ex'](a, 0x6D, *first_pins, serial_inputs=first_serial, emitted_outputs=ob)
    c = w['ex'](other, 0x6D, *first_pins, serial_inputs=first_serial, emitted_outputs=oc)
    p.add(w['ip'](b) == 0x6F)
    w['prove'](p, And(w['ip'](c) == 0x6F, w['stack'](b)[0] == 0x6E,
        w['stack'](c)[0] == 0x6E, w['eq'](ob, a.m), w['eq'](oc, other.m)),
        'original6D branch pushes6E and copies no raw payload to outgoing ring')
    for i, code in enumerate((0x6F, 0x62, 0x6E)):
        w['prove'](p, And(w['ip'](b) == code, w['ip'](c) == code),
                   f'original6D branch forces{code:02X}', False)
        pins = q['arbitrary_keys'](f'decoder_forced6E_keys{i}')
        serial = q['State'](f'decoder_forced6E_serial{i}').m
        before_b, before_c = b, c; ob, oc = [], []
        b = w['ex'](b, code, *pins, serial_inputs=serial, emitted_outputs=ob)
        c = w['ex'](c, code, *pins, serial_inputs=serial, emitted_outputs=oc)
        w['prove'](p, And(w['eq'](ob, before_b.m), w['eq'](oc, before_c.m)),
                   'forced6E tail makes no new outgoing copy', False)
    w['prove'](p, And(w['ip'](b) == 0x61, w['ip'](c) == 0x61,
        *[w['eq'](getattr(b, n), getattr(c, n)) for n in ('r', 'st', 'm')],
        *[getattr(b, n) == getattr(c, n) for n in ('s', 's1', 'l', 't', 'carry')],
        w['eq'](ob, oc)),
        'selected original6D/6F/62/6E forgets ALL six independent raw tetras in primary/output')
    p.push(); p.add(And(*[a.r[j] != other.r[j] for j in raw])); assert p.check() == sat; p.pop()
    print('LIMIT: counter/readiness repair cannot redirect THIS original62 return '
          'to1D/28 or idle. Earlier correlated copies, other chips and the '
          'original physical programme are NOT erased/excluded by this proof.', flush=True)


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    scan_initializers()
    keyboard_prefixes()
    source_frontier()
    exact_internal_gates()
    earlier_internal_bridges()
    counter_ready_packet_and_forced_return()
    r['inlet']['immutable_reference']()
