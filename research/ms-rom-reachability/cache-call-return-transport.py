#!/usr/bin/env python3
"""Original return74, its input-flag gate, and distinct C7/C8/C9 data lanes.

Positive claims here are universal PRIMARY ROM contracts, not keyboard
inlets. Original73 itself pushes74; no free return address is inserted.
Frozen reset coverage is used only after its source/metadata audit. C9 is
an exchange with programme M3, but incoming A-cache is NOT its source.
"""
from collections import Counter
from pathlib import Path
import runpy

from z3 import And, If, sat

root = Path(__file__).resolve().parent
old = runpy.run_path(str(root / 'cache-decoder-source-contract.py'))
r, w, q = old['r'], old['w'], old['q']
states, edges, raw = old['states'], old['edges'], w['raw']
walk = old['old']['walk']


def original_returns():
    assert Counter(s[1][0] for s in states if s[0] == 0x62) == {0x6E: 14, 0x74: 15}
    assert Counter(s[1][0] for s in states if s[0] == 0x6F) == {0x6E: 14, 0x74: 107}
    assert Counter(states[i][0] for i, row in enumerate(edges)
        for child in row if states[child][0] == 0x62) == {0x6F: 121}
    assert Counter(states[i][0] for i, row in enumerate(edges)
        for child in row if states[child][0] == 0x6F) == {0x6D: 29, 0x73: 181}
    a = q['State']('call73_exact_gate'); p = w['base'](a, 0x73); out = []
    b = w['ex'](a, 0x73, *q['arbitrary_keys']('call73_gate_keys'), emitted_outputs=out)
    pc_zero = And(a.r[31] == 0, a.r[34] == 0)
    w['prove'](p, And(w['ip'](b) == If(pc_zero, q['BitVecVal'](0x75, 8),
        q['BitVecVal'](0x6F, 8)), w['stack'](b)[0] == 0x74,
        b.r[38] == a.r[38], b.r[23] == a.r[23],
        *[b.r[j] == a.r[j] for j in raw], w['eq'](out, a.m)),
        '73 exact PC00 gate/push74; holds selector/input flag/raw6; no outgoing copy')
    for flag_zero in (True, False):
        label = 'call73_return74_'+str(flag_zero)
        a = q['State'](label); p = w['base'](a, 0x73)
        p.add(~And(a.r[31] == 0, a.r[34] == 0),
              a.r[23] == 0 if flag_zero else a.r[23] != 0)
        b = walk(a, p, (0x73, 0x6F, 0x62, 0x74, 0x86, 0xD3), label)
        w['prove'](p, And(w['ip'](b) == (0xD5 if flag_zero else 0x63),
            b.r[26] == 0, b.r[23] == a.r[23],
            *[b.r[j] == a.r[j] for j in raw]),
            'original73/6F/62/74/86/D3: raw6 held, counter cleared; '
            + ('flag0 forcesD5' if flag_zero else 'nonzero flag forces63'))
    a = q['State']('call_D3_flag_gate'); p = w['base'](a, 0xD3)
    b = w['ex'](a, 0xD3, *q['arbitrary_keys']('call_D3_flag_gate_keys'))
    w['prove'](p, And(w['ip'](b) == If(a.r[23] == 0,
        q['BitVecVal'](0xD5, 8), q['BitVecVal'](0x63, 8)),
        b.r[23] == a.r[23], b.r[26] == a.r[26],
        *[b.r[j] == a.r[j] for j in raw]),
        'D3 dispatches ONLY by R23 input flag, NOT PC or cache digitA9')
    print('PASS complete62 return inventory:6E/74; exact original73 alternate '
          'return is genuine, but needs a native inlet with the cache. '
          'The nonzero flag branch is NOT a keyboard witness.', flush=True)


def distinct_exchange_lanes():
    for code in (0xC7, 0xC8, 0xC9):
        label = f'call_exchange_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); out = []
        b = w['ex'](a, code, *q['arbitrary_keys'](label+'_keys'), emitted_outputs=out)
        if code == 0xC7:
            claim = And(w['eq'](b.r[0:36:3], a.m[1:36:3]),
                w['eq'](out[1:36:3], a.r[0:36:3]),
                w['eq'](b.r[1:42:3], a.r[1:42:3]),
                *[out[j] == a.m[j] for j in range(42) if j % 3 != 1 or j >= 36])
        elif code == 0xC8:
            claim = And(w['eq'](b.r[1:42:3], a.m[1:42:3]),
                w['eq'](b.r[0:36:3], a.r[0:36:3]),
                w['eq'](out, a.m))
        else:
            claim = And(w['eq'](b.r[1:42:3], a.m[2:42:3]),
                w['eq'](out[2:42:3], a.r[1:42:3]),
                w['eq'](b.r[0:36:3], a.r[0:36:3]),
                *[out[j] == a.m[j] for j in range(42) if j % 3 != 2])
        w['prove'](p, claim, f'{code:02X} exact source/destination, including service boundaries')
    # This region can carry A unchanged while it formats/writes a DIFFERENT
    # B buffer. Holding A is not equivalent to exporting A at its writer.
    for code in (0x63, 0x64, 0x66, 0x67, 0x6A, 0x6B, 0xCC, 0xCD):
        a = q['State'](f'call_formatter_hold_{code:02X}'); p = w['base'](a, code); out = []
        b = w['ex'](a, code, *q['arbitrary_keys'](f'call_formatter_keys_{code:02X}'),
                    emitted_outputs=out)
        w['prove'](p, And(w['eq'](b.r[0:36:3], a.r[0:36:3]), w['eq'](out, a.m)),
            f'{code:02X} holds A12 and makes no outgoing write', False)
    a = q['State']('call_C9_paired'); other = a.copy()
    for j in raw: other.r[j] = q['BitVec'](f'call_C9_other_raw{j}', 4)
    pins = q['arbitrary_keys']('call_C9_paired_keys'); serial = q['State']('call_C9_serial').m
    left_out, right_out = [], []
    left = w['ex'](a, 0xC9, *pins, serial_inputs=serial, emitted_outputs=left_out)
    right = w['ex'](other, 0xC9, *pins, serial_inputs=serial, emitted_outputs=right_out)
    p = w['base'](a, 0xC9)
    w['prove'](p, And(w['eq'](left_out, right_out), w['ip'](left) == w['ip'](right),
        *[left.r[j] == right.r[j] for j in range(42) if j not in raw],
        w['eq'](left.st, right.st), w['eq'](left.m, right.m),
        *[getattr(left, n) == getattr(right, n) for n in ('s', 's1', 'l', 't', 'carry')],
        *[left.r[j] == a.r[j] for j in raw],
        *[right.r[j] == other.r[j] for j in raw]),
        'C9 does NOT export six independent incoming A tetras; holds them in A, exchanges B14/M3')
    p.push(); p.add(*[a.r[j] != other.r[j] for j in raw]); assert p.check() == sat; p.pop()
    heads = Counter(s[1][0] for s in states if s[0] == 0xC9)
    assert heads == {0x67: 61, 0x06: 85}
    assert Counter(states[i][0] for i, row in enumerate(edges)
        for child in row if states[child][0] == 0xC9) == {0xCD: 492}
    print('PASS C9 reset cover:146 contexts, original heads67/06, sourceCD. '
          'C9 writes all14 programme tetras, including two B service tetras; '
          'NOT an Ms store. C7 exchanges12 A/M2; C8 reads ALL14 M2/B. '
          'Need a real A-to-B transfer/inlet and preservation of displaced data '
          'and services for partialK2. Local algebra is NOT a composable key recipe.', flush=True)


def local_page_exchange_equations():
    """Relational DATA composition, deliberately NOT a control-flow walk.

    Three independent legal entry states have their own original IPs and
    unrelated return stacks. Only DATA edges between the fragments are
    assumed. The required actual transports, physical pages and controller
    entry/exit are explicit unresolved obligations, not state repairs.
    """
    read = q['State']('page_equations_read_C8')
    exchange = q['State']('page_equations_exchange_C9')
    store = q['State']('page_equations_store_BB')
    p = w['base'](read, 0xC8)
    p.add(*w['base'](exchange, 0xC9).assertions(),
          *w['base'](store, 0xBB).assertions())
    read_out, exchange_out, preload_out, store_out = [], [], [], []
    loaded = w['ex'](read, 0xC8, *q['arbitrary_keys']('page_equations_read_keys'),
                     emitted_outputs=read_out)
    exchanged = w['ex'](exchange, 0xC9,
        *q['arbitrary_keys']('page_equations_exchange_keys'), emitted_outputs=exchange_out)
    preloaded = w['ex'](store, 0xBB,
        *q['arbitrary_keys']('page_equations_preload_keys'), emitted_outputs=preload_out)
    w['prove'](p, And(w['ip'](preloaded) == 0xBC, w['eq'](preload_out, store.m)),
               'original BB really preloads/rotates B and forces BC, no outgoing write')
    stored = w['ex'](preloaded, 0xBC,
        *q['arbitrary_keys']('page_equations_store_keys'), emitted_outputs=store_out)
    # Assumptions are lossless B14 data transport between three FRAGMENTS,
    # NOT dispatch equality or a claimed original C8→C9→BB path.
    p.add(w['eq'](exchange.r[1:42:3], loaded.r[1:42:3]),
          w['eq'](store.r[1:42:3], exchanged.r[1:42:3]))
    ms_before, program_before = read.m[1:42:3], exchange.m[2:42:3]
    assert len(ms_before) == len(program_before) == 14
    w['prove'](p, And(w['eq'](read_out, read.m),
        w['eq'](exchange_out[2:42:3], ms_before),
        w['eq'](store_out[1:42:3], program_before),
        w['eq'](loaded.r[0:36:3], read.r[0:36:3]),
        w['eq'](exchanged.r[0:36:3], exchange.r[0:36:3]),
        w['eq'](stored.r[0:36:3], store.r[0:36:3]),
        *[exchange_out[j] == exchange.m[j] for j in range(42) if j % 3 != 2],
        *[store_out[j] == preloaded.m[j] for j in range(42) if j % 3 != 1]),
        'DATA EQUATIONS ONLY: C8 ; C9 ; original BB/BC would swap ALL14 tetras '
        '(7 raw bytes) of M2/programme if both B14 transports exist; '
        'M2 is Ms ONLY at the corresponding physical slot')
    # All28 tetras are independent, including the two extra/service tetras.
    p.push(); p.add(*[a != b for a, b in zip(ms_before, program_before)])
    assert p.check() == sat; p.pop()
    a = q['State']('page_equations_decoder48'); d = w['base'](a, 0x48); out = []
    b = w['ex'](a, 0x48, *q['arbitrary_keys']('page_equations_decoder48_keys'),
                emitted_outputs=out)
    w['prove'](d, And(b.r[37] == 15, b.r[40] == 10,
        w['eq'](b.r[1:36:3], a.r[1:36:3]), w['eq'](out, a.m)),
        'ordinary48 sets B service pair AF; holds numeric B12 but NOT opaque B14')
    print('LIMIT: this is a four-ROM-word DATA specification, not four executable '
          'instructions. Need native C8→C9 and C9→BB transports, correct physical '
          'Ms/programme pages and a safe exit. C9 returns67/06, not BB; '
          'ordinary48 overwrites the seventh byte in B services. No native '
          '7-byte exchange, repeatability, eight-page loop or partialK2 claimed.', flush=True)


def c8_original_return_boundary():
    # The completed C8-inclusive reset controller allows no C8 head other
    # than6E. Verify the exact packet at arbitrary legal primary inputs.
    assert Counter(s[1][0] for s in states if s[0] == 0xC8) == {0x6E: 19}
    a = q['State']('page_original_C8'); p = w['base'](a, 0xC8)
    p.add(w['stack'](a)[0] == 0x6E)
    b = walk(a, p, (0xC8, 0x6E, 0x61), 'page_original_C8')
    w['prove'](p, And(w['eq'](b.r[1:30:3], a.m[1:30:3]),
        b.r[37] == 8, b.r[40] == 2,
        q['Or'](w['ip'](b) == 0x3A, w['ip'](b) == 0x63)),
        'original C8/6E/61 holds first10 M2 tetras in B (5 bytes), '
        'sets B services28 and cannot jump directly toC9')
    a = q['State']('page_return_service_pair'); other = a.copy()
    other.r[37] = q['BitVec']('page_return_other_B12', 4)
    other.r[40] = q['BitVec']('page_return_other_B13', 4)
    p = w['base'](a, 0x6E); left, right = a, other
    for i, code in enumerate((0x6E, 0x61)):
        w['prove'](p, And(w['ip'](left) == code, w['ip'](right) == code),
                   'original C8 continuation forced service-loss stage', False)
        pins = q['arbitrary_keys'](f'page_return_pair_keys{i}')
        serial = q['State'](f'page_return_pair_serial{i}').m
        lo, ro = [], []; before_l, before_r = left, right
        left = w['ex'](left, code, *pins, serial_inputs=serial, emitted_outputs=lo)
        right = w['ex'](right, code, *pins, serial_inputs=serial, emitted_outputs=ro)
        w['prove'](p, And(w['eq'](lo, before_l.m), w['eq'](ro, before_r.m),
            w['eq'](lo, ro)), '6E/61 makes no new outgoing copy of B service data', False)
    w['prove'](p, And(
        *[w['eq'](getattr(left, n), getattr(right, n)) for n in ('r', 'st', 'm')],
        *[getattr(left, n) == getattr(right, n) for n in ('s', 's1', 'l', 't', 'carry')]),
        '6E/61 locally forgets ALL independent B12/B13 service data in primary state/output')
    p.push(); p.add(a.r[37] != other.r[37], a.r[40] != other.r[40])
    assert p.check() == sat; p.pop()
    print('LIMIT: the original physical M2/Ms still holds those two tetras. '
          'No global information-loss/fullK2 theorem follows. A prior reserve '
          'or reread may recover them; B10/B11 also change in6E. The five '
          'held bytes are a local buffer fact, NOT a native Ms-to-programme copy.', flush=True)


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    original_returns()
    distinct_exchange_lanes()
    local_page_exchange_equations()
    c8_original_return_boundary()
    r['inlet']['immutable_reference']()
