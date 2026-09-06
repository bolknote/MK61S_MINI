#!/usr/bin/env python3
"""Run ordinary C APPs with public services from real resident ARM code.

C5 and workspace backing use the existing peripheral model. Service lookup,
feature reporting, math, EABI helpers, formatting and editor execute in ARM.
"""
import argparse
import struct
import tempfile
from pathlib import Path
from run_portable_system_arm_tests import Machine, Elf, ROOT, run


def package(reader, path, elf, work):
    packed = path.read_bytes()
    image_size, memory_size, entry = struct.unpack_from('<III', packed, 28)
    crc = struct.unpack_from('<I', packed, 52)[0]
    low = (elf.symbol('__mk61_dynamic_begin') + 2048 + 31) & ~31
    high = elf.symbol('__mk61_dynamic_end') - ((memory_size + 31) & ~31)
    assert low <= high
    variants = []
    for address in (low, ((low + high) // 2) & ~31, high):
        decoded = work/'decoded.bin'
        run([reader, path, decoded, hex(address)])
        variants.append((address, decoded.read_bytes()))
    return path.parent.name, variants, image_size, entry, crc


class UserMachine(Machine):
    def load_user(self, package):
        self.kind, variants, self.image_size, self.entry, self.crc = package
        self.base, self.image = variants[self.address_index]
        self.uc.mem_write(self.pool_begin, b'\xCD' * (self.pool_end - self.pool_begin))
        self.uc.mem_write(self.base, self.image)
        self.uc.ctl_remove_cache(self.pool_begin, self.pool_end)
        return self.call(0, self.api)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resident-elf', type=Path, action='append', required=True)
    parser.add_argument('--minimal-elf', type=Path, required=True)
    parser.add_argument('--apps-dir', type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='mk61-services-arm-') as directory:
        work = Path(directory)
        reader = work/'reader'
        run(['c++', '-std=c++17', '-O2', '-DMK61_ENABLE_PORTABLE_APPS=1',
             '-I'+str(ROOT/'code'), ROOT/'tests/portable_app_format_self_test.cpp',
             ROOT/'code/loadable_module_format.cpp', ROOT/'code/zx0.cpp', '-o', reader])
        for resident in args.resident_elf:
            elf = Elf(resident)
            for kind in ('services', 'services-local', 'example'):
                app = package(reader, args.apps_dir/kind/'SERVICES.APP', elf, work)
                for address in range(3):
                    m = UserMachine(resident, True, address)
                    assert m.load_user(app) == 0
                    m.keys = [19]
                    result = m.call(1, m.api)
                    assert result == 0, (resident, kind, address, result, m.trace[-15:])
                    assert not m.files, 'temporary C5 file leaked'
                    if kind == 'example': assert m.lines == ['sqrt(3^2+4^2)=5'], m.lines
                print(f'{resident.parent.name}/{kind}: three load addresses, registers, bounds PASS')

        # Optional services can be absent from a current, reduced firmware.
        # Shared-runtime APPs stop at INITIALIZE; normal APPs can choose fallback.
        for resident in (args.minimal_elf,):
            elf = Elf(resident)
            for kind in ('services', 'services-local'):
                app = package(reader, args.apps_dir/kind/'SERVICES.APP', elf, work)
                m = UserMachine(resident, False)
                result = m.load_user(app)
                if kind == 'services': assert result == 5
                else:
                    assert result == 0
                    assert m.call(1, m.api) == 5
                assert not m.files and not m.leases
            print(f'{resident.parent.name}: missing services refused cleanly PASS')


if __name__ == '__main__':
    main()
