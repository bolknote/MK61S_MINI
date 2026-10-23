#!/usr/bin/env python3
"""Verify the second offline math checkpoint and optional bare-ARM replay."""
from pathlib import Path
from fractions import Fraction as F
import argparse
import gzip
import hashlib
import json
import random
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
ROOT = W.parents[1]
BASE = W.parent / 'm0-math-checkpoint-20261024'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def raw(name):
    p = W / name
    return p.read_bytes() if p.exists() else gzip.decompress(p.with_suffix(p.suffix + '.gz').read_bytes())


def report(name):
    return json.loads(raw(name))


def verify(check_local):
    index = report('checkpoint.json')
    assert sha((BASE / 'checkpoint.json').read_bytes()) == index['base_checkpoint_sha256']
    base = json.loads((BASE / 'checkpoint.json').read_bytes())
    for name, digest in base['files'].items():
        assert sha((BASE / name).read_bytes()) == digest, name
    for name, digest in index['files'].items():
        assert sha((W / name).read_bytes()) == digest, name
    provenance = report('provenance.json')
    for entry in provenance['archived_files']:
        data = (W / entry['path']).read_bytes()
        assert sha(data) == entry['sha256']
        data = gzip.decompress(data) if entry['encoding'] == 'gzip' else data
        assert len(data) == entry['uncompressed_bytes']
        assert sha(data) == entry['uncompressed_sha256'], entry['path']
        if check_local:
            assert (ROOT / entry['source']).read_bytes() == data, entry['source']
    for name, digest in index['review_pins'].items():
        assert sha(raw('reviews/' + name + '/FINAL-REVIEW.json')) == digest
        assert report('reviews/' + name + '/FINAL-REVIEW.json')['blockers'] == []
    for name, count in [('int64-to-double', 30222), ('sqrt-cold', 15136), ('atan-packing', 58276)]:
        q = report('deltas/' + name + '/qualification.json')
        assert q['cases'] == len(q['rows']) == count
        for row in q['rows']:
            if name == 'int64-to-double':
                assert row['outputs']['candidate'] == row['outputs']['parent'] == row['expected']
            else:
                assert row['correct']['candidate'] and row['correct']['parent']
                assert row['outputs']['candidate'] == row['outputs']['parent']
            if row.get('profiled', True):
                assert row['instructions']['candidate'] <= row['instructions']['parent']
    prefix = 'wip/atan-residual/'
    status = report(prefix + 'checkpoint-status.json')
    helper = report(prefix + 'helper-proof.json')
    build_info = report(prefix + 'candidate-build.json')
    assert status['status'].startswith('WIP_') and not status['full_public_qualification']
    assert helper['source_sha256'] == build_info['source_include_sha256'] == sha(raw(prefix + 'native_eabi_m0_atan_fast.inc'))
    assert helper['candidate_ELF_sha256'] == build_info['ELF_sha256'] == status['candidate_ELF_sha256']
    assert helper['ARM_calls'] == 30408 and helper['all_bounded_quotients_0_to_33_covered']
    probe = report(prefix + 'probe.json')['rows']
    assert len(probe) == 27 and all(r['outputs']['candidate'] == r['expected'] for r in probe)
    assert status['remaining_probe_slower_correct_Qfplib'] == 2
    return dict(archive_files=len(index['files']), original_artifacts=len(provenance['archived_files']),
                preceding_checkpoint_files=len(base['files']), independent_receipts=4,
                local_originals_checked=check_local, prototype_qualified=False)


def build(output, toolchain):
    output = output.resolve()
    assert W != output and W not in output.parents
    assert BASE != output and BASE not in output.parents
    output.mkdir(parents=True, exist_ok=False)
    includes = BASE / 'baseline-v164/source/code'
    commands, hashes = [], {}

    def run(args):
        commands.append([str(a) for a in args])
        subprocess.run(commands[-1], check=True)

    for name, source_dir in [('int64-to-double', 'deltas/int64-to-double'),
                             ('sqrt-cold', 'deltas/sqrt-cold'),
                             ('atan-packing', 'deltas/atan-packing'),
                             ('atan-residual', 'wip/atan-residual')]:
        source, target = W / source_dir, output / name
        target.mkdir()
        flags = ['-mcpu=cortex-m0plus', '-mthumb', '-mfloat-abi=soft',
                 '-DMK61_USE_M0_EABI=1', '-DMK61_M0_RP2040_EABI=1']
        if name == 'int64-to-double':
            for filename in ('candidate.S', 'candidate.ld'):
                shutil.copyfile(source / filename, target / filename)
            run([toolchain / 'arm-none-eabi-gcc', *flags, '-c', target / 'candidate.S', '-o', target / 'candidate.o'])
            objects = [target / 'candidate.o']
        elif name == 'sqrt-cold':
            for filename in ('native_eabi_m0.S', 'native_eabi_m0_rp2040.S',
                             'native_eabi_m0_sqrt_special.S.inc', 'candidate.ld'):
                shutil.copyfile(source / filename, target / filename)
            objects = []
            for filename, obj in [('native_eabi_m0.S', 'main.o'), ('native_eabi_m0_rp2040.S', 'rp.o')]:
                run([toolchain / 'arm-none-eabi-gcc', *flags, '-I', includes, '-c', target / filename, '-o', target / obj])
                objects.append(target / obj)
        else:
            for filename in ('native_eabi_m0.cpp', 'native_eabi_m0_atan.inc', 'native_eabi_m0_atan_fast.inc', 'candidate.ld'):
                shutil.copyfile(source / filename, target / filename)
            run([toolchain / 'arm-none-eabi-g++', *flags, '-Os', '-std=gnu++17',
                 '-fno-exceptions', '-fno-rtti', '-fno-unwind-tables', '-fno-use-cxa-atexit',
                 '-ffunction-sections', '-fdata-sections', '-fno-lto', '-I', includes,
                 '-I', W / 'support/includes',
                 '-c', target / 'native_eabi_m0.cpp', '-o', target / 'candidate-full.o'])
            objects = [target / 'candidate-full.o']
        entry = ['--gc-sections', '-e', 'mk61_m0_atan'] if name.startswith('atan-') else []
        run([toolchain / 'arm-none-eabi-ld', *entry, '-T', target / 'candidate.ld', *objects, '-o', target / 'candidate.elf'])
        saved = report(source_dir + ('/candidate-build.json' if name.startswith('atan-') else '/build.json'))
        expected = saved.get('candidate_ELF_sha256', saved.get('ELF_sha256'))
        actual = sha((target / 'candidate.elf').read_bytes())
        assert actual == expected, (name, actual, expected)
        hashes[name] = actual
    (output / 'build-commands.json').write_text(json.dumps(commands, indent=2) + '\n')
    return output, hashes


def replay(output):
    sys.path.insert(0, str(BASE / 'support'))
    sys.path.insert(0, str(BASE / 'support/support'))
    import ctypes as C
    import struct
    from native_eabi_m0_arm_self_test import Machine, SP
    from m0_mpfr_oracle import Oracle, _Number
    from oracles import round_ratio, integer_sqrt, equal
    from check_stm32_vectors import ElfImage

    oracle = Oracle()
    lib = oracle.lib
    assert C.sizeof(C.c_long) == C.sizeof(C.c_ulong) == 8
    lib.mpfr_set_si.argtypes = [C.POINTER(_Number), C.c_long, C.c_int]
    lib.mpfr_set_ui.argtypes = [C.POINTER(_Number), C.c_ulong, C.c_int]
    number = _Number()
    lib.mpfr_init2(C.byref(number), 64)
    states = (bytes(28), struct.pack('<7I', 17, 3, 17, 3, 5, 2, 3))
    machine = Machine(output / 'int64-to-double/candidate.elf', True, stack_bytes=32)
    conversions = report('deltas/int64-to-double/qualification.json')['rows']
    try:
        for i, row in enumerate(conversions):
            op, raw_input = row['operation'], int(row['x'], 16)
            width, signed = {'l2d': (64, True), 'ul2d': (64, False), 'i2d': (32, True), 'ui2d': (32, False)}[op]
            value = raw_input - (1 << width) if signed and raw_input >> (width - 1) else raw_input
            expected = round_ratio(abs(value), 1, 0, 64, value < 0)
            (lib.mpfr_set_si if signed else lib.mpfr_set_ui)(C.byref(number), value, 0)
            assert struct.unpack('<Q', struct.pack('<d', lib.mpfr_get_d(C.byref(number), 0)))[0] == expected
            state = states[i % 2]
            machine.uc.mem_write(0xd0000060, state)
            got, _, count = machine.call('__aeabi_' + op, raw_input, count=True)
            assert got == expected == int(row['outputs']['candidate'], 16)
            assert count == row['instructions']['candidate']
            assert bytes(machine.uc.mem_read(0xd0000060, 28)) == state
        assert SP - machine.stack_lowest == 0
    finally:
        lib.mpfr_clear(C.byref(number))
    root = Machine(output / 'sqrt-cold/candidate.elf', True, stack_bytes=32)
    roots = report('deltas/sqrt-cold/qualification.json')['rows']
    for i, row in enumerate(roots):
        raw_input = int(row['x'], 16)
        expected = integer_sqrt(raw_input, 64)
        assert equal(expected, oracle.reference('sqrt', raw_input), 64)
        state = states[i % 2]
        root.uc.mem_write(0xd0000060, state)
        got, _, count = root.call('mk61_m0_sqrt', raw_input, count=True)
        assert equal(got, expected, 64) and got == int(row['outputs']['candidate'], 16)
        assert count == row['instructions']['candidate']
        assert bytes(root.uc.mem_read(0xd0000060, 28)) == state
    assert SP - root.stack_lowest == 28
    # Exercise only the new helper: no resident firmware or ROM is mapped.
    image = ElfImage(output / 'atan-residual/candidate.elf')
    names = [n for n in image.symbols if n.startswith('atan_fast_tail_repair')]
    assert len(names) == 1
    helper = Machine(output / 'atan-residual/candidate.elf', True, stack_bytes=128)
    helper.elf.symbols['repair_helper'] = image.symbols[names[0]]
    pairs = set()
    for bit in range(59, 65):
        for d in ((1 << bit) - 1, 1 << bit, (1 << bit) + 1):
            if (1 << 59) <= d < (1 << 64):
                for n in (0, 1, 3, d // 4, d // 2 - 1, d // 2):
                    pairs.add((n, d))
    rng = random.Random(0xA7A6DE17)
    for _ in range(1024):
        d = rng.randrange(1 << 59, 1 << 64)
        pairs.add((rng.randrange(d // 2 + 1), d))
    digest, calls, quotients = hashlib.sha256(), 0, set()
    states = (struct.pack('<7I', 0, 0, 0, 0, 0, 0, 1), states[1])
    for i, (n, d) in enumerate(sorted(pairs)):
        H = F(n << 64, d)
        floor = H.numerator // H.denominator
        for offset in range(-32, 34) if i < 128 else (-32, -31, -1, 0, 1, 31, 32, 33):
            h = floor + offset
            if h < 0 or h >= (1 << 63) or abs(F(h) - H) >= 33:
                continue
            for si, state in enumerate(states):
                helper.uc.mem_write(0xd0000060, state)
                got = helper.call('repair_helper', n, d, c=h)[0] & 0xffffffff
                delta = got - (1 << 32) if got >> 31 else got
                residual = (n << 64) - h * d
                q = (abs(residual) >> 38) // (d >> 38)
                assert delta == (-q if residual < 0 else q)
                assert abs(F(delta) - (H - h)) < 1 + F(34, 1 << 20)
                assert abs(delta) <= 33
                assert bytes(helper.uc.mem_read(0xd0000060, 28)) == state
                digest.update(struct.pack('<QQQiB', n, d, h, delta, si))
                quotients.add(abs(delta))
                calls += 1
    saved = report('wip/atan-residual/helper-proof.json')
    assert calls == saved['ARM_calls'] == 30408 and quotients == set(range(34))
    assert digest.hexdigest() == saved['digest_sha256']
    assert SP - helper.stack_lowest == saved['observed_stack_bytes'] == 80
    return dict(fresh_conversion_calls=len(conversions), fresh_sqrt_calls=len(roots),
                profiled_counts_reproduced=len(conversions) + len(roots),
                fresh_residual_helper_calls=calls, residual_transcript_sha256=digest.hexdigest(),
                fresh_candidate_ARM_calls=len(conversions) + len(roots) + calls,
                MPFR_version=oracle.version, firmware_or_ROM_mapped=False,
                public_atan_or_Qfplib_replayed=False, whole_library_replayed=False,
                hardware_accessed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-local', action='store_true')
    parser.add_argument('--build-output', type=Path)
    parser.add_argument('--toolchain', type=Path)
    parser.add_argument('--replay', action='store_true')
    args = parser.parse_args()
    if args.replay and args.build_output is None:
        parser.error('--replay requires --build-output')
    result = {'status': 'PASS_INTERMEDIATE_RESEARCH_CHECKPOINT', **verify(args.check_local)}
    if args.build_output:
        tc = args.toolchain
        if tc is None:
            compiler = shutil.which('arm-none-eabi-gcc')
            if compiler is None:
                parser.error('Specify --toolchain /path/to/arm-none-eabi/bin')
            tc = Path(compiler).parent
        output, result['rebuilt_ELF_hashes'] = build(args.build_output, tc)
        if args.replay:
            result['replay'] = replay(output)
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
