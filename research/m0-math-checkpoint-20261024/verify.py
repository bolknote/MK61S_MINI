#!/usr/bin/env python3
"""Verify this offline checkpoint; optionally rebuild/replay standalone ARM."""
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
ROOT = W.parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def report(name):
    path = W / name
    if path.exists():
        return json.loads(path.read_bytes())
    return json.loads(gzip.decompress(path.with_suffix(path.suffix + '.gz').read_bytes()))


def verify(check_local=False):
    index = report('checkpoint.json')
    for name, digest in index['files'].items():
        assert sha((W / name).read_bytes()) == digest, name
    provenance = report('provenance.json')
    for entry in provenance['archived_files']:
        data = (W / entry['path']).read_bytes()
        assert sha(data) == entry['sha256'], entry['path']
        raw = gzip.decompress(data) if entry['encoding'] == 'gzip' else data
        assert len(raw) == entry['uncompressed_bytes'], entry['path']
        assert sha(raw) == entry['uncompressed_sha256'], entry['path']
        if check_local:
            assert (ROOT / entry['source']).read_bytes() == raw, entry['source']
    components = report('baseline-v164/evidence/math-component-manifest.json')
    for name, digest in components['files'].items():
        assert sha((W / 'baseline-v164/source' / name).read_bytes()) == digest, name
    q = report('deltas/subnormal-input/qualification.json')
    c = report('deltas/subnormal-input/controls.json')
    assert q['cases'] == len(q['rows']) == 70261
    assert q['ARM_calls'] == 210783
    assert all(r['correct']['candidate'] and r['correct']['parent'] for r in q['rows'])
    profiled = [r for r in q['rows'] if r['profiled']]
    assert len(profiled) == 3015
    assert sum(r['instructions']['candidate'] < r['instructions']['parent'] for r in profiled) == 2623
    assert sum(r['instructions']['candidate'] == r['instructions']['parent'] for r in profiled) == 392
    assert all(r['instructions']['candidate'] <= r['instructions']['Qfplib']
               for r in profiled if r['correct']['Qfplib'])
    assert c['cases'] == len(c['rows']) == 1768
    assert all(r['correct']['candidate'] and r['outputs']['candidate'] == r['outputs']['parent']
               and r['instructions']['candidate'] == r['instructions']['parent'] for r in c['rows'])
    u = report('deltas/uint32/qualification.json')
    assert u['cases'] == len(u['rows']) == 47966
    assert all(r['outputs']['candidate'] == r['outputs']['baseline'] == r['expected'] for r in u['rows'])
    for name, filename in [('mixed-sign', 'receipt.json'), ('uint32', 'receipt.json'),
                           ('top-normal', 'FINAL-REVIEW.json'), ('low-normal', 'FINAL-REVIEW.json')]:
        assert not report('reviews/' + name + '/' + filename)['blockers'], name
    return {'archive_files': len(index['files']), 'original_artifacts': len(provenance['archived_files']),
            'math_components': len(components['files']), 'local_originals_checked': check_local}


def build(output, toolchain):
    output = output.resolve()
    assert output != W and W not in output.parents, 'Use a new private output directory'
    output.mkdir(parents=True, exist_ok=False)
    compiler = str(toolchain / 'arm-none-eabi-gcc')
    linker = str(toolchain / 'arm-none-eabi-ld')
    hashes = {}
    for name in ('mixed-sign', 'top-normal', 'low-normal', 'subnormal-input', 'uint32'):
        source = W / 'deltas' / name
        target = output / name
        target.mkdir()
        saved = report('deltas/' + name + '/build.json')
        for filename in ('candidate.S', 'candidate.ld'):
            shutil.copyfile(source / filename, target / filename)
        subprocess.run([compiler, '-mcpu=cortex-m0plus', '-mthumb', '-mfloat-abi=soft',
                        '-DMK61_USE_M0_EABI=1', '-DMK61_M0_RP2040_EABI=1', '-c',
                        str(target / 'candidate.S'), '-o', str(target / 'candidate.o')], check=True)
        # Historical diagnostic blobs bind the old C++ fallback's address;
        # they are rebuilt here but only the self-contained final blob is replayed.
        bindings = ['--defsym', 'mk61_m0_dadd_slow=269381189'] if name in (
            'mixed-sign', 'top-normal', 'low-normal') else []
        subprocess.run([linker, '-T', str(target / 'candidate.ld'), *bindings, str(target / 'candidate.o'),
                        '-o', str(target / 'candidate.elf')], check=True)
        expected = saved.get('candidate_ELF_sha256') or saved.get('files', {}).get('candidate.elf')
        if expected is None:
            expected = report('deltas/' + name + '/body-equivalence.json')['executed_diagnostic_ELF_sha256']
        actual = sha((target / 'candidate.elf').read_bytes())
        assert actual == expected, (name, actual, expected)
        hashes[name] = actual
    return output, hashes


def replay(output):
    # These modules operate only on local ELF bytes and emulated memory.
    sys.path.insert(0, str(W / 'support'))
    sys.path.insert(0, str(W / 'support/support'))
    import ctypes as C
    import struct
    from native_eabi_m0_arm_self_test import Machine, SP
    from m0_mpfr_oracle import Oracle, _Number
    from oracles import integer_binary, equal, is_nan
    oracle = Oracle()
    machine = Machine(output / 'subnormal-input/candidate.elf', True, stack_bytes=32)
    state = struct.pack('<7I', 17, 3, 17, 3, 5, 2, 3)
    checked = profiled = 0
    for name in ('qualification', 'controls'):
        for row in report('deltas/subnormal-input/' + name + '.json')['rows']:
            a, b = int(row['x'], 16), int(row['y'], 16)
            op = row['operation']
            expected = integer_binary('add' if op == 'dadd' else 'sub', a, b, width=64)
            assert equal(expected, oracle.reference(op, a, b), 64)
            sb = b ^ ((1 << 63) if op == 'dsub' else 0)
            policy = a | (1 << 51) if is_nan(a, 64) else sb | (1 << 51) if is_nan(sb, 64) else expected
            machine.uc.mem_write(0xd0000060, state)
            got, _, count = machine.call('sub_candidate_' + op, a, b, count=row['profiled'])
            assert got == policy == int(row['outputs']['candidate'], 16), row
            assert bytes(machine.uc.mem_read(0xd0000060, 28)) == state
            if row['profiled']:
                assert count == row['instructions']['candidate'], row
                profiled += 1
            checked += 1
    assert SP - machine.stack_lowest == 20
    conversion = Machine(output / 'uint32/candidate.elf', True, stack_bytes=32)
    lib = oracle.lib
    lib.mpfr_get_ui.argtypes = [C.POINTER(_Number), C.c_int]
    lib.mpfr_get_ui.restype = C.c_ulong
    number = _Number()
    lib.mpfr_init2(C.byref(number), 53)
    try:
        for row in report('deltas/uint32/qualification.json')['rows']:
            a = int(row['x'], 16)
            exponent, fraction = (a >> 52) & 2047, a & ((1 << 52) - 1)
            expected = (0 if a >> 63 or exponent < 1023 or (exponent == 2047 and fraction)
                        else 0xffffffff if exponent >= 1055 else ((1 << 52) | fraction) >> (1075 - exponent))
            lib.mpfr_set_d(C.byref(number), struct.unpack('<d', struct.pack('<Q', a))[0], 0)
            assert expected == min(int(lib.mpfr_get_ui(C.byref(number), 1)), 0xffffffff)
            count_enabled = row['instructions']['candidate'] is not None
            conversion.uc.mem_write(0xd0000060, state)
            got, _, count = conversion.call('candidate_d2uiz', a, count=count_enabled)
            assert got & 0xffffffff == expected == row['outputs']['candidate'], row
            assert bytes(conversion.uc.mem_read(0xd0000060, 28)) == state
            if count_enabled:
                assert count == row['instructions']['candidate'], row
                profiled += 1
            checked += 1
    finally:
        lib.mpfr_clear(C.byref(number))
    return {'fresh_candidate_ARM_calls': checked, 'profiled_counts_reproduced': profiled,
            'MPFR_version': oracle.version, 'firmware_or_ROM_mapped': False,
            'hardware_accessed': False, 'whole_library_replayed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-local', action='store_true')
    parser.add_argument('--build-output', type=Path)
    parser.add_argument('--toolchain', type=Path)
    parser.add_argument('--replay', action='store_true')
    args = parser.parse_args()
    if args.replay and args.build_output is None:
        parser.error('--replay requires --build-output')
    result = verify(args.check_local)
    if args.build_output:
        toolchain = args.toolchain
        if toolchain is None:
            compiler = shutil.which('arm-none-eabi-gcc')
            if not compiler:
                parser.error('Specify --toolchain /path/to/arm-none-eabi/bin')
            toolchain = Path(compiler).parent
        output, result['rebuilt_ELF_hashes'] = build(args.build_output, toolchain)
        if args.replay:
            result['replay'] = replay(output)
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': 'PASS_RESEARCH_CHECKPOINT', **result}, indent=2))


if __name__ == '__main__':
    main()
