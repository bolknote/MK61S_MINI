#!/usr/bin/env python3
"""Build the exact-image Pico H pow timing APP or verify its saved RESULT.bin."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys

from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'dev/lib'), str(ROOT / 'ports/picocalc')]
from seal_picocalc import BASE, FOOTER, verify
from tools.firmware.picocalc.build_picocalc import TARGET, compiler_bin
from uf2 import validate

SYS_HZ = 125_000_000
TIMEOUT_MS = 8000
DIRECTORY = '/MK61S-POW-WDT'
HEADER = struct.Struct('<8I')
SAMPLE = struct.Struct('<QQ12IQ')
MAX_SUBNORMAL = 0x000FFFFFFFFFFFFF
ONE = 0x3FF0000000000000
Y_AT_DENOMINATOR_LIMIT = 0x3BFFFFFFFFFFFFFF
VECTORS = (
    # name, x, y, lower encoding of the adjacent pair, expected stage mask
    ('even_lower_tie', 0x4008000000000000, 0x4041000000000000, 0x434D9FE779881944, 7),
    ('maximum_products_inverse_first', MAX_SUBNORMAL, Y_AT_DENOMINATOR_LIMIT | (1 << 63), ONE, 3),
    ('published_near_midpoint', 0x0F1234687B59D4F7, 0x3C3101A6C819D38D, 0x3FEFFFFFFFFFFFFB, 3),
    ('exp_endpoint_work', 0x3FFFFFFFFFFFFFFF, 0xC03F800000000000, 0x3DF6A09E667F3BE3, 7),
    ('maximum_products_positive', MAX_SUBNORMAL, Y_AT_DENOMINATOR_LIMIT, ONE-1, 3),
    ('maximum_products_inverse_repeat_1', MAX_SUBNORMAL, Y_AT_DENOMINATOR_LIMIT | (1 << 63), ONE, 3),
    ('maximum_products_inverse_repeat_2', MAX_SUBNORMAL, Y_AT_DENOMINATOR_LIMIT | (1 << 63), ONE, 3),
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path):
    return json.loads(path.read_bytes())


def build_app(args):
    firmware = args.production.resolve()
    elf_path = firmware / (TARGET + '.elf')
    bin_path = firmware / (TARGET + '.bin')
    uf2_path = firmware / (TARGET + '.uf2')
    manifest = load_json(firmware / 'manifest.json')
    image = bin_path.read_bytes()
    assert manifest['profile'] == 'picocalc-pico-h' and manifest['arithmetic_runtime'] == 'owned-m0'
    assert len(image) == manifest['flash_bytes'] and sha(bin_path) == manifest['bin_sha256']
    assert sha(uf2_path) == manifest['uf2_sha256']
    integrity = manifest['firmware_integrity']
    footer_offset = integrity['footer_offset']
    assert verify(image, footer_offset) == integrity
    validate(uf2_path.read_bytes(), image)
    elf = ElfImage(elf_path)
    for kind, offset, _, load, size, _, _, _ in elf.segments:
        if kind == 1 and size:
            assert BASE <= load and load+size <= BASE+len(image)
            assert image[load-BASE:load-BASE+size] == elf.data[offset:offset+size], 'ELF/BIN mismatch'

    functions = dict(POW_FIXED512='FixedILj512EE8evaluateEyyRy',
                     POW_FIXED1024='FixedILj1024EE8evaluateEyyRy',
                     POW_EXACT='mk61_m0_pow_exact_small',
                     POW_BOUNDS4096='PowerBoundsILj256EE4sideEyyy',
                     POW_FEED='diagnostics13feed_watchdogEv',
                     POW_CLOCK_HZ='clock_get_hz')
    objects = dict(POW_WDT_STATE='diagnostics12_GLOBAL__N_18watchdogE',
                   POW_WDT_LAST_FEED='diagnostics12_GLOBAL__N_19last_feedE',
                   POW_FW_FOOTER='mk61_picocalc_firmware_footer')
    bindings = {}
    for key, suffix in (functions | objects).items():
        (symbol,) = (name for name in elf.symbols if name.endswith(suffix) and elf.sizes[name])
        address, size = elf.symbols[symbol], elf.sizes[symbol]
        if key in functions:
            assert BASE <= (address & ~1) < BASE+len(image) and size > 1
            address |= 1
        elif key == 'POW_FW_FOOTER':
            assert address == BASE+footer_offset and size == FOOTER.size
        else:
            assert 0x20000000 <= address < 0x20038000 and address % 4 == 0
            assert size == (24 if key == 'POW_WDT_STATE' else 8)
        bindings[key] = dict(symbol=symbol, address=address, size=size)

    out = args.output.resolve()
    out.mkdir(parents=True)
    source = out / 'POWWDT.c'
    shutil.copy2(ROOT / 'tests/fixtures/m0_pow_watchdog_benchmark.c', source)
    constants = [f'#define {name} 0x{binding["address"]:08x}U' for name, binding in bindings.items()]
    words = struct.unpack_from('<10I', image, footer_offset)
    constants.append('#define POW_FOOTER_WORDS ' + ','.join(f'0x{word:08x}U' for word in words))
    constants.append('#define POW_BUILD_ID 0x' + manifest['build_id'] + 'U')
    (out / 'pow_locations.h').write_text('\n'.join(constants) + '\n')

    oracle = Oracle()
    rows = []
    input_bytes = bytearray(struct.pack('<4I', 0x50574937, 1, len(VECTORS), 0))
    for name, x, y, lower, mask in VECTORS:
        expected = oracle.reference('pow', x, y)
        assert expected in (lower, lower+1)
        rows.append(dict(name=name, x=x, y=y, lower=lower, expected=expected, accepted=mask))
        input_bytes.extend(struct.pack('<4Q', x, y, lower, expected))
    inputs = out / 'INPUT.bin'
    inputs.write_bytes(input_bytes)
    command = [sys.executable, '-B', str(ROOT / 'tools/apps/portable/build_portable_app.py'),
               '--target', 'picocalc-pico-h', '--name', 'POWWDT', '--source', str(source),
               '--shared-runtime', '--arm-toolchain-bin', str(compiler_bin(args.toolchain)),
               '--output-dir', str(out / 'app')]
    with (out / 'app-build.log').open('x') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    metadata = dict(firmware=manifest, elf_sha256=sha(elf_path), bindings=bindings, rows=rows,
                    mpfr=oracle.version, directory=DIRECTORY, input_sha256=sha(inputs),
                    app_sha256=sha(out / 'app/POWWDT.APP'))
    (out / 'benchmark.json').write_text(json.dumps(metadata, indent=2) + '\n')


def decode(raw, metadata):
    rows = metadata['rows']
    assert len(raw) == HEADER.size + len(rows)*SAMPLE.size
    header = HEADER.unpack_from(raw)
    assert header == (0x50575237, 1, int(metadata['firmware']['build_id'], 16),
                      len(rows), TIMEOUT_MS, 0, 0xffffffff, 0), header
    samples = []
    for row, packet in zip(rows, SAMPLE.iter_unpack(raw[HEADER.size:])):
        (before, after, before_count, after_count, inside_count, us512, us1024, exact, us4096,
         total, mask, side_bits, hz_before, hz_after, rounded) = packet
        side = side_bits - (1 << 32) if side_bits & (1 << 31) else side_bits
        gap = after-before
        assert TIMEOUT_MS*1000 > gap >= total >= 10_000
        assert before_count == inside_count and after_count == before_count+1
        assert total == us512+us1024+exact+us4096 and hz_before == hz_after == SYS_HZ
        assert mask == row['accepted'] and rounded == row['expected']
        assert side == (1 if rounded > row['lower'] else -1)
        samples.append(dict(name=row['name'], step512_us=us512, step1024_us=us1024, exact_us=exact,
                            step4096_us=us4096, chain_us=total, watchdog_gap_us=gap,
                            watchdog_margin_us=TIMEOUT_MS*1000-gap, before_count=before_count,
                            in_timing_count=inside_count, after_count=after_count, side=side,
                            rounded=f'{rounded:016x}'))
    return samples


def main():
    if sys.flags.optimize:
        raise SystemExit('Benchmark checks require Python assertions')
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest='mode', required=True)
    prepare = modes.add_parser('prepare')
    prepare.add_argument('--production', required=True, type=Path)
    prepare.add_argument('--output', required=True, type=Path)
    prepare.add_argument('--toolchain', type=Path)
    check = modes.add_parser('verify')
    check.add_argument('--benchmark', required=True, type=Path)
    check.add_argument('--result', required=True, type=Path)
    args = parser.parse_args()
    if args.mode == 'prepare':
        build_app(args)
    else:
        print(json.dumps(decode(args.result.read_bytes(), load_json(args.benchmark)), indent=2))


if __name__ == '__main__':
    main()
