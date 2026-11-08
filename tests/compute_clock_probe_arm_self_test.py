#!/usr/bin/env python3
"""Run the finite diagnostic's ARM code with modeled C9/time/COMPUTE services.

This verifies the probe, not clock hardware or performance. The production
clock/policy code has separate ARM and sanitizer tests.
"""
import argparse
import re
import struct
import tempfile
from pathlib import Path
from run_portable_system_arm_tests import Machine, ROOT, run
from compute_clock_fixture import oracle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resident-elf', type=Path, required=True)
    parser.add_argument('--app', type=Path, required=True)
    args = parser.parse_args()
    header = (ROOT / 'code/loadable_app_services.h').read_text()
    body = header.split('enum mk61_service_operation {', 1)[1].split('};', 1)[0]
    names = re.findall(r'\bMK61_SERVICE_[A-Z_]+\b', re.sub(r'/\*.*?\*/', '', body, flags=re.S))
    compute = names.index('MK61_SERVICE_COMPUTE') + 1

    class ProbeMachine(Machine):
        def system(self, op, a, b, c, p):
            if op != compute:
                return super().system(op, a, b, c, p)
            assert c == p == 0
            self.compute_calls.append((a, b))
            if a == 0:
                return 0x434D5031
            if a == 1:
                assert not b and not self.token
                self.token = 0x10001
                return self.token
            if a == 2:
                if not self.token or b != self.token:
                    return 0
                self.token = 0
                return 1
            assert a == 3 and not b
            return 96000000 if not self.profile else (108000000 if self.token else 54000000)

    packed = args.app.read_bytes()
    image_size, memory_size, entry = struct.unpack_from('<III', packed, 28)
    crc = struct.unpack_from('<I', packed, 52)[0]
    with tempfile.TemporaryDirectory(prefix='mk61-compute-probe-') as directory:
        root = Path(directory)
        reader, target = root / 'reader', root / 'image.bin'
        run(['c++', '-std=c++17', '-O2', '-I' + str(ROOT / 'code'),
             ROOT / 'tests/portable_app_format_self_test.cpp',
             ROOT / 'code/loadable_module_format.cpp', ROOT / 'code/zx0.cpp', '-o', reader])
        for profile in (0, 1):
            machine = ProbeMachine(args.resident_elf, True)
            machine.profile, machine.token, machine.compute_calls = profile, 0, []
            base = (machine.pool_begin + 31) & ~31
            assert base + memory_size <= machine.pool_end
            run([reader, args.app, target, hex(base)])
            machine.load(('app', [(base, target.read_bytes())], image_size, entry, crc))
            machine.files = {100: (8, 'CLKTEST', packed)}
            flow = machine.input
            machine.uc.mem_write(flow, struct.pack('<4I', 48, 1, 0, 0) +
                struct.pack('<HBBI', 100, 4, 0, 8) + bytes(24))
            assert machine.call(3) == 0x31574C46
            # The production flow_invoke accepts exactly1, independently of
            # flow->status (whose successful wire value is0).
            assert machine.call(4, flow) == 1
            assert machine.words(flow + 32, 4) == (4, 0, 0, 0)
            reports = [data for kind, name, data in machine.files.values()
                       if kind == 4 and name == 'clock']
            assert len(reports) == 1
            report = reports[0].decode('ascii')
            fields = {key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', report)}
            assert fields['V'] == 1 and fields['N'] == 8192
            assert fields['HASH'] == oracle(fields['N'])
            assert fields['END'] == fields['DUP'] == fields['MATCH'] == 1
            assert [fields[f'HZ{i}'] for i in range(3)] == (
                [54000000, 108000000, 54000000] if profile else [96000000] * 3)
            assert all(fields[f'US{i}'] > 0 and fields[f'GAP{i}'] > 0 for i in range(3))
            assert not machine.token and machine.services == 24
            assert sum(a == 1 for a, _ in machine.compute_calls) == 1
            print(f'Finite COMPUTE probe ARM: profile {profile}, bounded workload, hash, leases, report and canaries PASS')


if __name__ == '__main__':
    main()
