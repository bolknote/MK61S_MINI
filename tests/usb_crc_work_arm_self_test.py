#!/usr/bin/env python3
"""Execute the compiled CRC isolation workload, including real resident memcpy."""
import argparse
import re
import struct
import tempfile
from pathlib import Path
from run_portable_system_arm_tests import Machine, ROOT, run
from compute_clock_fixture import oracle


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--resident-elf', type=Path, required=True)
    ap.add_argument('--app', type=Path, required=True)
    args = ap.parse_args()
    body = (ROOT/'code/loadable_app_services.h').read_text().split('enum mk61_service_operation {', 1)[1].split('};', 1)[0]
    compute = re.findall(r'\bMK61_SERVICE_[A-Z_]+\b', re.sub(r'/\*.*?\*/', '', body, flags=re.S)).index('MK61_SERVICE_COMPUTE')+1

    class Probe(Machine):
        def system(self, op, a, b, c, p):
            if op != compute:
                return super().system(op, a, b, c, p)
            assert p == 0
            if a == 0: return 0x434D5031
            if a == 1:
                assert not self.token
                self.token = 0x10001
                return self.token
            if a == 2:
                assert b == self.token
                self.token = 0
                return 1
            if a == 3:
                return 144000000 if self.mode & 32 or (not self.mode & 16 and self.token) else 72000000
            if a == 0xC006: return 0x55435231
            if a == 0xC007: return self.mode
            if a == 0xC009:
                assert b not in self.results
                self.results[b] = c
                return 1
            if a == 0xC00A:
                assert not self.token
                self.finished = True
                return 1
            if a == 0xC00E:return 0
            if a in (0xC002, 0xC003): return 1
            if a == 0xC004: return 100+b
            if a == 0xC005: return 1000+b
            raise AssertionError((a, b, c))

    packed = args.app.read_bytes()
    image, memory, entry = struct.unpack_from('<III', packed, 28)
    crc = struct.unpack_from('<I', packed, 52)[0]
    with tempfile.TemporaryDirectory(prefix='mk61-usb-crc-work-') as directory:
        reader, target = Path(directory)/'reader', Path(directory)/'image.bin'
        run(['c++', '-std=c++17', '-O2', '-I'+str(ROOT/'code'),
             ROOT/'tests/portable_app_format_self_test.cpp', ROOT/'code/loadable_module_format.cpp',
             ROOT/'code/zx0.cpp', '-o', reader])
        for mode in (0, 32, 16):
            m = Probe(args.resident_elf, True)
            m.mode, m.results, m.token, m.finished = mode, {}, 0, False
            m.keys = [-1]*(66*3)
            base = (m.pool_begin+31) & ~31
            assert base+memory <= m.pool_end
            run([reader, args.app, target, hex(base)])
            m.load(('app', [(base, target.read_bytes())], image, entry, crc))
            flow = m.input
            m.uc.mem_write(flow, struct.pack('<4I', 48, 1, 0, 0)+struct.pack('<HBBI', 100, 4, 0, 66)+bytes(24))
            assert m.call(3) == 0x31574C46
            assert m.call(4, flow) == 1
            assert m.words(flow+32, 4) == (4, 0, 0, 0)
            assert m.finished and m.results[60] == 0 and m.results[61] == mode
            assert all(m.results[20*i] == oracle(66*1024) for i in range(3))
            expected = [144000000]*3 if mode == 32 else [72000000]*3 if mode == 16 else [72000000,144000000,72000000]
            assert [m.results[20*i+1] for i in range(3)] == expected
            assert m.results[62] == 0 and m.results[63] == 0x31415926
            assert all(m.results[i] == 0 for i in range(64,70))
            assert len(m.results) == 70
            print('RAM-only CRC workload ARM: mode', mode, 'hash/memcpy/canaries/clocks/no-file-writes PASS')


if __name__ == '__main__':
    main()
