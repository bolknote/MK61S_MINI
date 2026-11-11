#!/usr/bin/env python3
"""Check exact ARM Karatsuba probes and trace the real AI exponential.

Default: offline ARM/ROM execution, not a cycle-accurate hardware simulation.
--decode-result parses a later on-device timing report without touching USB.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import statistics
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from build_m0_karatsuba_benchmark import VARIANTS


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def decode(path):
    raw = path.read_bytes()
    assert len(raw) == 40 + 4 * 88, ('report bytes', len(raw))
    h = struct.unpack_from('<10I', raw)
    assert h == (0x4b415231, 1, 125000000, 270000000, 125000000, 1, 256, 2048, 8, 0), h
    rows = []
    for i, name in enumerate(('resident',) + VARIANTS):
        values = struct.unpack_from('<IIQQ16I', raw, 40 + i * 88)
        failures, first, expected, actual = values[:4]
        assert failures == 0 and first == 0xffffffff, (name, failures, first, hex(expected), hex(actual))
        times, controls = values[4:12], values[12:20]
        samples = [(t - c) / 2048 for t, c in zip(times, controls)]
        assert min(samples) > 0, (name, 'call control exceeds measured interval')
        rows.append(dict(variant=name, microseconds_per_call=statistics.median(samples),
                         cycles_per_call=270 * statistics.median(samples),
                         samples_microseconds_per_call=samples, raw_times_us=times,
                         raw_controls_us=controls))
    return dict(status='HARDWARE_MEASURED', cpu_hz=h[3], restored_hz=h[4], rows=rows)


def check_package(base):
    metadata = json.loads((base / 'package.json').read_text())
    assert sha(metadata['resident_elf']) == metadata['resident_elf_sha256']
    assert sha(metadata['runtime_source']) == metadata['runtime_source_sha256']
    assert sha(metadata['rp2040_source']) == metadata['rp2040_source_sha256']
    assert sha(base / 'app/KARAMUL.APP') == metadata['app_sha256']
    for name, value in metadata['files'].items():
        assert sha(ROOT / name) == value, name
    for name, value in metadata['generated'].items():
        assert sha(base / name) == value, name
    return metadata


def verify(base, rom, samples):
    # Import only after --decode-result, which needs no emulator dependency.
    from native_eabi_m0_arm_self_test import Machine, nan, bits
    from check_stm32_vectors import ElfImage
    from tools.apps.packer.app_relocations import extract
    from unicorn import UC_HOOK_CODE
    from unicorn.arm_const import UC_ARM_REG_PC

    metadata = check_package(base)
    app = ElfImage(base / 'app/KARAMUL.elf')
    manifest = json.loads((base / 'app/KARAMUL.json').read_text())
    corpus = json.loads((base / 'corpus.json').read_text())
    delta = 0x20020000 - 0x20000000

    class Probe(Machine):
        def __init__(self):
            self.allowed = []
            super().__init__(metadata['resident_elf'], True, stack_bytes=16384,
                             instruction_budget=2000000, bootrom=rom)
            errno = self.call('__errno', 0, width=32)[0] & 0xffffffff
            self.allowed = [(errno, errno + 4)]

        def write(self, uc, access, address, size, value, user):
            if any(lo <= address and address + size <= hi for lo, hi in self.allowed):
                return
            return super().write(uc, access, address, size, value, user)

    m = Probe()
    image = bytearray(app.bytes_at(app.named_sections['.module_image']))
    offsets, _ = extract(base / 'app/KARAMUL.elf', 0x20000000,
                         manifest['image_bytes'], manifest['memory_bytes'])
    for offset in offsets:
        value = struct.unpack_from('<I', image, offset)[0]
        struct.pack_into('<I', image, offset, value + delta)
    m.uc.mem_write(0x20020000, bytes(image))
    output = app.symbols['m0_kara_product_words'] + delta
    m.allowed.append((output, output + 16))
    for name, address in app.symbols.items():
        if name.startswith(('m0_kara_', 'm0_product_')):
            m.elf.symbols[name] = address + delta
    variants = ('__aeabi_dmul',) + tuple('m0_kara_' + name for name in VARIANTS)
    same = lambda a, b: a == b or (nan(a) and nan(b))
    counts = Counter()
    for a, b, expected, kind in corpus['cases']:
        for name in variants:
            actual = m.call(name, a, b)[0]
            assert same(actual, expected), (name, kind, hex(a), hex(b), hex(expected), hex(actual))
        counts[kind] += 1
    print(f'ARM binary64: {len(corpus["cases"])} MPFR cases x {len(variants)} implementations PASS', flush=True)

    # Independent Python integers check all106 bits, including sticky bits
    # which might not be visible in a rounded floating-point result.
    rng = random.Random(0x53CA4A)
    values = [0, 1, 65535, 65536, (1 << 32) - 1, 1 << 32,
              (1 << 52) - 1, 1 << 52, (1 << 53) - 1]
    values += [(hi << 32) | low for hi in (1, 0xfffff, 0x100000, 0x1fffff)
               for low in (0, 1, 0xffe00000, 0xfff00000, 0xffffffff)]
    integer_pairs = [(a, b) for a in values for b in values]
    integer_pairs += [(rng.getrandbits(53), rng.getrandbits(53)) for _ in range(samples)]
    for a, b in integer_pairs:
        for variant in VARIANTS:
            m.call('m0_product_' + variant, a, b)
            actual = int.from_bytes(m.uc.mem_read(output, 16), 'little')
            assert actual == a * b, (variant, hex(a), hex(b), hex(a * b), hex(actual))
    print(f'ARM integer products: {len(integer_pairs)} complete106-bit results x3 PASS', flush=True)

    # Count the actual instructions on identical normal inputs. This is
    # deliberately NOT a physical-clock measurement or a cycles estimate.
    operations = Counter()
    decoded = {}
    def opcode(uc, address, size, unused):
        del size, unused
        if address not in decoded:
            decoded[address] = int.from_bytes(uc.mem_read(address, 2), 'little')
        if decoded[address] & 0xffc0 == 0x4340:
            operations['MULS'] += 1
    hook = m.uc.hook_add(UC_HOOK_CODE, opcode)
    instruction_rows = []
    resident_counts = []
    try:
        for name in variants:
            totals, muls = [], []
            for a, b, _, _ in corpus['cases'][:128]:
                operations.clear()
                total = m.call(name, a, b, count=True)[2]
                totals.append(total)
                muls.append(operations['MULS'])
            instruction_rows.append(dict(variant=name, mean_instructions=statistics.mean(totals),
                                         min_instructions=min(totals), max_instructions=max(totals),
                                         mean_MULS=statistics.mean(muls)))
            if name == '__aeabi_dmul':
                resident_counts = totals
            if name == 'm0_kara_baseline':
                assert totals == resident_counts, 'SRAM control is not the best resident normal kernel'
    finally:
        m.uc.hook_del(hook)

    # Trace the actual unchanged firmware. Redirect only __aeabi_dmul to
    # each private variant to determine both reachability and output parity.
    selected = [None]
    reached = Counter()
    tracked = ('__aeabi_dmul', '__aeabi_lmul', 'mk61_m0_mul_q62', 'mk61_m0_cr_exp',
               '__aeabi_f2d', '__aeabi_d2f')
    addresses = {m.elf.symbols[n] & ~1: n for n in tracked if n in m.elf.symbols}
    def trace(uc, address, size, unused):
        del size, unused
        name = addresses.get(address)
        if name:
            reached[name] += 1
            if name == '__aeabi_dmul' and selected[0]:
                uc.reg_write(UC_ARM_REG_PC, selected[0] | 1)
    hook = m.uc.hook_add(UC_HOOK_CODE, trace)
    m.uc.ctl_flush_tb()
    exp_inputs = [bits(struct.unpack('<f', struct.pack('<f', random.Random(6140 + i).uniform(-30, 8)))[0]) for i in range(128)]
    exp_inputs += [bits(x) for x in (-745., -744., -710., -104., -90., -1., -2.**-54,
                                   -2.**-55, -0., 0., 2.**-55, 2.**-54, .0007, 1., 88., 709., 710.)]
    exp_inputs += [1, (1 << 63) | 1, 0x7ff0000000000000, 0xfff0000000000000,
                   0x7ff8000000001234, 0x7ff0000000001234]
    exp_rows = []
    float_rows = []
    try:
        for i, a in enumerate(exp_inputs):
            reached.clear();selected[0] = None
            expected = m.call('mk61_m0_exp', a)[0]
            baseline_calls = dict(reached)
            candidate_calls = {}
            for variant in VARIANTS[1:]:
                selected[0] = m.elf.symbols['m0_kara_' + variant]
                reached.clear()
                actual = m.call('mk61_m0_exp', a)[0]
                assert same(actual, expected), ('exp changed', variant, hex(a), hex(expected), hex(actual))
                candidate_calls[variant] = dict(reached)
            exp_rows.append(dict(input_bits=f'{a:016x}', group='AI_like_FP32' if i < 128 else 'boundary',
                                 output_bits=f'{expected:016x}', calls=baseline_calls,
                                 redirected_calls=candidate_calls, candidate_output_matches=True))
        wrapper = '_ZN6mk61ai4math3expEf'
        if wrapper in m.elf.symbols:
            for a in exp_inputs[:128]:
                f = struct.unpack('<I', struct.pack('<f', struct.unpack('<d', struct.pack('<Q', a))[0]))[0]
                reached.clear();selected[0] = None
                expected = m.call(wrapper, f, width=32)[0] & 0xffffffff
                baseline_calls = dict(reached)
                for variant in VARIANTS[1:]:
                    selected[0] = m.elf.symbols['m0_kara_' + variant]
                    actual = m.call(wrapper, f, width=32)[0] & 0xffffffff
                    assert actual == expected, ('AI float exp changed', variant, hex(f), hex(expected), hex(actual))
                float_rows.append(dict(input_bits=f'{f:08x}', output_bits=f'{expected:08x}',
                                       calls=baseline_calls, candidate_output_matches=True))
    finally:
        m.uc.hook_del(hook)
    by_group = {}
    for group in ('AI_like_FP32', 'boundary'):
        rows = [row for row in exp_rows if row['group'] == group]
        summed = Counter()
        for row in rows:
            summed.update(row['calls'])
        by_group[group] = dict(inputs=len(rows), entry_calls=dict(summed))
    if float_rows:
        summed = Counter()
        for row in float_rows:
            summed.update(row['calls'])
        by_group['actual_AI_float_wrapper'] = dict(inputs=len(float_rows), entry_calls=dict(summed))
    print('Actual resident exp trace:', by_group, flush=True)
    result = dict(schema=1, status='HOST_ARM_PASS', physical_io=False,
                  numerical_cases_per_variant=len(corpus['cases']), strata=dict(counts),
                  exact106_bit_cases_per_variant=len(integer_pairs),
                  callee_saved_registers_and_SP_checked=True, writes_bounded=True,
                  normal_control_matches_best_resident_instruction_counts=True,
                  ROM_sha256=sha(rom), app_sha256=metadata['app_sha256'],
                  resident_elf_sha256=metadata['resident_elf_sha256'],
                  instruction_counts_are_not_physical_timings=True,
                  instruction_counts=instruction_rows, exp_profile=by_group,
                  exp_profile_details=exp_rows, AI_wrapper_details=float_rows,
                  physical_timing=None,
                  stack_high_water_bytes=0x2003fff0 - m.stack_lowest)
    (base / 'host-results.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(instruction_rows, indent=2), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package-dir', type=Path)
    parser.add_argument('--rom', type=Path, default=ROOT / 'research/rp2040-memset-2026-10-21/capture/bootrom.bin')
    parser.add_argument('--samples', type=int, default=4096)
    parser.add_argument('--decode-result', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.decode_result:
        result = decode(args.decode_result)
        if args.output:
            args.output.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2))
        return
    if not args.package_dir or not 128 <= args.samples <= 100000:
        parser.error('--package-dir and --samples128..100000 are required for ARM verification')
    verify(args.package_dir.resolve(), args.rom.resolve(), args.samples)


if __name__ == '__main__':
    main()
