#!/usr/bin/env python3
"""Can unused m4 mantissa fields hold a payload on the existing indirect-A path?

Detached original-ROM semantics only. This does not create a carrier with keys,
prove physical entry reachability, or establish a 23-word-preserving Ms writer.
Each tested field is universally decimal (0..9), not a key-sequence search.
"""
import argparse
import json
import runpy
from pathlib import Path

from z3 import And, BitVec, ULE, sat, unsat

h = runpy.run_path(str(Path(__file__).with_name('k1-p0-carrier-indirect-check.py')))
State, execute, base, keys = (h[n] for n in ('State', 'ex', 'base', 'keys'))
address, stack, accumulator, same, tetras, slots = (
    h[n] for n in ('address', 'stack', 'A', 'same', 'tet', 'slots'))
SEQUENCE = ([0xD6] + [0x2F, 0x20] * 3 + [0x2F, 0x21, 0x23, 0x25]
            + [1] * 3 + [2] * 11
            + [3, 4, 0xBA, 0xCB, 0xDD, 0xD4, 0x26, 0x28, 0x7E, 0x71, 0xAA]
            + [0xE5] * 3 + [0xE6, 0xED, 0xEE, 0xAB, 0xAD, 0xA4]
            + [1] * 9 + [2, 3, 4, 0xBA, 0xCB, 0xDD, 0xD4])


def check(fields, timeout_ms=15000):
    label = 'payload_' + ('_'.join(map(str, fields)) or 'baseline')
    pages = [State(label + '_page_' + str(i)).m for i in range(len(SEQUENCE) + 1)]
    initial = State(label)
    initial.m = pages[0]
    solver = base(initial, 0xD6)
    solver.set(timeout=timeout_ms)
    carrier = tetras('0040F0000000')
    payload = {i: BitVec(label + '_digit_' + str(i), 4) for i in fields}
    for i, digit in payload.items():
        carrier[i] = digit
        solver.add(ULE(digit, 9))
    solver.add(initial.r[29] == 11, initial.r[32] == 10,
               initial.r[35] == 1, initial.r[26] == 15, initial.s1 == 6,
               *[v == n for v, n in zip(stack(initial), [0x2F, 0xAC, 0x9A])],
               *[pages[0][3 * j] == v for j, v in enumerate(carrier)])
    names = [slots[(7 + i) % 15] for i in range(len(SEQUENCE) + 1)]
    for i, ip in enumerate(SEQUENCE):
        if ip in (1, 0xE5):
            solver.add(pages[i][22] == 15 if names[i] in ('marker', 'Z', 'T')
                       else pages[i][22] != 15)
    assert solver.check() == sat, 'nonempty entry required'

    def prove(claim, stage, expression=None):
        solver.push()
        solver.add(~claim)
        result = solver.check()
        failure = None
        if result == sat:
            model = solver.model()
            concrete = [model.eval(v, model_completion=True).as_long()
                        if hasattr(v, 'sort') else v for v in carrier]
            failure = dict(status='COUNTEREXAMPLE', stage=stage,
                           carrier=''.join(format(v, 'X') for v in reversed(concrete)),
                           payload={i: model.eval(v, model_completion=True).as_long()
                                    for i, v in payload.items()})
            if expression is not None:
                failure['actual'] = model.eval(expression, model_completion=True).as_long()
        elif result != unsat:
            failure = dict(status='UNKNOWN', stage=stage, reason=solver.reason_unknown())
        solver.pop()
        return failure

    state = initial
    normalized = source = None
    normalized_is_old_literal = None
    writes = []
    for i, ip in enumerate(SEQUENCE):
        stage = '%02d %02X(%s)' % (i, ip, names[i])
        failed = prove(address(state) == ip, stage + ' next IP', address(state))
        if failed:
            return dict(fields=fields, **failed)
        if ip == 0xEE:
            assert names[i] == 'X'
            source = [pages[i][1 + 3 * j] for j in range(12)]
        out = []
        state = execute(state, ip, *keys(label + '_keys_' + str(i)),
                        serial_inputs=pages[i + 1], emitted_outputs=out)
        if ip == 0x25:
            # The transformed payload need not equal the old literal m4.
            normalized = accumulator(state)
            literal_failure = prove(same(normalized, tetras('0070000F0000')),
                                    stage + ' normalization discards payload')
            normalized_is_old_literal = (True if literal_failure is None else
                                         None if literal_failure['status'] == 'UNKNOWN' else False)
            failed = prove(And(state.s1 == 4, stack(state)[0] == 0x26),
                           stage + ' carrier return fields')
        elif ip == 0x71:
            failed = prove(And(state.r[30] == 0, state.r[33] == 4),
                           stage + ' reconstructed STORE0', h['byte'](state.r[30], state.r[33]))
        if failed:
            return dict(fields=fields, **failed)
        if ip == 0xD4:
            writes.append(names[i])
            expected = source if source is not None else normalized
            assert expected is not None
            invariant = And(*[out[3 * j] == v for j, v in enumerate(expected)],
                            *[out[j] == pages[i][j] for j in range(42)
                              if j % 3 != 0 or j >= 36])
        else:
            invariant = same(out, pages[i])
        failed = prove(invariant, stage + ' exact ring effects')
        if failed:
            return dict(fields=fields, **failed)
        if source is not None and ip not in (0xDD, 0xD4):
            failed = prove(same(accumulator(state), source), stage + ' arbitrary p held')
            if failed:
                return dict(fields=fields, **failed)
    assert writes == ['U', 'U']
    failed = prove(address(state) == 0xA5, 'finite A5 return', address(state))
    return dict(fields=fields, **failed) if failed else dict(
        fields=fields, status='PASS', commands=len(SEQUENCE),
        writes='D4(P0=transformed carrier), D4(P0=arbitrary p)',
        normalizedCarrierAlwaysOldLiteral=normalized_is_old_literal,
        otherTetrasHeld=True, limit='conditional entry, not a keyboard Ms writer')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fields', help='comma separated low-to-high mantissa fields 0..6')
    args = parser.parse_args()
    sets = [[int(v) for v in args.fields.split(',')]] if args.fields else (
        [[]] + [[i] for i in range(7)] + [[0, 1, 2], list(range(7))])
    for fields in sets:
        assert len(set(fields)) == len(fields) and all(0 <= i <= 6 for i in fields)
        print(json.dumps(check(fields), sort_keys=True), flush=True)
