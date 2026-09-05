#!/usr/bin/env python3
"""Execute packed ARM APPs against API tables from two real resident ELFs.

Requires ARM GCC, a host C++ compiler, and Python's unicorn package.
The APP machine code is real; display, storage, keyboard and time are mocked.
"""
import argparse
import struct
import subprocess
import tempfile
from pathlib import Path

from unicorn import Uc, UC_ARCH_ARM, UC_HOOK_CODE, UC_MODE_MCLASS, UC_MODE_THUMB
from unicorn.arm_const import (UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_SP,
    UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
    UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
    UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11)

ROOT = Path(__file__).resolve().parents[1]
BASE, OVERLAY = 0x20000000, 20480
CALLBACKS = ("millis_ms service delay_ms display_columns display_rows "
    "display_clear display_write_utf8 key_poll key_wait led_set led_blink "
    "beep sound_stop file_size file_read graphics_available graphics_width "
    "graphics_height graphics_revision graphics_begin graphics_present "
    "graphics_end key_pressed").split()


def run(command):
    result = subprocess.run([str(x) for x in command], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


def resident_api(path):
    """Read ELF32 sections/symbols without interpreting any firmware code."""
    data = path.read_bytes()
    header = struct.unpack_from("<16sHHIIIIIHHHHHH", data)
    assert header[0][:6] == b"\x7fELF\x01\x01" and header[2] == 40
    sections = [struct.unpack_from("<10I", data, header[6] + i * header[11])
                for i in range(header[12])]
    symbols = {}
    for section in sections:
        if section[1] != 2:
            continue
        strings = sections[section[6]]
        names = data[strings[4]:strings[4] + strings[5]]
        for offset in range(section[4], section[4] + section[5], section[9]):
            name, value, size, _, _, index = struct.unpack_from("<IIIBBH", data, offset)
            name = names[name:names.find(b"\0", name)].decode()
            symbols[name] = value
            if name.startswith("_ZN12loadable_app12_GLOBAL__N_1L3APIE"):
                source = sections[index]
                start = source[4] + value - source[3]
                assert size == 104
                api_address, api = value, data[start:start + size]
    assert symbols["mk61_module_overlay"] == BASE
    assert symbols["_sbss"] == BASE and symbols["_ebss"] >= BASE + OVERLAY
    assert symbols["_sdata"] >= symbols["_ebss"]
    assert symbols["_edata"] <= symbols["_end"] < 0x20010000
    assert struct.unpack_from("<IHH", api) == (0x31505041, 1, 104)
    return api_address, api


def dark(x, y):
    return (x * 3 + y * 5) % 11 < 5


def wbmp(width, height):
    def mb(value):
        return bytes((0x80 | (value >> 7), value & 127)) if value >= 128 else bytes((value,))
    stride = (width + 7) // 8
    pixels = bytearray(stride * height)
    for y in range(height):
        for x in range(width):
            if not dark(x, y):
                pixels[y * stride + x // 8] |= 0x80 >> (x % 8)
    return b"\0\0" + mb(width) + mb(height) + pixels


def oracle(width, height, x0=0, y0=0):
    pixels = bytearray(1536)
    for y in range(64):
        for x in range(192):
            if x + x0 < width and y + y0 < height and dark(x + x0, y + y0):
                pixels[(y // 8) * 192 + x] |= 1 << (y % 8)
    return bytes(pixels)


class Machine:
    def __init__(self, api_address, api):
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        self.uc.mem_map(BASE, 65536)
        self.uc.mem_map(0x08000000, 0x100000)
        self.api_address, self.api = api_address, api
        self.uc.mem_write(api_address, api)
        self.callbacks = {}
        for name, pointer in zip(CALLBACKS, struct.unpack_from("<23I", api, 12)):
            assert pointer & 1 and (pointer & ~1) not in self.callbacks
            self.callbacks[pointer & ~1] = name
            self.uc.mem_write(pointer & ~1, b"\x70\x47")  # BX LR, replaced by hook.
        self.stop = 0x080FF000
        self.uc.mem_write(self.stop, b"\x70\x47")
        self.uc.hook_add(UC_HOOK_CODE, self.hook)

    def load(self, image, image_size, entry):
        self.uc.mem_write(BASE, b"\xcd" * OVERLAY)
        self.uc.mem_write(BASE, image)
        self.memory_size, self.image_size, self.entry = len(image), image_size, entry
        self.frames, self.text, self.keys = [], [], []
        self.begins = self.ends = self.services = 0
        self.file = b""

    def hook(self, uc, address, _size, _context):
        if BASE <= address < BASE + self.image_size or address == self.stop:
            return
        name = self.callbacks.get(address)
        assert name is not None, f"execution escaped APP/API: {address:#x}"
        a, b, c, d = [uc.reg_read(r) for r in
                     (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]
        result = 0
        if name == "file_size":
            result = len(self.file) if a == 42 else 0xFFFFFFFF
        elif name == "file_read":
            assert a == 42 and b + d <= len(self.file)
            assert BASE <= c <= BASE + self.memory_size - d
            uc.mem_write(c, self.file[b:b + d])
            result = d
        elif name == "graphics_present":
            assert b == 1536 and BASE <= a <= BASE + self.memory_size - b
            self.frames.append(bytes(uc.mem_read(a, b)))
            result = 1
        elif name == "graphics_begin":
            self.begins += 1
            result = 1
        elif name == "graphics_end":
            self.ends += 1
        elif name == "graphics_available":
            result = 1
        elif name == "graphics_width":
            result = 192
        elif name == "graphics_height":
            result = 64
        elif name == "graphics_revision":
            result = 7
        elif name == "key_poll":
            assert self.keys, "APP polled past its exit key"
            result = self.keys.pop(0)
        elif name == "service":
            self.services += 1
            assert self.services < 100
        elif name == "delay_ms":
            assert a == 10
        elif name == "display_clear":
            result = 1
        elif name == "display_write_utf8":
            assert a == b == 0 and d <= 63
            self.text.append(bytes(uc.mem_read(c, d)).decode())
            result = 1
        else:
            raise AssertionError(f"unexpected API call: {name}")
        uc.reg_write(UC_ARM_REG_R0, result & 0xFFFFFFFF)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    def call(self, command, argument=0):
        uc, sp = self.uc, 0x2000FFF0
        saved = (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
                 UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11)
        for index, register in enumerate(saved):
            uc.reg_write(register, 0x31410000 + index)
        for register, value in ((UC_ARM_REG_SP, sp), (UC_ARM_REG_LR, self.stop | 1),
                (UC_ARM_REG_R0, command), (UC_ARM_REG_R1, self.api_address),
                (UC_ARM_REG_R2, argument), (UC_ARM_REG_R3, 0)):
            uc.reg_write(register, value)
        uc.mem_write(sp, bytes(4))  # Fifth entry argument, per AAPCS.
        uc.emu_start(BASE + self.entry + 1, self.stop, timeout=10_000_000, count=10_000_000)
        assert uc.reg_read(UC_ARM_REG_PC) == self.stop, "APP failed to return"
        assert uc.reg_read(UC_ARM_REG_SP) == sp
        for index, register in enumerate(saved):
            assert uc.reg_read(register) == 0x31410000 + index
        assert bytes(uc.mem_read(BASE + self.memory_size, OVERLAY - self.memory_size)) == \
            b"\xcd" * (OVERLAY - self.memory_size), "APP wrote beyond its memory"
        return uc.reg_read(UC_ARM_REG_R0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm-toolchain-bin", type=Path, required=True)
    parser.add_argument("--resident-elf", type=Path, action="append", required=True)
    args = parser.parse_args()
    assert len(args.resident_elf) >= 2, "provide two different portable residents"
    apis = [resident_api(x) for x in args.resident_elf]
    assert len({address for address, _ in apis}) == len(apis)
    assert len({api[12:] for _, api in apis}) == len(apis), "callback addresses must differ"
    with tempfile.TemporaryDirectory(prefix="mk61-arm-app-") as directory:
        work = Path(directory)
        reader = work / "reader"
        run(["c++", "-std=c++17", "-O2", "-DMK61_ENABLE_PORTABLE_APPS=1",
             "-I" + str(ROOT / "code"), ROOT / "tests/portable_app_format_self_test.cpp",
             ROOT / "code/loadable_module_format.cpp", ROOT / "code/zx0.cpp", "-o", reader])
        for name in ("HELLO", "WBMP"):
            sources = [ROOT / "examples/portable-apps" / name / "main.c"]
            if name == "WBMP":
                sources += [ROOT / "examples/portable-apps/WBMP/viewer.cpp", ROOT / "code/wbmp.cpp"]
            command = ["python3", ROOT / "tools/build_portable_app.py", "--name", name,
                       "--output-dir", work / name, "--arm-toolchain-bin", args.arm_toolchain_bin]
            for source in sources:
                command += ["--source", source]
            if name == "WBMP":
                command += ["--handled-magic", "I1"]
            run(command)
            app = work / name / (name + ".APP")
            memory = work / name / "decoded.bin"
            run([reader, app, memory])
            packed, decoded = app.read_bytes(), memory.read_bytes()
            image_size, _, entry = struct.unpack_from("<III", packed, 28)
            assert decoded[:image_size] == (work / name / (name + ".bin")).read_bytes()
            assert decoded[image_size:] == bytes(len(decoded) - image_size)
            for api_address, api in apis:
                machine = Machine(api_address, api)
                for launch in range(2):
                    machine.load(decoded, image_size, entry)
                    assert machine.call(0) == 0
                    if name == "HELLO":
                        assert machine.call(1) == 0
                        assert machine.text == ["HELLO C APP"]
                        assert machine.call(1) == 1  # Negative control: dirty .data/.bss.
                    else:
                        width, height = (208, 48) if launch == 0 else (144, 80)
                        machine.file = wbmp(width, height)
                        machine.keys = [16, 16, 16, 15, 20] if launch == 0 else [18, 18, 17, 19]
                        expected = ([oracle(width, height, x) for x in (0, 8, 16, 8)] if launch == 0
                                    else [oracle(width, height, 0, y) for y in (0, 16, 0)])
                        assert machine.call(2, 42) == 0
                        assert machine.frames == expected
                        assert machine.begins == machine.ends == 1
                # Startup refuses an old, truncated API before invoking callbacks.
                machine.load(decoded, image_size, entry)
                machine.uc.mem_write(api_address + 6, struct.pack("<H", 64))
                assert machine.call(0) == 5
            print(f"{name}: same {len(packed)}-byte APP ran with {len(apis)} resident API tables; "
                  "startup, pixels/globals, register and memory guards PASS")


if __name__ == "__main__":
    main()
