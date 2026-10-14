#!/usr/bin/env python3
"""Digit-entry 84→75→CA→DB writer: a conditional, not native, bridge.

Four native controls get as far as84 with raw6 intact, but ordinary C sign
0/9 selects85. In a detached primary-chip model, changing ONLY saved sign
ST25 toF at those native entries makes an exact header4 writer with return76.
All six payload tetras remain arbitrary. No keyboard constructor of signF,
whole-ring positive retention, Ms transfer or partial K2 is claimed.
"""
import json
from pathlib import Path
import runpy
import subprocess

from z3 import And, If, Or, UGT, ULE, sat

root = Path(__file__).resolve().parent
w = runpy.run_path(str(root / 'cache-writer-contract.py'))
q = w['q']
State, ex, base, keys = (q[n] for n in
                        ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))
ip, stack, prove, constant, number = (w[n] for n in
                                    ('address', 'stack', 'prove', 'constant', 'number'))
raw = w['positions']
eq = lambda xs, ys: And(*[x == y for x, y in zip(xs, ys)])
restore = (0x8C, 0x91, 0x92, 0x93, 0x94, 0x95, 0x98, 0x9A,
           0x93, 0x94, 0x95, 0x98, 0x9A, 0x8D)
call = (0x8F, 0x82, 0x84, 0x75, 0xCA, 0xDB)
packet = (0xDC, 0xDE, 0xD4, 0xDD, 0xD4)


def native_replays(cases):
    for case in cases:
        es = case['prefix']
        b = constant(es[0])
        for event, following in zip(es, es[1:]):
            assert number(ip(b)) == event['ip']
            b = ex(b, event['ip'], event['keyX'], event['keyY'],
                   serial_inputs=[q['N4'](v) for v in following['m']])
            for field in ('r', 'st', 'm'):
                assert [number(v) for v in getattr(b, field)] == following[field]
            for field in ('s', 's1', 'l', 't', 'carry'):
                assert number(getattr(b, field)) == following[field]
        report = case['report']
        assert report['nativeST25'] in (0, 9)
        assert report['nextAfter84'] == 0x85 and not report['nativeCall75']
        print('PASS native exact ALL primary fields:', report['fixture'],
              'ordinaryC sign', report['nativeST25'], len(es)-1,
              'macros through85; raw6 held at84; NOT75.', flush=True)


def entry_and_gates():
    a = State('digit_call_restore')
    p = base(a, 0x8C)
    p.add(ULE(a.s1, 9))
    b = a
    for j, code in enumerate(restore):
        prove(p, ip(b) == code, f'digit restore step{j}', False)
        out = []
        before = b
        b = ex(b, code, *keys(f'digit_restore_keys{j}'), emitted_outputs=out)
        prove(p, eq(out, before.m), 'digit restore no outgoing write', False)
    # The common restore swaps A into B and back. Only the restored boundary
    # claims raw6 in its original positions, not every intermediate A.
    prove(p, And(ip(b) == 0x8F, b.r[26] == a.st[25], b.s == a.r[41],
                 b.r[41] == a.r[41],
                 *[b.r[k] == a.st[k] for k in range(27, 36)],
                 eq([b.r[k] for k in raw], [a.r[k] for k in raw])),
          '8C/S1=0..9 restore reaches8F with ALL6 raw recovered, '
          'R26=oldST25, R27..35=oldST27..35 and S=oldR41')
    b = ex(b, 0x8F, *keys('digit_restore_8F_keys'))
    prove(p, And(ip(b) == If(UGT(a.st[25], a.r[41]),
                            q['BitVecVal'](0x82, 8), q['BitVecVal'](0x81, 8)),
                 b.r[26] == a.st[25],
                 eq([b.r[k] for k in raw], [a.r[k] for k in raw])),
          '8F chooses82 IFF saved signST25 > lift flagR41; '
          'else81 resets the sign before82')
    # Independent local gates make the two distinct barriers explicit.
    a = State('digit_call_81')
    p = base(a, 0x81)
    b = ex(a, 0x81, *keys('digit_call_81_keys'))
    prove(p, And(ip(b) == 0x82, b.r[26] == 0,
                 eq(b.r[0:36:3], a.r[0:36:3])),
          '81 always reaches82 but clearsR26, retainingALL12 A')
    a = State('digit_call_84')
    p = base(a, 0x84)
    out = []
    b = ex(a, 0x84, *keys('digit_call_84_keys'), emitted_outputs=out)
    prove(p, And(ip(b) == If(a.r[26] == 15, q['BitVecVal'](0x75, 8),
                            q['BitVecVal'](0x85, 8)),
                 b.r[26] == a.r[26] + q['N4'](1),
                 b.s1 == a.r[30], b.r[30] == a.s1,
                 eq([b.r[k] for k in raw], [a.r[k] for k in raw]), eq(out, a.m)),
          '84 enters75 IFF oldR26=F; allother signs select85; '
          'increment/sign wrap and A10/S1 swap leave raw6/output held')
    print('SOURCE LIMIT: the tested C9 reader suppliesST25 from ordinaryC '
          'M1[24]. Native controls construct0/9 and lift flag0, NOT signF. '
          'SignF with lift flagF would go81 and clear the neededF.', flush=True)


def run_to_dc(a, p, label):
    b = a
    for j, code in enumerate(restore + call):
        prove(p, ip(b) == code, f'{label} prefix{j}', False)
        before = b
        out = []
        b = ex(b, code, *keys(f'{label}_keys{j}'), emitted_outputs=out)
        prove(p, eq(out, before.m), f'{label} no outgoing prefix write', False)
    prove(p, And(ip(b) == 0xDC, b.r[26] == 15, stack(b)[0] == 0x76,
                 eq([b.r[k] for k in raw], [a.r[k] for k in raw])),
          f'{label}: 84→75→CA→DB reachesDC with tag76/F and ALL6 raw held', False)
    return b


def write_from_dc(a, b, p, label):
    writes = []
    for j, code in enumerate(packet):
        prove(p, ip(b) == code, f'{label} writer packet{j}', False)
        before = b
        out = []
        b = ex(b, code, *keys(f'{label}_packet_keys{j}'), emitted_outputs=out)
        if code == 0xD4:
            writes.append((out, before.m))
        else:
            prove(p, eq(out, before.m), f'{label} nonwriter holds ring', False)
    prove(p, And(ip(b) == 0x76,
                 *[writes[0][0][k+3] == a.r[k] for k in raw],
                 *[writes[1][0][k] == a.r[k] for k in raw],
                 *[out[k] == page[k] for out, page in writes
                   for k in range(42) if k % 3 != 0 or k >= 36]),
          f'{label}: all6 arbitrary raw tetras written twice in M1, '
          'M2/M3 held, returns76 notCF')


def conditional_bridge():
    a = State('digit_call_conditional')
    p = base(a, 0x8C)
    p.add(ULE(a.s1, 9), a.r[41] == 0, a.st[25] == 15,
          ULE(a.st[33], 14), a.st[35] == 5)
    b = run_to_dc(a, p, 'digit_call_conditional')
    prove(p, Or(b.r[34] == 4, b.r[34] == 5),
          'CONDITIONAL signF digit call: real selector0..E choosesDB '
          '(notDA), native reader type5 allows writerheader4/5')
    p.add(b.r[34] == 4)
    assert p.check() == sat
    write_from_dc(a, b, p, 'CONDITIONAL digit signF/header4')
    print('POSITIVE SCOPE: noEE/D6 in the local prefix; no PC00 prerequisite, '
          'no DD pre-rotation and no CE/CF inlet. This is primary-chip output '
          'only: this local proof does not construct the native signF entry '
          'or establish physical retention/cleanup. The separate full-ring '
          'audit closes a conditional exit with a further type7 hypothesis.', flush=True)


def one_missing_sign_from_native(cases):
    for j, case in enumerate(cases):
        # All metadata are the observed native digit1 entry EXCEPT ST25.
        # This assignment occurs only in Z3, never in the reference. The
        # six raw source tetras become independent symbols: 256^3 payloads.
        a = constant(case['prefix'][0])
        a.st[25] = q['N4'](15)
        for k in raw:
            a.r[k] = q['BitVec'](f'digit_call_native{j}_raw{k}', 4)
        p = base(a, 0x8C)
        label = f'digit_call_native{j}_signF_HYPOTHESIS'
        b = run_to_dc(a, p, label)
        prove(p, b.r[34] == 4,
              f'{label}: observed remaining metadata forceheader4 '
              'for ALL256^3 raw payloads, no header substitution')
        write_from_dc(a, b, p, label)
    print('MISSING BEFORE LOCAL EXPORT: only signST25=F differs from '
          'these four native metadata entries. It must be constructed '
          'without damaging the C8 reader/cache and withR41=0. '
          'This is NOT one missing step before a complete partialK2.', flush=True)


if __name__ == '__main__':
    entry_and_gates()
    conditional_bridge()
    cases = json.loads(subprocess.check_output(
        ['node', str(root / 'cache-digit-call-native.cjs'), '--proof-input'], text=True))
    native_replays(cases)
    one_missing_sign_from_native(cases)
    print('PASS digit-call bridge audit. Native controls remain negative; '
          'no native program-cache export or partialK2 is claimed.', flush=True)
