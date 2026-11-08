#!/usr/bin/env python3
"""Finite selector APP lifetime and invalid-input checks in the ARM model."""
import argparse
import struct
import tempfile
from pathlib import Path
from run_portable_system_arm_tests import Machine, ROOT, run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resident-elf', type=Path, required=True)
    parser.add_argument('--app', type=Path, required=True)
    args = parser.parse_args()
    packed = args.app.read_bytes()
    size, memory, entry = struct.unpack_from('<III', packed, 28)
    crc = struct.unpack_from('<I', packed, 52)[0]
    with tempfile.TemporaryDirectory(prefix='mk61-clock-select-') as directory:
        root = Path(directory)
        reader, image = root / 'reader', root / 'image.bin'
        run(['c++', '-std=c++17', '-O2', '-I' + str(ROOT / 'code'),
             ROOT / 'tests/portable_app_format_self_test.cpp',
             ROOT / 'code/loadable_module_format.cpp', ROOT / 'code/zx0.cpp', '-o', reader])
        for value in (b'1', b'3', b'4', b'5', b'7', b'11'):
            m = Machine(args.resident_elf, True)
            m.compute_platform = 1
            m.compute_profile = 0
            base = (m.pool_begin + 31) & ~31
            assert base + memory <= m.pool_end
            run([reader, args.app, image, hex(base)])
            m.load(('app', [(base, image.read_bytes())], size, entry, crc))
            m.files = {100: (8, 'CLKSET', packed), 101: (4, 'profile.txt', value)}
            m.uc.mem_write(m.input, struct.pack('<4I', 48, 1, 0, 0) +
                struct.pack('<HBBI', 100, 4, 0, 0) + bytes(24))
            assert m.call(3) == 0x31574C46
            assert m.call(4, m.input) == 1
            expected=int(value) if value in (b'1', b'3', b'4') else 0
            assert m.compute_profile == expected
            if expected:
                assert m.words(m.input + 32, 4) == (4, 0, 0, 0)
                assert m.clock >= 2000 and m.services
            else:
                assert not any(row[:3] == (25, 27, 1) for row in m.trace)
        print('Finite clock selector ARM: SETUP profile, save wait, invalid input and canaries PASS')


if __name__ == '__main__':
    main()
