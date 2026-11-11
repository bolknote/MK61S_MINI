#!/usr/bin/env python3
"""Build private ARMv6-M Karatsuba probes; never access or flash a device."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle, bits
from tools.firmware.picocalc.build_picocalc import compiler_bin

VARIANTS = ('baseline', 'difference', 'sum_guarded')
MASK52 = (1 << 52) - 1


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def operands(samples):
    """Distinct carry, normalization, ties, subnormal and nonfinite strata."""
    rng = random.Random(0xCA4A6140)
    normal = []
    for _ in range(128):
        pair = tuple((rng.randrange(2) << 63) | (rng.randrange(1020, 1027) << 52)
                     | rng.getrandbits(52) for _ in range(2))
        normal.append(pair)
    edges = [0, 1 << 63, 1, 2, (1 << 52) - 1, 1 << 52, (1 << 52) + 1,
             bits(.5), bits(1.), bits(-1.), bits(2.), bits(1. + 2.**-26),
             0x7FEFFFFFFFFFFFFF, 0xFFEFFFFFFFFFFFFF, 0x7FF0000000000000,
             0xFFF0000000000000, 0x7FF0000000000001, 0x7FF8000000001234]
    special = [(a, b) for a in edges for b in edges]
    pairs = [(a, b, 'normal') for a, b in normal]
    # Keep on-device validation small enough for the existing APP arena.
    pairs += [(a, b, 'edge') for a, b in random.Random(6140).sample(special, 128)]
    pairs += [(a, b, 'edge') for a, b in special]
    for exponent in (1, 2, 511, 1022, 1023, 1024, 1534, 2045, 2046):
        for ah in (0, 1, 0x7FFFF, 0xFFFFF):
            for al in (0, 1, 0xFFFEFFFF, 0xFFF00000, 0xFFFFFFFF):
                a = (exponent << 52) | (ah << 32) | al
                b = (1023 << 52) | (rng.getrandbits(20) << 32) | rng.getrandbits(32)
                pairs.extend(((a, b, 'carry'), (b, a, 'carry')))
    # These products have exactly half an ULP in their discarded52-bit tail;
    # perturb one operand to exercise either side and both result signs.
    for p in range(1, 51):
        a, b = (1023 << 52) | (1 << p), (1023 << 52) | (1 << (51 - p))
        for delta in (-1, 0, 1):
            pairs.extend(((a + delta, b, 'rounding'),
                          ((a + delta) ^ (1 << 63), b, 'rounding')))
    pairs += [(rng.getrandbits(64), rng.getrandbits(64), 'random') for _ in range(samples)]
    return pairs


def assembly(runtime, rp2040, slow_address):
    source = runtime.read_text()
    macro = source[source.index('.macro product32\n'):source.index('.endm', source.index('.macro product32\n')) + 6]
    body = source.split('function __aeabi_dmul\n', 1)[1].split('end __aeabi_dmul', 1)[0]
    first = body.index(' product32                    // low*low')
    last = body.index(' ldr r4, [sp,#16]', first)
    product = body[first:last]
    assert product.count(' product32') == 4
    rp = rp2040.read_text()
    def extract_macro(name):
        begin = rp.index('.macro ' + name)
        assert rp[begin + len('.macro ' + name)].isspace()
        return rp[begin:rp.index('.endm', begin) + 6]
    shipped = rp[rp.index('.Lrp_mul_short_b:'):rp.index('\n.ltorg', rp.index('.Lrp_mul_short:'))]
    begin = shipped.index(' push {r0-r2,r6}', shipped.index('.Lrp_mul_general:'))
    end = shipped.index('.Lrp_mul_pack:', begin)
    shipped_prefix, shipped_product, shipped_suffix = shipped[:begin], shipped[begin:end], shipped[end:]
    assert shipped_product.count(' mul32_32_64 ') == 4
    shipped_prefix = shipped_prefix.replace(' bl mk61_m0_dmul_slow', f' ldr r7, ={slow_address:#x}\n blx r7')
    license_text = rp[:rp.index('#if defined(MK61_USE_M0_EABI)')]
    output = [license_text, '.syntax unified\n.cpu cortex-m0plus\n.thumb\n', macro,
              extract_macro('mul_unpack_normal'), extract_macro('mul32_32_64'),
              '.macro baseline_product53\n' + product + '.endm\n',
              (ROOT / 'tests/fixtures/m0_karatsuba_blocks.inc').read_text()]
    for variant in VARIANTS:
        name = 'm0_kara_' + variant
        block = ' baseline_product53\n' if variant == 'baseline' else ' kara_' + variant + '\n'
        replacement = shipped_product if variant == 'baseline' else ''' sub sp,#44
 str r0,[sp,#0]
 str r1,[sp,#4]
 str r2,[sp,#8]
 str r3,[sp,#12]
 str r6,[sp,#16]
''' + block + ''' mov r5,r3
 mov r6,r0
 mov r7,r2
 ldr r3,[sp,#16]
 add sp,#44
'''
        text = (shipped_prefix + replacement + shipped_suffix).replace('.Lrp_mul_', '.L' + name + '_')
        text = text.replace(' regular_func __aeabi_dmul',
                            f' .global {name}\n .type {name},%function\n .thumb_func\n{name}:')
        output.append(f'.section .text.{name},"ax",%progbits\n{text}\n.ltorg\n.size {name},.-{name}\n')
        raw = 'm0_product_' + variant
        output.append(f'''.section .text.{raw},"ax",%progbits
.global {raw}
.type {raw},%function
.thumb_func
{raw}:
 push {{r4-r7,lr}}
 sub sp,#44
 str r0,[sp,#0]
 str r1,[sp,#4]
 str r2,[sp,#8]
 str r3,[sp,#12]
{block} ldr r4,=m0_kara_product_words
 mov r5,r12
 str r5,[r4,#0]
 str r3,[r4,#4]
 str r0,[r4,#8]
 str r2,[r4,#12]
 add sp,#44
 pop {{r4-r7,pc}}
 .ltorg
.size {raw},.-{raw}
''')
    output.append('''.section .bss.m0_kara_product_words,"aw",%nobits
.balign 4
.global m0_kara_product_words
m0_kara_product_words: .space 16
.section .note.GNU-stack,"",%progbits
''')
    return '\n'.join(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resident-elf', type=Path, required=True)
    parser.add_argument('--runtime-source', type=Path, default=ROOT / 'code/native_eabi_m0.S')
    parser.add_argument('--rp2040-source', type=Path, default=ROOT / 'code/native_eabi_m0_rp2040.S')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--toolchain', type=Path)
    parser.add_argument('--samples', type=int, default=4096)
    args = parser.parse_args()
    if not 128 <= args.samples <= 100000:
        parser.error('--samples must be128..100000')
    elf, runtime, rp2040, out = (args.resident_elf.resolve(), args.runtime_source.resolve(),
                               args.rp2040_source.resolve(), args.output_dir.resolve())
    out.mkdir(parents=True, exist_ok=True)
    image = ElfImage(elf)
    for symbol in ('__aeabi_dmul', 'mk61_m0_dmul_slow', 'mk61_m0_exp'):
        if symbol not in image.symbols:
            parser.error('resident symbol missing: ' + symbol)
    tc = compiler_bin(args.toolchain)
    symbols = {}
    for line in subprocess.check_output([str(tc / 'arm-none-eabi-nm'), '--defined-only', '--demangle', str(elf)], text=True).splitlines():
        fields = line.split(None, 2)
        if len(fields) == 3:
            symbols[fields[2]] = int(fields[0], 16) | 1
    def find(prefix):
        values = [value for name, value in symbols.items() if name.startswith(prefix)]
        if len(set(values)) != 1:
            raise ValueError('resident clock symbol is ambiguous: ' + prefix)
        return values[0]
    oracle = Oracle()
    cases = [[a, b, oracle.reference('dmul', a, b), kind] for a, b, kind in operands(args.samples)]
    corpus = dict(schema=1, seed='0xca4a6140', oracle='MPFR directed interval RNE',
                  mpfr_version=oracle.version, on_device_cases=256, timing_cases=128, cases=cases)
    (out / 'corpus.json').write_text(json.dumps(corpus, indent=2) + '\n')
    generated = out / 'variants.S'
    generated.write_text(assembly(runtime, rp2040, image.symbols['mk61_m0_dmul_slow'] | 1))
    footer = image.named_sections['.mk61_fw_footer']
    words = struct.unpack('<10I', image.bytes_at(footer))
    header = ['#pragma once', '#include <cstdint>',
              'struct KaraPair {std::uint64_t a,b,expected;};',
              'static const KaraPair kara_pairs[]={']
    header += ['{' + ','.join(f'0x{x:016x}ULL' for x in row[:3]) + '},' for row in cases[:256]]
    header += ['};', 'static constexpr unsigned KaraCases=256,KaraTimeCases=128;',
               f'static constexpr std::uint32_t resident_dmul={image.symbols["__aeabi_dmul"] | 1:#x}U;',
               f'static constexpr std::uint32_t clock_hz_function={find("picocalc::ai_clock::hz("):#x}U;',
               f'static constexpr std::uint32_t clock_begin_function={find("picocalc::ai_clock::begin("):#x}U;',
               f'static constexpr std::uint32_t clock_end_function={find("picocalc::ai_clock::restore("):#x}U;',
               f'static constexpr std::uint32_t footer_address={footer[3]:#x}U;',
               'static constexpr std::uint32_t footer_words[]={' + ','.join(f'{x:#x}U' for x in words) + '};']
    (out / 'karatsuba-inputs.hpp').write_text('\n'.join(header) + '\n')
    command = [sys.executable, str(ROOT / 'tools/apps/portable/build_portable_app.py'),
               '--target', 'picocalc-pico-h', '--shared-runtime', '--name', 'KARAMUL',
               '--source', str(ROOT / 'tests/fixtures/m0_karatsuba_benchmark.cpp'),
               '--source', str(generated), '--include', str(out), '--arm-toolchain-bin', str(tc),
               '--output-dir', str(out / 'app')]
    with (out / 'build.log').open('w') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    app = out / 'app/KARAMUL.APP'
    metadata = dict(schema=1, status='BUILT_NOT_RUN_ON_DEVICE', resident_elf=str(elf),
                    resident_elf_sha256=sha(elf), runtime_source=str(runtime),
                    runtime_source_sha256=sha(runtime), rp2040_source=str(rp2040),
                    rp2040_source_sha256=sha(rp2040), variants=list(VARIANTS),
                    app_sha256=sha(app), app_bytes=app.stat().st_size,
                    output_file='KARAOUT.BIN', cpu_hz=270000000, rounds=8, calls=2048,
                    timing='microsecond timer; equal ABI loop control; rotated order',
                    footprint='private APP; no global arithmetic/firmware patch',
                    files={str(p.relative_to(ROOT)): sha(p) for p in
                           (Path(__file__).resolve(), ROOT / 'tests/fixtures/m0_karatsuba_blocks.inc',
                            ROOT / 'tests/fixtures/m0_karatsuba_benchmark.cpp')})
    metadata['generated'] = {name: sha(out / name) for name in
                             ('variants.S', 'corpus.json', 'karatsuba-inputs.hpp',
                              'app/KARAMUL.elf', 'app/KARAMUL.json')}
    (out / 'package.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(f'Built {app}: {app.stat().st_size} bytes; {len(cases)} MPFR cases; no device I/O.')


if __name__ == '__main__':
    main()
