"""Self-extracting Grundy S=10, through calculator opcodes and K1/K2.

This is a representation/compression experiment, not a new firmware codec.
The original 49-byte listing cannot be treated as ordinary numeric words.
The alternate layout generates four displayed replies and uses resident
control flow. One numeric seed derives four reply words; embedded scale
literals construct the other two nonzero words that supply digit prefixes.
Two code-word service bytes also encode the second reply's digit prefix;
they are retained from the initial decoder by 56 55 56 55.
The catalogue listing has one rule-breaking digit: 5311 -> 33221 has eleven
objects. Both the reference and extracted variant repair it to 33211.

Run with the experimental real-core runner:
  PYTHONDONTWRITEBYTECODE=1 python3 grandi.py ../ms-selfextract-rle-2026-09-30/core_runner
"""
from decimal import Decimal
from itertools import product
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'tools/elite'))
from assembler import Assembler

BANK = 24
SEEDS = [('A', 500103060)]
DECODER = bytes.fromhex(
    '8e 49 6a 40 09 09 00 11 41 01 00 05 00 11 43 45 '
    '0d 46 47 01 0c 03 00 42 01 0c 01 00 12 44 0d 48 00 '
    '02 02 02 01 01 01 01 4d 51 63')
TAIL = bytes.fromhex(
    '56 55 56 55 07 01 4e 69 49 08 04 40 69 08 02 11 5e 01 51 08 '
    '49 09 08 40 69 05 03 01 01 11 5e 34 51 20 '
    '6d 0e 00 50 51 71')
assert len(DECODER) == 43 and len(TAIL) == 40
assert DECODER[21] == 3 and DECODER[35] == 2


def pack(value):
    d = Decimal(str(value))
    if not d:
        return bytes(7)
    _, digits, scale = abs(d).normalize().as_tuple()
    exponent = len(digits) + scale - 1
    assert 0 <= exponent <= 99 and len(digits) <= 8
    t = list(map(int, ''.join(map(str, digits)).ljust(8, '0')[::-1]))
    t += [9 if d < 0 else 0, exponent % 10, exponent // 10, 0, 0, 0]
    return bytes((t[h] << 4) | t[h - 1] for h in (13, 1, 3, 5, 7, 9, 11))


def expected_head():
    words = [500103060, 500102070, '1e30', 500101020, '1e40', 500101020, 0, 0, 0]
    code = bytearray(b''.join(pack(n) for n in words))
    initial = DECODER + bytes(63 - len(DECODER))
    for i in range(0, 63, 7):
        code[i] = initial[i]
    return bytes(code)


def original():
    # Include the zero target operand omitted after the listing's final BP.
    raw = bytearray((HERE / 'original.raw').read_bytes())
    assert len(raw) == 49 and raw[26] == 2
    raw[26] = 1  # 33221 -> 33211; both reference and candidate are repaired.
    return bytes(raw)


def image(n, reference=False):
    a = Assembler()
    main = a.module(0, 'register setup and input driver')
    if not reference:
        for r, v in SEEDS:
            # Nine integer digits cannot be keyed as one native mantissa.
            # Both seeds have a trailing zero: enter eight digits and VP 1.
            main.raw(*map(int, str(v // 10)), 0x0c, 1).st(r)
        # Initial B24:00 enters the decoder through RE=1. After extraction
        # RE=71 makes the same byte support the usual VO restart key.
        main.raw(1).st('E')
    main.n(n).op('stop').far(0x51, BANK * 112)
    banks, info = a.link()
    raw = bytearray(32 * 112)
    for b, data in banks.items():
        raw[b * 112:(b + 1) * 112] = data
    if reference:
        code = original()
    else:
        code = DECODER + bytes(63 - len(DECODER)) + TAIL
    raw[BANK * 112:BANK * 112 + len(code)] = code
    return raw, info


def run(runner, n, inputs=(), reference=False, trace=False, restart=False):
    name = ('vo_' if restart else '') + '_'.join(map(str, [n, *inputs]))
    folder = HERE / ('reference' if reference else 'selfextract') / name
    folder.mkdir(parents=True, exist_ok=True)
    raw, info = image(n, reference)
    lines = ['reinit']
    lines += [f'hin {b * 112:04d} {raw[b * 112:(b + 1) * 112].hex()}'
              for b in (0, BANK)]
    lines.append('run')
    (folder / 'autoexec.m61').write_text('\n'.join(lines) + '\n')
    (folder / 'initial.raw').write_bytes(raw)
    commands = 'dump\nrun\n' + ''.join(
        f'{"restart" if restart and i == 2 else "input"} {v}\n'
        for i, v in enumerate(inputs))
    env = {**os.environ}
    if trace:
        env['ELITE_TRACE'] = '1'
    else:
        env.pop('ELITE_TRACE', None)
    result = subprocess.run([str(runner), str(folder)], input=commands,
                            text=True, capture_output=True, check=True, timeout=30, env=env)
    states = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(states) == len(inputs) + 2, result.stdout
    for s in states:
        assert not s['running'] and not s['error'], (folder, s)
        assert s['auto_display'] and not s['segmented'], (folder, s)
    if not reference:
        assert states[0]['output_code'][0] == raw[BANK * 112:BANK * 112 + 63].hex()
        for s in states[1:]:
            assert s['output_code'][0] == expected_head().hex(), (folder, s)
            assert s['output_tail'][0] == states[0]['output_tail'][0], (folder, s)
    if trace:
        swaps = [line.split(' op=')[1].split()[0] for line in result.stderr.splitlines()
                 if ' op=55 ' in line or ' op=56 ' in line]
        assert swaps == ['56', '55', '56', '55'], swaps
        (folder / 'trace.txt').write_text(result.stderr)
    (folder / 'results.json').write_text(json.dumps(states, indent=2) + '\n')
    return states


def parts(n):
    return tuple(sorted(map(int, str(n)), reverse=True))


def splits(p):
    return {tuple(sorted(p[:i] + p[i + 1:] + (k, pile - k), reverse=True))
            for i, pile in enumerate(p) for k in range(1, (pile + 1) // 2)}


def as_number(p):
    return int(''.join(map(str, p)))


def legal_parties():
    out = []
    for first in (91, 82, 73, 64):
        cpu1 = 721 if first == 82 else 631
        assert parts(cpu1) in splits(parts(first))
        for second_parts in sorted(splits(parts(cpu1))):
            second = as_number(second_parts)
            cpu2 = 33211 if second == 5311 else 42211
            assert parts(cpu2) in splits(second_parts)
            for third_parts in sorted(splits(parts(cpu2))):
                assert parts(2221111) in splits(third_parts)
                assert all(p <= 2 for p in parts(2221111))
                out.append((first, second, as_number(third_parts)))
    assert len(out) == 12, out
    return out


def compare(runner, first, second, restart):
    n, p, q = first
    moves = (p, q, *second)
    ref = run(runner, n, moves, reference=True, restart=restart)
    trace = first == second == (82, 4321, 322111) and not restart
    got = run(runner, n, moves, trace=trace, restart=restart)
    projection = lambda s: [s['x'], s['y'], s['regs'][9]]
    assert [projection(s) for s in got[1:]] == [projection(s) for s in ref[1:]], (first, second, restart, got, ref)
    for end in (3, 6):
        assert got[end]['x'] == 0 and got[end]['y'] == 2221111, got[end]
    return dict(first_party=first, next_party=second, vo_restart=restart,
                outputs=[projection(s) for s in got[1:]])


if __name__ == '__main__':
    runner = Path(sys.argv[1]).resolve()
    parties = legal_parties()
    cases = [compare(runner, p, q, restart)
             for restart in (False, True) for p, q in product(parties, repeat=2)]
    raw, info = image(82)
    _, reference_info = image(82, reference=True)
    driver_bytes = next(b['used'] for b in info['banks'].values())
    reference_driver_bytes = next(b['used'] for b in reference_info['banks'].values())
    setup_bytes = driver_bytes - reference_driver_bytes
    kernel = len(DECODER) + len(TAIL)
    report = dict(original_program_bytes=len(original()), decoder_bytes=len(DECODER),
                  resident_tail_bytes=len(TAIL), numeric_seed=SEEDS,
                  native_setup_bytes=setup_bytes,
                  program_plus_native_setup_bytes=kernel + setup_bytes,
                  full_driver_and_program_bytes=driver_bytes + kernel,
                  reference_driver_and_program_bytes=reference_driver_bytes + len(original()),
                  output_exchange_bytes=63, generated_nonzero_numeric_words=6,
                  seed_representation_bytes=7, legal_parties=len(parties),
                  reference_repair=dict(address=26, old_opcode='02', new_opcode='01',
                                        reason='5311 -> 33211 preserves ten objects'),
                  scenarios=len(cases), checked_game_stops=sum(len(c['outputs']) for c in cases),
                  cases=cases)
    (HERE / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    (HERE / 'autoexec.m61').write_text('\n'.join(['reinit'] + [
        f'hin {b * 112:04d} {raw[b * 112:(b + 1) * 112].hex()}' for b in (0, BANK)] + ['run']) + '\n')
    (HERE / 'grandi-selfextract.m61').write_text((HERE / 'autoexec.m61').read_text())
    (HERE / 'initial.raw').write_bytes(raw)
    (HERE / 'reference-fixed.raw').write_bytes(original())
    (HERE / 'expanded-head.raw').write_bytes(expected_head())
    (HERE / 'expanded-bank.raw').write_bytes(expected_head() + TAIL + bytes(49 - len(TAIL)))
    print(json.dumps({k: v for k, v in report.items() if k != 'cases'}, indent=2))
