#!/usr/bin/env python3
"""Source-sensitive mode audit BEFORE the conditional low-flag07 writer.

Mode5 cannot be replaced by the old high-flag theorem: it is a NEW colour
of the same complete caller/data-flow slice. Original77 clears the flag
AND sets modeF. Exact source relations, not keyboard search, decide which
joint packets exist. Positive SAT states are not native witnesses.
"""
from pathlib import Path
import runpy

from z3 import And, Extract, Implies, Or, UGE, sat, unsat

root = Path(__file__).resolve().parent
previous = runpy.run_path(str(root / 'cache-bc-lowflag-b-source.py'))
r, w, q, basis, states, edges, pred, execute, walk = (previous[n] for n in
    ('r', 'w', 'q', 'basis', 'states', 'edges', 'pred', 'execute', 'walk'))
checked = previous['checked']
old = basis['old']
wanted = lambda a: Or(a.r[35] == 9, a.r[35] == 11)
coloured = lambda a: And(wanted(a), a.r[2] != 15)
safe = lambda a: Implies(coloured(a), a.r[26] != 0)
shape = lambda a: a.r[38] == a.r[35]+8
origin = lambda a: Implies(wanted(a), Or(a.r[2] == 15, shape(a)))
even = lambda a: Extract(0, 0, a.r[32]) == 0


def zero_invariant(a, code):
    if code == 0x1F:
        return Implies(wanted(a), And(a.r[26] == 15, UGE(a.s1, 7)))
    if code == 0x1C: return safe(a)
    if code == 0x12: return ~wanted(a)
    if code == 0xA3: return basis['correlation'](a)
    if code == 0x77: return And()
    if code in (0x22, 0x36, 0x37, 0x38, 0x55, 6):
        return Implies(coloured(a), Or(a.r[26] != 0, basis['before_increment'](a)))
    if code in (7, 0x6D):
        return Implies(coloured(a), Or(a.r[26] != 0, basis['dead_before'](a)))
    if code == 0x6F:
        return And(a.r[26] == 0, a.s1 == 14, Implies(coloured(a), basis['dead_before'](a)))
    if code == 0x6E: return Implies(coloured(a), basis['dead_before'](a))
    if code == 0x61: return Implies(coloured(a), basis['dead_after'](a))
    if code == 0x3A: return ~coloured(a)
    return safe(a)


def mode_coloured_zero07_sources():
    region, counts, pairs = basis['zero07_cut']()
    checked('same COMPLETE14/21 selected A3 vector/counter provenance',
            basis['a3_diagonal_provenance'])
    checked('ALL selected zero1F/1C real callers and counterzero/kind5 source',
            lambda: basis['onef_native_sources'](region))
    for code in sorted(counts):
        if code == 0x62: continue
        label = f'lowflag_B_mode_zero07_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); p.add(zero_invariant(a, code))
        b = execute(a, p, code, label)
        if code == 0x6F:
            w['prove'](p, w['ip'](b) == 0x62, 'ORIGINAL6F forces62', False)
            b = execute(b, p, 0x62, label+'_62'); destinations = [0x6E]
        else: destinations = sorted({dst for first, dst in pairs if first == code})
        w['prove'](p, And(*[Implies(w['ip'](b) == dst, zero_invariant(b, dst))
                           for dst in destinations]),
            f'ALL ORIGINAL{code:02X} preserves COMPLETE658/822 MODE-coloured joint source')
    print('PASS GLOBAL selected zero07 and6E: kind9/B + mode!=F '
          'forces bytes30/60; original6E gives27/57 and61 cannot select3A. '
          'This uses MODE, NOT an assumed high flag: flag0/1/2 is included.', flush=True)
    return region


def nonzero_invariant(a, code):
    typ, f = a.r[32], a.r[26] == 15
    if code == 0x1F: return And()
    if code == 0x1C: return shape(a)
    if code == 0x6E: return Or(origin(a), basis['dead_before'](a))
    if code == 0x61: return Or(origin(a), basis['dead_after'](a))
    if code in (0x3A, 0x27, 0x38): return origin(a)
    if code in (6, 7):
        return And(origin(a), Or(And(typ == 0, a.r[29] == 0), a.r[38] == 8))
    if code in (0x6D, 0x60): return And(origin(a), Or(even(a), a.r[38] == 8))
    if code == 0x77: return And(even(a), a.r[35] == 7)
    if code == 0x1A: return And(typ == 0, shape(a))
    if code in (0x18, 0x1B, 0x1D):
        parity = (Or(Extract(0, 0, typ) == 1, And(f, Or(typ == 0, typ == 2)))
                  if code == 0x1B else Or(even(a), And(f,
                      typ == 1 if code == 0x18 else Or(typ == 1, typ == 3))))
        return And(parity, Implies(wanted(a), Or(a.r[2] == 15, And(f, shape(a)))))
    if code == 0x2D: return And(typ == 2, shape(a))
    if code == 0x2C: return And(Or(even(a), typ == 1, typ == 3), origin(a))
    return And(Implies(a.r[35] == 7, even(a)), Implies(wanted(a), a.r[2] == 15))


def mode_coloured_nonzero07_sources(zero_region):
    region, counts, pairs = old['source_cut']()
    assert {i for i in region if states[i][0] == 0x6E} == {
        i for i in zero_region if states[i][0] == 0x6E}
    checked('ALL1C real selector=kind+8 provenance', old['all_1c_selector_provenance'])
    for code in sorted(counts):
        label = f'lowflag_B_mode_nonzero07_{code:02X}'
        a = q['State'](label); p = w['base'](a, code)
        p.add(nonzero_invariant(a, code))
        if code in (0x1F, 0x1A): p.add(a.r[26] == 15)
        b = execute(a, p, code, label)
        destinations = sorted({dst for first, dst in pairs if first == code})
        w['prove'](p, And(*[Implies(w['ip'](b) == dst, nonzero_invariant(b, dst))
                           for dst in destinations]),
            f'ALL ORIGINAL{code:02X} preserves COMPLETE1345/1702 MODE-coloured origin')
    print('PASS GLOBAL selected nonzero07: kind9/B implies modeF OR '
          'selector=kind+8. At kindB/mode5 the selector is3, not9; '
          'flag0/1/2 and counter8 do NOT bypass this joint source bound.', flush=True)
    a = q['State']('lowflag_B_mode_excluded07'); p = w['base'](a, 7)
    p.add(nonzero_invariant(a, 7), previous['seed07_packet'](a, 87))
    assert p.check() == unsat
    print('PASS actual new07/mode5/selector9/kindB packet UNSAT '
          'under COMPLETE native source induction. Early A0 backups '
          'cannot repair its incompatible control fields.', flush=True)
    all_nonzero25 = {i for i, a in enumerate(states) if a[0] == 0x25
                    and (a[7] is None or any(v != 0 for v in a[7]))}
    assert len(all_nonzero25) == 58
    assert {i for i in region if states[i][0] == 0x25} == all_nonzero25
    print('PASS same MODE-coloured source proof covers ALL58 nonzero25: '
          'kind9/B implies modeF, not mode5. No missing independent '
          '25 boundary supplies the conditional low-flag writer.', flush=True)
    return region


def mode_coloured_initial28_sources(nonzero_region):
    inlet = previous['loops']['inlet']
    counts, pairs = inlet['source_cut']()
    targets = {i for i, a in enumerate(states) if a[0] == 0x28
               and (a[7] is None or any(v != 0 for v in a[7]))}
    region = basis['backward'](targets, {7, 0x1F, 0x1C})
    assert len(region) == 1213 and len(counts) == 33
    assert {i for i in region if states[i][0] == 7} == {
        i for i in nonzero_region if states[i][0] == 7}
    for code in sorted(counts):
        label = f'lowflag_B_mode_first28_{code:02X}'
        a = q['State'](label); p = w['base'](a, code)
        p.add(nonzero_invariant(a, code))
        if code in (0x1F, 0x1A): p.add(a.r[26] == 15)
        b = execute(a, p, code, label)
        destinations = sorted({dst for first, dst in pairs if first == code})
        w['prove'](p, And(*[Implies(w['ip'](b) == dst, nonzero_invariant(b, dst))
                           for dst in destinations]),
            f'ALL ORIGINAL{code:02X} preserves COMPLETE1213/1525 mode origin')
    for flag in (0, 1, 2):
        a = q['State'](f'lowflag_B_mode_excluded28_flag{flag}'); p = w['base'](a, 0x28)
        p.add(nonzero_invariant(a, 0x28), a.r[23] == flag,
              previous['component']['inlet_packet'](a, 87))
        assert p.check() == unsat
    print('PASS GLOBAL ALL53 native nonzero28: kind9/B implies MODEF. '
          'The ENTIRE new type2/number3/kindB/mode5/flag0..2 writer '
          'packet is excluded, not just its earlier07/counter8 factory. '
          'Conditional F9/twoC9 component contracts remain valid '
          'outside native reachability; backups cannot fix the mode mismatch.', flush=True)


def earlier61_payload_contract():
    a = q['State']('lowflag_B_earlier61_payload'); p = w['base'](a, 0x61)
    b = execute(a, p, 0x61, 'lowflag_B_earlier61_payload')
    p.add(w['ip'](b) == 0x3A); assert p.check() == sat
    w['prove'](p, And(previous['eq'](previous['A'](b),
        [*previous['A'](a)[1:], previous['A'](a)[11]]),
        previous['eq'](previous['B'](b), previous['B'](a)),
        previous['eq'](b.st[:36], a.st[:36])),
        'ORIGINAL61 shifts A before3A, duplicates oldA11; '
        'does NOT copy the discarded oldA0 to B or numericST')
    b = walk(b, p, (0x3A, 6), 'lowflag_B_earlier61_payload_tail')
    w['prove'](p, And(w['ip'](b) == 7,
        previous['eq'](previous['A'](b),
            [*previous['A'](a)[2:11], *([q['N4'](15)]*3)])),
        'ORIGINAL61/3A/06 gives [oldA2..A10,F,F,F]; '
        'later07 reserve is not a pre61 cache reserve')
    other = q['State']('lowflag_B_earlier61_other'); c = a.copy()
    c.r[0], c.r[3] = other.r[0], other.r[3]
    b = a
    for index, code in enumerate((0x61, 0x3A, 6)):
        pins = q['arbitrary_keys'](f'lowflag_B_earlier61_pair_keys{index}')
        serial = q['State'](f'lowflag_B_earlier61_pair_serial{index}').m
        ob, oc = [], []
        b = w['ex'](b, code, *pins, serial_inputs=serial, emitted_outputs=ob)
        c = w['ex'](c, code, *pins, serial_inputs=serial, emitted_outputs=oc)
        if code == 0x61:
            p.add(w['ip'](b) == 0x3A); assert p.check() == sat
            w['prove'](p, w['ip'](c) == 0x3A,
                'same actual61 branch for both independent A0/A1 payloads', False)
        w['prove'](p, previous['eq'](ob, oc),
            f'ORIGINAL{code:02X} pair emits no oldA0/A1 difference', False)
    w['prove'](p, w['same'](b, c),
        'WHOLE-primary pair: arbitrary pre61 A0/A1 differences vanish '
        'after61/3A/06; existing earlier copies/refetch not excluded')
    p.push(); p.add(Or(a.r[0] != other.r[0], a.r[3] != other.r[3]))
    assert p.check() == sat; p.pop()


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    zero = mode_coloured_zero07_sources()
    nonzero = mode_coloured_nonzero07_sources(zero)
    mode_coloured_initial28_sources(nonzero)
    earlier61_payload_contract()
    r['inlet']['immutable_reference']()
    print('PASS mode-coloured source audit. No native/live/ALL5/key '
          'experiment or state/IP/return/ROM repair; no global partialK2 '
          'impossibility claim.', flush=True)
