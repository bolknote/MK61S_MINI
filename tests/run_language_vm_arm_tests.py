#!/usr/bin/env python3
"""Execute the real compiler/VM ARM APPs with an eviction between them.

Uses the existing resident-service emulator. The compiler's SRAM image is
poisoned/replaced before VM execution; hardware, storage and allocator remain
fixtures, so this test does not claim real-device RAM or latency measurements.
"""
import argparse
import math
import struct
import tempfile
from pathlib import Path

from run_portable_system_arm_tests import Machine, Elf, ROOT, run


class LanguageMachine(Machine):
    def load(self, package):
        self.kind, variants, self.image_size, self.entry, self.crc = package
        self.base, self.image = variants[self.address_index]
        self.uc.mem_write(self.pool_begin, b"\xCD"*(self.pool_end-self.pool_begin))
        self.uc.mem_write(self.base,self.image)
        self.uc.ctl_remove_cache(self.pool_begin,self.pool_end)
        kind={"focal":1,"tinybasic":2,"language-vm":10}[self.kind]
        assert self.call(0,self.api,self.crc,kind)==0, (self.kind,self.trace[-12:])


def package(reader, path, elf, work, kind):
    packed = path.read_bytes()
    image_size, memory_size, entry = struct.unpack_from("<III", packed, 28)
    crc = struct.unpack_from("<I", packed, 52)[0]
    low = (elf.symbol("__mk61_dynamic_begin") + 2048 + 31) & ~31
    high = elf.symbol("__mk61_dynamic_end") - ((memory_size + 31) & ~31)
    if low > high:
        raise RuntimeError(f"{path}: APP does not fit fixture's dynamic RAM")
    variants = []
    for address in (low, ((low + high) // 2) & ~31, high):
        decoded = work / "decoded.bin"
        run([reader, path, decoded, hex(address)])
        variants.append((address, decoded.read_bytes()))
    return kind, variants, image_size, entry, crc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resident-elf", type=Path, required=True)
    parser.add_argument("--apps-dir", type=Path, default=ROOT / "tmp/language-vm")
    parser.add_argument("--vm-profile",choices=("core","local"),default="core")
    args = parser.parse_args()
    elf = Elf(args.resident_elf)
    if args.vm_profile=="core":
        elf.require_libm_math(args.resident_elf)
    with tempfile.TemporaryDirectory(prefix="mk61-language-arm-") as directory:
        work = Path(directory)
        reader = work / "reader"
        run(["c++", "-std=c++17", "-O2", "-I" + str(ROOT / "code"),
             ROOT / "tests/portable_app_format_self_test.cpp",
             ROOT / "code/loadable_module_format.cpp", ROOT / "code/zx0.cpp",
             "-o", reader])
        packages = {
            kind: package(reader, args.apps_dir / path, elf, work, kind)
            for kind, path in (("tinybasic", "compiler/tinybasic/BASIC.APP"),
                               ("focal", "compiler/focal/FOCAL.APP"),
                               ("language-vm", f"runner/{args.vm_profile}/LANGVM.APP"))
        }
        cases = [
            ("tinybasic", b"10 A=.1+.2\n20 GOSUB 100;A=A+10;END\n100 A=A+1;RETURN\n", 11.3),
            ("tinybasic", b"10 S=0\n20 FOR I=1 TO 3\n30 S=S+I\n40 NEXT I\n50 A=S\n", 6),
            ("focal", b"1.10 D 2\n1.20 E\n2.10 F I=1,3; S A=A+I\n", 6),
            ("focal", b"1.10 S A=SQRT(9)+SIN(0)\n1.20 E\n" if args.vm_profile=="core"
             else b"1.10 S A=SQRT(9)\n1.20 E\n", 3),
            ("focal", b"1.10 S A=SQRT(2)\n1.20 E\n",
             math.sqrt(2) if args.vm_profile=="core" else
             struct.unpack("<f",struct.pack("<f",math.sqrt(2)))[0]),
        ]
        for address_index in range(3):
            for kind, source, expected in cases:
                m = LanguageMachine(args.resident_elf, True, address_index)
                m.load(packages[kind])
                m.files[42] = (3 if kind == "tinybasic" else 2, "VMTEST", source)
                request = m.input + 512
                image = m.workspace + 6400
                m.uc.mem_write(request, bytes(32))
                m.put(request, 32, 3, image, 1536)
                command = 0x206 if kind == "tinybasic" else 0x106
                result = m.call(command, 42, 0, request)
                assert result == (1 if kind == "tinybasic" else 0), (kind, result, m.lines)
                wire = bytes(m.uc.mem_read(request, 32))
                assert wire[16] == 0 and wire[30] == 1, wire.hex()
                length = struct.unpack_from("<H", wire, 18)[0]
                bytecode = bytes(m.uc.mem_read(image, length))
                old_base, old_size = m.base, len(m.image)
                # This overwrites and invalidates all native compiler code,
                # globals and literal addresses before the following RUN.
                m.load(packages["language-vm"])
                assert bytes(m.uc.mem_read(image, length)) == bytecode
                assert m.base != old_base or len(m.image) != old_size
                variables, array, execute = m.input + 128, m.workspace, m.input + 640
                m.uc.mem_write(variables, bytes(26 * 8))
                m.uc.mem_write(array, bytes(385 * 8))
                m.uc.mem_write(execute, bytes(48))
                m.put(execute, 48, 3, image, length, variables, array, 385)
                m.uc.mem_write(execute + 28, b"\x01\0\0\0")  # no interactive final wait
                assert m.call(0x700, execute) == 1
                error = m.uc.mem_read(execute + 36, 1)[0]
                actual = struct.unpack("<d", m.uc.mem_read(variables, 8))[0]
                assert error == 0 and abs(actual - expected) < 1e-12, (
                    kind, address_index, error, actual, expected, m.lines, m.trace[-12:])
        math_kind="LIBM" if args.vm_profile=="core" else "local float + real conversion bridge"
        print(f"language_vm ARM ({args.vm_profile}): compiler eviction, 2 languages, 3 addresses, {math_kind}/EABI PASS")


if __name__ == "__main__":
    main()
