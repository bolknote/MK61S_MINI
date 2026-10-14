#!/usr/bin/env python3
"""Original restore returns and a conditional low-mode/cache-parking bridge.

All positive bridges below are detached universal primary-chip contracts,
NOT native keyboard recipes. No reference/ROM/state setters or fabricated
return addresses are used. The useful 49 return is pushed by original 48.
Serial pages and per-tick pins remain arbitrary except a quiet final33.
The frozen complete reset graph provides caller coverage, not witnesses.
"""
from collections import Counter
import json
from pathlib import Path
import runpy
import subprocess

from z3 import And, BitVec, If, UGE, UGT, ULE, ULT, sat

root = Path(__file__).resolve().parent
r = runpy.run_path(str(root / 'cache-cf-ready-control.py'))
inlet, w, q = r['inlet'], r['w'], r['q']
states, edges = inlet['states'], inlet['edges']
double = r['double']
raw = w['raw']


def original_return_inventory():
    parents = Counter(states[i][0] for i, row in enumerate(edges)
                      for child in row if states[child][0] == 0x91)
    assert parents == {0xE3: 120, 0xD1: 131, 0xE1: 42, 0x8C: 208, 0xBD: 74}
    expected_heads = {0xE4: 111, 0xD2: 72, 0xE2: 33, 0x8D: 67, 0xBE: 43}
    heads = Counter(s[1][0] for s in states if s[0] == 0x91)
    assert heads == expected_heads and sum(heads.values()) == 326
    for caller, head in ((0xE3, 0xE4), (0xD1, 0xD2), (0xE1, 0xE2),
                         (0x8C, 0x8D), (0xBD, 0xBE)):
        a = q['State'](f'restore_caller_{caller:02X}')
        p = w['base'](a, caller)
        if caller == 0xBD: p.add(a.l == 1)
        b = w['ex'](a, caller, *q['arbitrary_keys'](f'restore_caller_keys_{caller:02X}'))
        w['prove'](p, And(w['ip'](b) == 0x91, w['stack'](b)[0] == head,
            *[w['stack'](b)[i+1] == w['stack'](a)[i] for i in range(2)]),
            f'original{caller:02X} pushes{head:02X} and calls91')
    terminal_heads = {s[1][0] for s in states if s[0] == 0x98}
    assert terminal_heads == {0x93, 0xE4, 0xD2, 0xE2, 0x8D, 0xAC,
                              0xBE, 0x6E, 0xE5, 0xDD}
    assert 0x8E not in terminal_heads
    assert 0x8E not in {s[1][1] for s in states if s[0] == 0x98 and s[1][0] == 0x93}
    incoming_8e = Counter(states[i][0] for i, row in enumerate(edges)
                         for child in row if states[child][0] == 0x8E)
    assert incoming_8e == {0xB2: 30, 0xE7: 6, 0xE9: 3, 0xEE: 6}
    assert not {0x98, 0x9A} & set(incoming_8e)
    assert sum(s[0] == 0x98 for s in states) == 255
    assert sum(s[0] == 0x8E for s in states) == 39
    print('PASS COMPLETE restore coverage:326 entry contexts, five callers/heads; '
          'ALL255 98 contexts lack original8E and nested93/8E. '
          '8E itself has39 contexts, reached through B2/E7/E9/EE, NOT9A. '
          'Earlier free98/8E gadgets are conditional, not reset-reachable returns.', flush=True)
    return expected_heads


def walk(a, p, sequence, label, *, only_ring_writer=None):
    b = a
    for index, code in enumerate(sequence):
        w['prove'](p, w['ip'](b) == code, f'{label} forced{code:02X}', False)
        before = b; output = []
        pins = (0, 0) if code == 0x33 else q['arbitrary_keys'](f'{label}_keys{index}')
        b = w['ex'](b, code, *pins,
            serial_inputs=q['State'](f'{label}_serial{index}').m, emitted_outputs=output)
        if code != only_ring_writer:
            w['prove'](p, w['eq'](output, before.m), f'{label} no ring write', False)
        else:
            assert code == 0xBC
            # 48 installs vectorAF in B12/B13 BEFORE the store. Those
            # service tetras are not the corresponding original B values.
            values = [a.r[1+3*j] for j in range(12)] + [q['N4'](15), q['N4'](10)]
            if label.endswith('_C'): values = [q['N4'](7), *values[:13]]
            feed = [output[1+3*j] == v for j, v in enumerate(values)]
            w['prove'](p, And(
                *[output[j] == before.m[j] for j in range(42) if j % 3 != 1],
                *feed),
                f'{label} one exact BC write; M1/M3 held, M2 includes two services')
    return b


def be_tail_contract():
    a = q['State']('restore_BE_tail'); p = w['base'](a, 0x91)
    p.add(w['stack'](a)[0] == 0xBE, a.st[22] == 0)
    sequence = (*double, 0xBE, 0xB0, 0x33)
    b = walk(a, p, sequence, 'restore_BE_tail')
    w['prove'](p, And(w['ip'](b) == 0x35,
        w['eq'](b.r[0:36:3], a.r[0:36:3]),
        w['eq'](b.st[0:27:3], a.r[1:27:3]),
        b.r[2] == a.s1, b.r[5] == a.st[1]),
        '91/originalBE→idle35: A12 held, oldB lower9 inST0, '
        'end mode=(oldS1,oldST1[0])')
    # The branch uses the old numeric ST1 leading tetra, not key pins.
    a = q['State']('restore_BE_gate'); p = w['base'](a, 0xBE)
    b = w['ex'](a, 0xBE, *q['arbitrary_keys']('restore_BE_gate_keys'))
    w['prove'](p, w['ip'](b) == If(a.r[23] == 0,
        q['BitVecVal'](0xB0, 8), q['BitVecVal'](0x63, 8)),
        'BE choosesB0 iff incomingC7=0; otherwise63')


def second_restore_restores_high_mode():
    # Even granting the missing low-S1/flag0/exponent8 inlet at8D, the second
    # ORIGINAL restore reimports the mode that the first temporarily parked.
    a = q['State']('restore_8D_alternative'); p = w['base'](a, 0x8C)
    p.add(a.r[2] == 5, a.r[5] == 0, a.r[23] == 0, a.r[41] == 0,
          ULT(a.s1, 10), a.st[25] == 8, r['zero'](r['lower'](a, 1)))
    sequence = (0x8C, *double, 0x8D, 0x8F, 0x82, 0xBD,
                *double, 0xBE, 0xB0, 0x33)
    b = walk(a, p, sequence, 'restore_8D_alternative')
    assert len(sequence) == 32
    w['prove'](p, And(w['ip'](b) == 0x35,
        *[b.r[j] == a.r[j] for j in raw], b.r[2] == 0, b.r[5] == 5),
        '8C→8D/8F/82/BD→second91→BE/B0→35 can keep raw6, '
        'but reimports saved mode5 (NOT low-mode repair)')
    for label, code, claim in (
            ('8F', 0x8F, lambda x, y: w['ip'](y) == If(UGT(x.r[26], x.s),
                q['BitVecVal'](0x82, 8), q['BitVecVal'](0x81, 8))),
            ('82', 0x82, lambda x, y: And(w['ip'](y) == If(x.r[26] == 8,
                q['BitVecVal'](0xBD, 8), q['BitVecVal'](0x84, 8)),
                y.l == If(x.r[26] == 8, q['N1'](1), q['N1'](0)))),
            ('49', 0x49, lambda x, y: And(w['ip'](y) == 0xBD, y.l == 1))):
        x = q['State']('restore_gate_'+label); p = w['base'](x, code)
        y = w['ex'](x, code, *q['arbitrary_keys']('restore_gate_keys_'+label))
        w['prove'](p, claim(x, y), 'exact restore inlet gate'+label)
    print('LIMIT: the32-word path grants alternative8D metadata, not native keys. '
          'It is a NONEMPTY counterexample to free-return assumptions: '
          'no compulsoryEE, intact raw6, but saved5 still blocks normal07.', flush=True)


def bc_cache_parking_bridge():
    # Unlike free return-tag gadgets, this uses the real 45/8B/48 pushers.
    # 8B forms R29=(oldR29 + ~oldR2) mod16. At oldR2=0, it subtracts
    # one from the sum produced by45. Source that sum B/C/D and a type
    # in3..E BEFORE45 to obtain A/B/C and a B1 route. The unresolved
    # keyboard producer is explicit. No free return is assumed.
    for selector in (10, 11, 12):
        tag = f'{selector:X}'; label = 'restore_BC_park_'+tag
        a = q['State'](label); p = w['base'](a, 0x45)
        p.add(a.r[2] == 0, a.r[5] == 5, a.r[29]+a.s1 == selector+1,
              UGE(a.r[32], 3), ULE(a.r[32], 14), r['ready'](a))
        branch = {10: (0xBA, 0xCC, 0xBB), 11: (0xBB,), 12: ()}[selector]
        sequence = (0x45, 0x8B, 0x48, 0xB1, 0xB3, *branch, 0xBC, 0x49, 0xBD,
                    *double, 0xBE, 0xB0, 0x33)
        b = walk(a, p, sequence, label, only_ring_writer=0xBC)
        w['prove'](p, And(w['ip'](b) == 0x35, b.r[2] == 5, b.r[5] == 0,
            w['eq'](b.st[0:27:3], a.r[0:27:3]),
            *[b.st[j] == a.r[j] for j in raw]),
            f'CONDITIONAL original45/8B/48/B1/B3[{tag}]/BC/49→35: '
            'ALL raw6 parked losslessly inST0; savedR5=0')
        # All16^6 inputs are independent; constraints concern only metadata
        # and the independent B/ST1 preparation, never the code tetras.
        witness = {j: q['BitVec'](label+f'_coverage_raw{j}', 4) for j in raw}
        p.push(); p.add(*[a.r[j] == v for j, v in witness.items()])
        w['prove'](p, And(w['ip'](b) == 0x35,
            *[b.st[j] == v for j, v in witness.items()]),
            f'{tag} universal parking formula for six opaque independent tetras', False)
        p.pop()
        print('CONDITIONAL low-mode parking bridge:', tag,
              ' '.join(f'{code:02X}' for code in sequence), '→35;',
              len(sequence), 'words; exactly one BC M2/service write.', flush=True)
    print('LIMIT: no native source for (R29+S1)=B/C/D and R32=3..E BEFORE45 '
          '(A/B/C atB3), no physical destination '
          'of the BC write, no preserved ordinary registers/services, '
          'no keyboard cache extraction or reverse exchange. The reserve '
          'is ST0, NOT ready zeroST0 and NOT a partialK2 witness.', flush=True)


def operand_origin_contracts():
    callers45 = Counter(states[i][0] for i, row in enumerate(edges)
                        for child in row if states[child][0] == 0x45)
    assert callers45 == {0x35: 806, 0x83: 309, 0xB7: 801, 0x79: 149}
    print('PASS COMPLETE original45 source families:',
          {f'{code:02X}': count for code, count in sorted(callers45.items())}, flush=True)
    for code, claim in (
            (0x45, lambda a, b: And(b.r[29] == a.r[29]+a.s1,
                                    b.r[32] == a.r[32]+1)),
            (0x8B, lambda a, b: And(b.r[29] == a.r[29]+~a.r[2],
                                    b.r[32] == a.r[32],
                                    b.r[2] == a.r[5], b.r[5] == a.r[2]))):
        a = q['State'](f'restore_operand_{code:02X}'); p = w['base'](a, code)
        b = w['ex'](a, code, *q['arbitrary_keys'](f'restore_operand_keys_{code:02X}'))
        w['prove'](p, claim(a, b), f'exact operand/type/mode provenance{code:02X}')
    # Coverage of original49 entrances, not just the newly selected BC case.
    incoming = Counter(states[i][0] for i, row in enumerate(edges)
                       for child in row if states[child][0] == 0x49)
    assert incoming == {0xBC: 9, 0x47: 47}
    print('PASS COMPLETE original49 entrances:9 BC edges,47 47 edges. '
          'The47 operator imports ST0 into A; it cannot be treated as a '
          'transparent way to enter the cache-parking bridge.', flush=True)


def native_inlet_gap():
    data = json.loads(subprocess.check_output([
        'node', str(root / 'cache-reader-mode-reset-native.cjs'), '--proof-input'], text=True))
    assert data['report']['observerIndependent'] is True
    initial = data['initial']['state']['ik1302']
    a = r['concrete_primary'](initial)
    assert q['simplify'](r['ready'](a))
    mode = [initial['r'][j] for j in (2, 5)]
    assert mode == [0, 5]
    assert initial['r'][29] not in (11, 12, 13)
    assert initial['r'][29] == 10 and initial['r'][32] == 15 and initial['s1'] == 0
    print('PASS actual guarded cancelled-reader35 does NOT supply the new inlet:',
          json.dumps({'mode': mode, 'R29': initial['r'][29], 'S1': initial['s1'],
                      'R32': initial['r'][32],
                      'ready': True, 'mirror': True}), flush=True)
    # A conditional shortcut from this REAL35 is not a free dispatch8B.
    # Its mandatory45 rolls native typeF to0, closing B1 irrespective of
    # future pins/raw payload. Longer decoder routes are not excluded.
    a = r['concrete_primary'](initial)
    a.m = q['State']('restore_native35_incoming').m
    for j in raw: a.r[j] = BitVec(f'restore_native35_raw{j}', 4)
    p = w['base'](a, 0x35)
    b = w['ex'](a, 0x35, *q['arbitrary_keys']('restore_native35_shortcut_keys'))
    p.add(w['ip'](b) == 0x45); assert p.check() == sat
    for index, code in enumerate((0x45, 0x8B, 0x48)):
        w['prove'](p, w['ip'](b) == code, 'native35 shortcut forced', False)
        b = w['ex'](b, code, *q['arbitrary_keys'](f'restore_native35_decoder_keys{index}'))
    w['prove'](p, And(w['ip'](b) == 0x4A, b.r[32] == 0),
        'actual35→45→8B→48 forces4A/type0, NOT B1 or BC parking inlet; '
        'all raw6/per-tick future pins arbitrary')
    print('SCOPE: reused unchanged F/В↑ control, no new native success. '
          'All positive bridges remain detached primary contracts.', flush=True)


if __name__ == '__main__':
    inlet['immutable_reference']()
    original_return_inventory()
    be_tail_contract()
    second_restore_restores_high_mode()
    # Reuse the original paired contracts for the two deliberately
    # non-transparent operations used/ruled out by this bridge.
    w['entry46_and_exit47']()
    w['overwrite_without_read']()
    bc_cache_parking_bridge()
    operand_origin_contracts()
    native_inlet_gap()
    inlet['immutable_reference']()
