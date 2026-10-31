#!/usr/bin/env python3
"""Actual ARM 4096-step tests of all result bits at all repeated positions."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'tests')]
from build_picocalc import compiler_bin
from native_eabi_m0_arm_self_test import Machine, SP

MASK = 0xFFFFFFFF
V2 = ROOT / '.build/rp2040-interpolator-20261023/packet-v2'
V2_SHA = '849885aa360bf83cd45f21163a3079ba37b78c34fcd4dd9e822bea32197eccf0'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def oracle(flip=0, position=7):
    state = 0
    for index in range(4096):
        lane = index % 32
        low = (lane * 0x1234567 + 0x7654321) & MASK
        high = (lane * 2654435761) & MASK
        if lane == position:
            low ^= flip & MASK
            high ^= flip >> 32
        state = ((state ^ low) * 16777619) & MASK
        state ^= state >> 16
        state = ((state ^ high) * 16777619) & MASK
        state ^= state >> 16
        state = (state + index) & MASK
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source_hashes = {name: sha(HERE / name) for name in ('checksum-probe.cpp', 'kernels.h', 'checksum-self-test.py')}
    tc = compiler_bin(None)
    elf = output / 'checksum.elf'
    command = [str(tc / 'arm-none-eabi-g++'), '-mcpu=cortex-m0plus', '-mthumb', '-mfloat-abi=soft',
               '-Os', '-fno-lto', '-fno-builtin', '-fno-exceptions', '-fno-rtti', '-std=c++17',
               '-ffunction-sections', '-fdata-sections', '-nostdlib', '-I' + str(HERE),
               '-Wl,-Ttext=0x20000000', '-Wl,-e,checksum_stream_v3',
               str(HERE / 'checksum-probe.cpp'), '-o', str(elf)]
    subprocess.run(command, check=True)
    assert sha(V2 / 'packet-manifest.json') == V2_SHA
    v2_files = json.loads((V2 / 'packet-manifest.json').read_text())['files']
    old_elf = V2 / 'protocol/alu/fixture.elf'
    assert sha(old_elf) == v2_files['protocol/alu/fixture.elf']['sha256']
    old = Machine(old_elf, rp2040=True)
    old_rows = []
    for flip in (0, 1, 0x80000000):
        got = old.call('checksum_probe', flip)[0] & MASK
        old_rows.append(dict(flip=f'{flip:08X}', checksum=f'{got:08X}', actual_ARM=True))
    assert [row['checksum'] for row in old_rows] == ['586F7800', 'F4B8F800', '586F7800']
    machine = Machine(elf)
    baseline = machine.call('checksum_stream_v3', 0, 7)[0]
    assert baseline == oracle()
    rows = []
    digest = hashlib.sha256()
    for word in range(2):
        for position in range(32):
            for bit in range(32):
                flip = 1 << (word * 32 + bit)
                got = machine.call('checksum_stream_v3', flip, position)[0]
                assert got == oracle(flip, position), (word, position, bit, hex(got))
                assert got != baseline, ('Undetected repeated bit error', word, position, bit)
                digest.update(struct.pack('<4I', word, position, bit, got))
                rows.append(dict(word=word, position=position, bit=bit, checksum=f'{got:08X}'))
            print(f'PASS word={word} position={position} bits=32 repeats=128', flush=True)
    profiles = {}
    for name in ('checksum_step_v2_formula', 'checksum_step_v3'):
        profiles[name] = []
        for value, state, index in ((0, 0, 0), (0x8000000080000000, 0xFFFFFFFF, 4095), (0x123456789ABCDEF0, 0x76543210, 123)):
            got, _, count = machine.call(name, value, state | (index << 32), count=True)
            profiles[name].append(dict(value=f'{value:016X}', state=f'{state:08X}', index=index,
                                       result=f'{got:08X}', ARM_instructions=count))
    for name, digest_value in source_hashes.items():
        assert sha(HERE / name) == digest_value, 'Source changed during test: ' + name
    report = dict(
        status='PASS_OFFLINE', hardware_verified=False, physical_timing=False,
        v2_manifest_sha256=V2_SHA, old_elf_sha256=sha(old_elf), old_counterexample=old_rows,
        elf_sha256=sha(elf), source_sha256=source_hashes, command=command,
        samples=4096, stream_positions=32, error_repetitions=128,
        tested_result_words=2, tested_bits_per_word=32, negative_cases=len(rows),
        actual_ARM_stream_calls=2049, total_actual_ARM_calls=machine.calls + old.calls,
        baseline=f'{baseline:08X}', msb_j7=next(row for row in rows if (row['word'], row['position'], row['bit']) == (0, 7, 31)),
        stack_bytes_observed=SP-machine.stack_lowest, callee_saved_and_SP_checked=True,
        result_digest=digest.hexdigest(), negatives=rows, step_profiles=profiles,
        timing_scope='Step profiles include the scalar function wrapper and are ARM instructions, not cycles. All checksum/loop costs remain in APP raw timing; nothing is subtracted to claim kernel-only speed.',
        limitation='2048 specified repeated single-bit faults on this deterministic stream are detected. A finite 32-bit checksum cannot prove detection of arbitrary corruption or every input stream.',
    )
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key not in ('negatives', 'command')}, indent=2))


if __name__ == '__main__':
    main()
