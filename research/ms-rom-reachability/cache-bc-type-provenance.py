#!/usr/bin/env python3
"""Type3 provenance and its distinct flag gate, with one native K9 control.

K9 is selected from the original type0 cleanup's exact operand subtraction,
not from a keyboard enumeration. All positive source paths are conditional:
48/type3 needs incoming R23>=3 for the DIRECT4A/4B/4D→54 path. The actual K9 control has
R23=0 at this48, takes4C/4E, and cannot be promoted to a keyboard BC witness.
"""
from collections import Counter
import json
from pathlib import Path
import runpy
import subprocess
import sys

from z3 import And, If, Implies, Or, UGE, ULE

root = Path(__file__).resolve().parent
control = runpy.run_path(str(root / 'cache-bc-phase-check.py'))
source = control['source']
r, w, q = (source[n] for n in ('r', 'w', 'q'))
states, edges = (source['entry'][n] for n in ('states', 'edges'))
walk = source['walk']
N8 = lambda n: q['BitVecVal'](n, 8)


def original_type_gates():
    expected = {
        0x48: {0x8B: 857, 0x60: 19},
        0x4A: {0x48: 466},
        0x4B: {0x4A: 146},
        0x4C: {0x4A: 146, 0x4B: 126},
        0x4D: {0x4B: 126},
        0x54: {0x4D: 126, 0x5F: 156, 0x5C: 220},
    }
    assert len(states) == 52416 and sum(map(len, edges)) == 95731
    for target, parents in expected.items():
        assert Counter(states[i][0] for i, row in enumerate(edges)
            for child in row if states[child][0] == target) == parents
    for code in (0x48, 0x4A, 0x4B, 0x4C, 0x4D):
        label = f'bc_type_gate_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); out = []
        b = w['ex'](a, code, *q['arbitrary_keys'](label+'_keys'), emitted_outputs=out)
        if code == 0x48:
            claim = And(w['ip'](b) == If(ULE(a.r[32], 3), N8(0x4A), N8(0xB1)),
                w['stack'](b)[0] == 0x49, b.r[23] == a.r[23],
                b.r[32] == a.r[32], b.r[35] == a.r[35])
        elif code in (0x4A, 0x4B):
            claim = And(w['ip'](b) == If(a.r[23] == 0,
                N8(0x4C), N8(0x4B if code == 0x4A else 0x4D)),
                b.r[23] == a.r[23]-1, b.r[32] == a.r[35], b.r[35] == a.r[32])
        elif code == 0x4C:
            claim = And(w['ip'](b) == 0x4E, b.r[23] == 0,
                b.r[32] == a.r[35], b.r[35] == a.r[32])
        else:
            claim = And(w['ip'](b) == If(a.r[23] == 0, N8(0x5E), N8(0x54)),
                b.r[23] == a.r[23]-1, b.r[32] == a.r[32], b.r[35] == a.r[35])
        w['prove'](p, And(claim, b.r[29] == a.r[29], w['eq'](out, a.m)),
            f'original{code:02X}: exact type/flag/operand gate, arbitrary per-tick keys, no ring write')
    # The double swap restores the incoming type, NOT the old pending type.
    for flag, sequence, exit_code in (
            (0, (0x48, 0x4A, 0x4C), 0x4E),
            (1, (0x48, 0x4A, 0x4B, 0x4C), 0x4E),
            (2, (0x48, 0x4A, 0x4B, 0x4D), 0x5E),
            (None, (0x48, 0x4A, 0x4B, 0x4D), 0x54)):
        label = 'bc_type3_flag_'+str(flag)
        a = q['State'](label); p = w['base'](a, 0x48)
        p.add(a.r[32] == 3, a.r[29] == 6)
        p.add(UGE(a.r[23], 3) if flag is None else a.r[23] == flag)
        b = walk(a, p, sequence, label)
        w['prove'](p, And(w['ip'](b) == exit_code,
            b.r[32] == (a.r[35] if flag == 1 else q['N4'](3)),
            b.r[35] == (q['N4'](3) if flag == 1 else a.r[35]), b.r[29] == 6),
            f'CONDITIONAL48/type3/operand6/flag{flag}: exact original exit{exit_code:02X}')
    print('PASS original48/type3 needs R23>=3 for4A/4B/4D→54/type3. '
          'Flags0/1 choose4E, flag2 chooses5E. The DIRECT54 double swap restores '
          'oldR32, not pending R35; the flag1/4E path instead makes three swaps. '
          'Other54 parents are audited separately below;60→48 remains open.', flush=True)


def exact_type0_cleanup():
    a = q['State']('bc_type0_cleanup'); p = w['base'](a, 0x54)
    p.add(a.r[32] == 0, a.r[2] == 5, a.r[5] == 0, UGE(a.r[29], 3))
    b = walk(a, p, (0x54, 0x56, 0x65, 0x7B, 0xB7, 0x45, 0x8B, 0x48),
             'bc_type0_cleanup')
    w['prove'](p, And(w['ip'](b) == 0x4A, b.r[32] == 3,
        b.r[29] == a.r[29]-3, b.r[23] == 0,
        w['eq'](b.r[0:27:3], a.r[0:27:3]), w['eq'](b.st[1:36:3], a.st[1:36:3])),
        'type0/54 cleanup makes type3 and operand-3, but ALWAYS R23zero; '
        'raw A lower9 and numeric ST1 held')
    b = walk(b, p, (0x4A, 0x4C), 'bc_type0_cleanup_zero')
    w['prove'](p, And(w['ip'](b) == 0x4E, b.r[32] == 3, b.r[23] == 0),
        'numeric ST1 flag1 does NOT repair the actual control flag before4A; no second54')


def other_54_parent_cut():
    """Complete reset-region induction, not rejection of a bounded key sample.

    At5A/5B, operand bit2 can be set only in high mode; high5A exits4E.
    Low5A therefore sends only bit2-zero operands into5C. The independent
    5F induction gives operands5/7/D/F. Neither dispatcher can call54.
    """
    predecessors = {
        0x5A: {0x59: 127, 0x5B: 232, 0x5C: 220, 0x5F: 156},
        0x5B: {0x59: 127, 0x7D: 173, 0x5C: 220, 0x5F: 156},
        0x5C: {0x5A: 336, 0x5C: 220, 0x5F: 156},
        0x5F: {0x59: 127, 0x5C: 220, 0x5F: 156},
    }
    graph = r['inlet']['g']['graph']
    assert graph['metadata']['complete'] and graph['metadata']['pending'] == 0
    assert graph['metadata']['terminal'] is None
    assert all(states[i][0] == 0 for i in graph['indexes']['roots'])
    assert graph['metadata']['fusedCommands'] == {'93': ['93', '94'], '12': ['12', 'C6']}
    for target, parents in predecessors.items():
        assert Counter(states[i][0] for i, row in enumerate(edges)
            for child in row if states[child][0] == target) == parents
    for first, second in ((0x93, 0x94), (0x12, 0xC6)):
        a = q['State'](f'bc_type_fused_{first:02X}'); p = w['base'](a, first)
        b = w['ex'](a, first, *q['arbitrary_keys'](f'bc_type_fused_keys_{first:02X}'))
        w['prove'](p, w['ip'](b) == second,
            f'original fused{first:02X} internal boundary not a new5-region inlet', False)

    def invariant(a, code):
        if code in (0x5A, 0x5B): return Or(a.r[29] & 4 == 0, UGE(a.r[2], 5))
        if code == 0x5C: return a.r[29] & 4 == 0
        if code == 0x5F: return a.r[29] & 5 == 5
        return And()

    sources = sorted({code for parents in predecessors.values() for code in parents})
    assert sources == [0x59, 0x5A, 0x5B, 0x5C, 0x5F, 0x7D]
    for code in sources:
        label = f'bc_type_5_region_{code:02X}'
        a = q['State'](label); p = w['base'](a, code)
        p.add(invariant(a, code)); out = []
        b = w['ex'](a, code, *q['arbitrary_keys'](label+'_keys'), emitted_outputs=out)
        goals = [target for target, parents in predecessors.items() if code in parents]
        w['prove'](p, And(
            *[Implies(w['ip'](b) == target, invariant(b, target)) for target in goals],
            b.r[2] == a.r[2], b.r[29] == a.r[29], b.r[32] == a.r[32],
            w['eq'](out, a.m)),
            f'COMPLETE reset induction{code:02X}: ALL original outgoing5-region invariants')
    for code in (0x5C, 0x5F):
        label = f'bc_type_closed_54_parent_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); p.add(invariant(a, code))
        b = w['ex'](a, code, *q['arbitrary_keys'](label+'_keys'))
        w['prove'](p, And(w['ip'](b) != 0x54, w['ip'](b) != 0x56),
            f'ALL reset{code:02X} cannot call54 or56, unlimited keys/serial data')
    print('PASS GLOBAL RESET CUT:5C has operand bit2zero;5F has operands5/7/D/F. '
          'Neither can enter54/56 at any future key timing. ALL actual54 parents '
          'reduce to4D←4B←4A←48; hence actual54 type is the incoming48 low type0..3. '
          'For the BC bridge only type3 remains, with simultaneous48 R23>=3. '
          'The real60→48 inlet and other decoder constructors remain open.', flush=True)


def numeric_order_type_barrier():
    # Two SEPARATE original local contracts, not an invented AC→E3 edge.
    a = q['State']('bc_numeric_order_AC'); p = w['base'](a, 0xAC)
    b = w['ex'](a, 0xAC, *q['arbitrary_keys']('bc_numeric_order_AC_keys'))
    w['prove'](p, And(w['eq'](b.st[1:27:3], a.st[1:27:3]),
        w['eq'](b.st[28:36:3], a.st[29:36:3])),
        'AC preserves numeric ST1 lower9 but replaces ALL upper3/order from oldST2')
    a = q['State']('bc_numeric_order_E3'); p = w['base'](a, 0xE3)
    b = walk(a, p, (0xE3, *source['double']), 'bc_numeric_order_E3')
    w['prove'](p, And(w['ip'](b) == 0xE4,
        *[b.r[j] == a.st[j-1] for j in (2, 23, 26, 29, 32, 35)]),
        'originalE3/full91/E4 imports flag AND operand/type/pending from currentST1, '
        'not the original ordinary C order before interveningAC')
    print('PASS simple numeric-order encoding is NOT a type supplier acrossAC: '
          'flag3 can survive, while original order/type tetras are replaced. '
          'Other routes/reserves beforeAC are not excluded.', flush=True)


def native_k9_control():
    native = json.loads(subprocess.check_output([
        'node', str(root / 'cache-bc-phase-native.cjs'), '--type-proof-input'], text=True))
    report = native['report']
    assert report['keys'] == ['K', '9'] and report['operand'] == 9
    assert report['nativeKeyboardOnly'] and report['observerIndependent']
    assert report['type3Operand6At48'] and not report['nativeType3At54']
    assert report['all105Programme56Ms15OrdinaryHeld'] and not report['nativeBC']
    assert control['replay'](native, reader=True)+control['replay'](native, reader=False) == 762
    a = r['concrete_primary'](native['gate']['state']['ik1302'])
    p = w['base'](a, 0x54)
    b = walk(a, p, (0x54, 0x56, 0x65, 0x7B, 0xB7, 0x45, 0x8B), 'bc_K9_actual_cleanup')
    w['prove'](p, And(w['ip'](b) == 0x48, b.r[32] == 3, b.r[29] == 6,
        b.r[23] == 0, b.st[1] == 5, b.st[22] == 1, b.st[25] == 0),
        'actual native K9 coexists type3/operand6/numeric joint, but control R23zero')
    print(json.dumps({**report, 'consecutiveALL5Transitions': 762,
        'completeReaderSuffixEnds': [6720, 3360], 'freshUnobservedMirror': True,
        'actual48': {'command': 1134, 'slot': 'P9', 'type': 3, 'operand': 6,
            'controlR23': 0, 'numericST1': [5, 1, 0]},
        'actualExit': ['48', '4A', '4C', '4E'],
        'lateBE': {'command': 1350, 'flags': [5, 0, 0]},
        'type3OnlyHypothesisApplied': False}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    original_type_gates()
    exact_type0_cleanup()
    other_54_parent_cut()
    numeric_order_type_barrier()
    if '--source-only' not in sys.argv: native_k9_control()
    r['inlet']['immutable_reference']()
    if '--source-only' in sys.argv:
        print('PASS ALL source gates/complete reset induction/numeric-order contracts. '
              'Native controls were NOT replayed by this source-only invocation.', flush=True)
    else:
        print('PASS source gates +762 consecutive native ALL5 transitions/COMPLETE '
              '6720/3360 ends/fresh mirror. No state repair, native BC, Ms-byte '
              'copy, exchange or partialK2.', flush=True)
