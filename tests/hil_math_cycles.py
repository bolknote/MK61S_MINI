#!/usr/bin/env python3
"""Compare local binary32/binary64 with published SEGGER inputs using real DWT.

Never flashes. Installs two reserved diagnostic APPs, then removes every test
file and verifies original files, program, registers, stack and current path.
SEGGER numbers are published reference data, not a local emFloat measurement.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

from hil_c5_stack import read_file, write_file
from hil_multi_device_identity import parse_identity
from hil_packbits_firmware import fingerprint
from hil_portable_apps import ScreenPort

ROOT = Path(__file__).resolve().parents[1]
OPERATIONS = ('sin', 'cos', 'tan', 'asin', 'acos', 'atan', 'ln',
              'log10', 'exp', 'sqrt', 'pow')
REMOTE = ('/SEGGD.APP', '/SEGGF.APP', '/SEGGD.bin', '/SEGGF.bin', '/SEGGG.APP', '/SEGGG.bin')


def decode(raw, mode, cases):
    assert len(raw) == 24 + 40 * len(cases), len(raw)
    header = struct.unpack_from('<6I', raw)
    assert header == (0x42474553, 1, mode, len(cases), 512, 9), header
    rows = []
    for index, case in enumerate(cases):
        fields = struct.unpack_from('<IIIIQIIII', raw, 24 + 40 * index)
        operation, operand, expected, rounded, actual, ram, control, flash, fctrl = fields
        assert operation == OPERATIONS.index(case['function'])
        assert operand == int(case['input32'], 16)
        assert expected == int(case['expected32'], 16)
        rows.append({
            **case,
            'calculated_round32': f'{rounded:08X}',
            'calculated_native_bits': f'{actual:016X}',
            'matches_expected_binary32': rounded == expected,
            'RAM_net_cycles_per_call': (ram - control) / 512,
            'RAM_raw_cycles_per_call': ram / 512,
            'RAM_control_cycles_per_call': control / 512,
            'Flash_net_cycles_per_call': (flash - fctrl) / 512 if mode == 1 else None,
            'Flash_raw_cycles_per_call': flash / 512 if mode == 1 else None,
            'Flash_control_cycles_per_call': fctrl / 512 if mode == 1 else None,
        })
    return {'rows': rows,
            'all_binary32_outputs_match': all(row['matches_expected_binary32'] for row in rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--public-id', required=True)
    parser.add_argument('--expected-build', required=True)
    parser.add_argument('--double-app', type=Path, required=True)
    parser.add_argument('--float-app', type=Path, required=True)
    parser.add_argument('--gnu-double-app', type=Path, help='Optional matching binary64 GNU libm control in SRAM')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--keyboard-layout', type=int, choices=(0, 1), default=1)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    reference = json.loads((ROOT / 'tests/fixtures/segger_float_cases.json').read_text())
    report = {
        'reference': {key: val for key, val in reference.items() if key != 'cases'},
        'comparison': 'Published emFloat binary32 on NXP K66FN2M0; no local emFloat binary',
        'precision': 'Own binary64: 53 bits; GNU binary32: 24 bits; exact original binary32 operands',
        'method': 'DWT CYCCNT, median of nine batches of 512 calls, minus identity-loop control',
        'Flash_method': 'Resident math service minus unknown-operation dispatcher control',
        'memory': 'Local APP math and arithmetic helpers in SRAM; resident service in Flash',
        'source_sha256': hashlib.sha256((ROOT / 'code/compact_math.cpp').read_bytes()).hexdigest(),
        'APP_sha256': {key: hashlib.sha256(path.read_bytes()).hexdigest()
                       for key, path in [('double', args.double_app), ('float', args.float_app)]},
    }
    if args.gnu_double_app:
        report['APP_sha256']['gnu_double'] = hashlib.sha256(args.gnu_double_app.read_bytes()).hexdigest()
    with ScreenPort(args.port, keyboard_layout=args.keyboard_layout) as port:
        identity = parse_identity(port.command('identity', 15))
        assert identity.public == args.public_id.upper(), identity
        assert identity.build == args.expected_build.upper(), identity
        report['identity'] = identity.__dict__
        report['prof_before'] = port.command('prof', 20)
        original = fingerprint(port)
        logical = {command: port.command(command, 20) for command in ('reg', 'stk', 'dump', 'pwd')}
        assert not any(path.casefold() in {p.casefold() for p in REMOTE}
                       for path in original['files']), 'reserved benchmark name already exists'
        try:
            variants = [(1, 'double', args.double_app, REMOTE[0], REMOTE[2]),
                        (0, 'float', args.float_app, REMOTE[1], REMOTE[3])]
            if args.gnu_double_app:
                variants.append((2, 'gnu_double', args.gnu_double_app, REMOTE[4], REMOTE[5]))
            for mode, kind, app, remote_app, remote_output in variants:
                write_file(port, remote_app, app.read_bytes())
                launch = port.command(f'open "{remote_app}"', timeout=120)
                assert 'Open failed!' not in launch, launch
                raw = read_file(port, remote_output)
                report[kind] = {**decode(raw, mode, reference['cases']), 'launch': launch}
                (args.output_dir / f'{kind}-raw.bin').write_bytes(raw)
                print(kind, len(reference['cases']), 'published inputs measured', flush=True)
            assert report['double']['all_binary32_outputs_match'], report['double']
        finally:
            port.command('fsput cancel')
            current = fingerprint(port)
            for path in REMOTE:
                actual = next((p for p in current['files'] if p.casefold() == path.casefold()), None)
                if actual:
                    response = port.command(f'rm "{actual}"', 30)
                    assert 'Removed 1 entry.' in response, response
            assert fingerprint(port) == original, 'benchmark changed original files'
            assert {command: port.command(command, 20) for command in logical} == logical, \
                'benchmark changed original logical state'
            identity = parse_identity(port.command('identity', 15))
            assert identity.public == args.public_id.upper() and identity.build == args.expected_build.upper()
            report['health'] = {command: port.command(command, 20)
                                for command in ('df', 'crash show', 'mpu status')}
            assert 'FIRMWARE CRC state=valid' in report['health']['df']
            assert 'CRASH none' in report['health']['crash show']
            report['preservation'] = 'Original files/program/registers/stack/pwd exact'
            (args.output_dir / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print('SRAM/Flash benchmark and preservation PASS', flush=True)


if __name__ == '__main__':
    main()
