"""One-bank self-extracting sum of cubes with a 22-byte tail generator.

The calculator constructs 0F through mantissa XOR, then executes the real
seven-operation sum-of-cubes formula. Its instruction packets occupy three
7-byte numeric words, skipping numeric metadata through jumps. This is a
useful execution/representation probe, not profitable compression: the
original calculator program is only seven bytes long (49 bytes of UTF-8).
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'tools/elite'))
from assembler import Assembler, pack_number

BANK = 24
GENERATOR = bytes.fromhex(
    '49 6a 6b 39 40 6c 41 6d 42 0d 43 44 45 46 47 48 '
    '55 56 55 69 51 01')
EXPECTED = bytes.fromhex('00 22 0f 51 85 00 00')
EXPECTED += pack_number(15510210)
EXPECTED += pack_number(99502213)
EXPECTED += bytes(42)

GENERATOR_F0 = bytes.fromhex(
    '49 6a 41 6b 42 6c 6d 39 43 6e 44 0d 40 45 46 47 48 '
    '55 56 55 69 51 08')
EXPECTED_F0 = pack_number(0) + pack_number(15516922) + pack_number(22510210)
EXPECTED_F0 += bytes.fromhex('00 13 f0 51 88 00 00')
EXPECTED_F0 += pack_number(99995022) + bytes(28)


def probe(n, runner, dark=False):
    asm = Assembler()
    main = asm.module(0, 'seed and input driver')
    main.raw(0x2F, 0x50, 0x2F, 0x2A)
    seeds = [('A', 85510722), ('B', 80000800), ('C', 15510210), ('D', 99502213)]
    generator, expected_code, bridge_address, bridge = GENERATOR, EXPECTED, 85, '51 08'
    if dark:
        seeds = [('A', 15516922), ('B', 22510210), ('C', 88517013),
                 ('D', 80008000), ('E', 99995022)]
        generator, expected_code = GENERATOR_F0, EXPECTED_F0
        bridge_address, bridge = 88, '51 29'
    for reg, value in seeds:
        main.set(reg, value)
    main.n(n).op('stop').far(0x51, BANK * 112 + 63)
    banks, info = asm.link()
    image = bytearray(32 * 112)
    for bank, code in banks.items():
        image[bank * 112:(bank + 1) * 112] = code
    assert not any(image[BANK * 112:BANK * 112 + 63])
    image[BANK * 112 + 63:BANK * 112 + 63 + len(generator)] = generator
    image[BANK * 112 + bridge_address:BANK * 112 + bridge_address + 2] = bytes.fromhex(bridge)
    if dark:
        assert 0xF0 not in image
    folder = HERE / f'{"dark_f0" if dark else "cubes"}_{n}'
    folder.mkdir(exist_ok=True)
    lines = ['reinit']
    lines += [f'hin {bank * 112:04d} {image[bank * 112:(bank + 1) * 112].hex()}'
              for bank in range(32)]
    lines.append('run')
    (folder / 'autoexec.m61').write_text('\n'.join(lines) + '\n')
    (folder / 'initial.raw').write_bytes(image)
    result = subprocess.run([str(runner), str(folder)], input='dump\nrun\n',
                            text=True, capture_output=True, check=True, timeout=30,
                            env={**os.environ, 'ELITE_TRACE': '1'})
    initial, state = [json.loads(line) for line in result.stdout.splitlines()]
    assert initial['output_code'][0] == bytes(63).hex(), initial
    assert not state['running'] and not state['error'], state
    assert state['output_code'][0] == expected_code.hex(), state
    expected = sum(k ** 3 for k in range(1, n + 1))
    assert state['x'] == expected, (n, expected, state)
    generated_opcode = 'f0' if dark else 'f'
    assert re.search(rf' op={generated_opcode} ', result.stderr), result.stderr
    if n == 10:
        (folder / 'trace.txt').write_text(result.stderr)
    (folder / 'result.json').write_text(json.dumps(state, indent=2) + '\n')
    return dict(n=n, dark_f0=dark, sum_cubes=state['x'], generator_bytes=len(generator),
                branch_bridge_bytes=2, register_seed_bytes=len(seeds) * 7,
                output_block_bytes=len(expected_code),
                calculator_formula_bytes=7,
                generated_packet_bytes=28 if dark else 21)


if __name__ == '__main__':
    runner = Path(sys.argv[1]).resolve()
    report = [probe(n, runner, dark) for dark in [False, True] for n in range(101)]
    (HERE / 'sum_cubes_report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(cases=len(report), samples=[case for case in report
          if case['n'] in (0, 10, 100)]), indent=2))
