#!/usr/bin/env python3
"""Run real ARMv6-M prefetch code against local DOS resources via Unicorn."""
from pathlib import Path
import argparse
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests"), str(ROOT / "tools/games")]
from native_eabi_m0_arm_self_test import Machine
from another_cache import unpack
from tools.firmware.picocalc.build_picocalc import compiler_bin


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data", type=Path, help="local DOS game directory")
    args = parser.parse_args()
    listing = (args.data / "MEMLIST.BIN").read_bytes()
    compiler = compiler_bin(None) / "arm-none-eabi-gcc"
    linker = """ENTRY(fixture_run)
MEMORY { FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 1M
         RAM (rwx) : ORIGIN = 0x20000000, LENGTH = 240K }
SECTIONS { .text : { *(.text*) *(.rodata*) } > FLASH
           .data : { *(.data*) } > RAM AT > FLASH
           .bss (NOLOAD) : { *(.bss*) *(COMMON) } > RAM }
"""
    with tempfile.TemporaryDirectory(prefix="another-prefetch-arm-") as temp:
        temp = Path(temp)
        (temp / "fixture.ld").write_text(linker)
        for slots in (1, 5):
            elf = temp / f"fixture-{slots}.elf"
            subprocess.run([str(compiler), "-mcpu=cortex-m0plus", "-mthumb", "-Os", "-ffreestanding",
                            "-fno-builtin", "-nostdlib", f"-DAW_ASSET_CACHE_SLOTS={slots}",
                            str(ROOT / "examples/portable-apps/ANOTHER/assets.c"),
                            str(ROOT / "tests/another_world_prefetch_arm_fixture.c"),
                            "-Wl,-T," + str(temp / "fixture.ld"), "-lgcc", "-o", str(elf)], check=True)
            for resource in (8, 16, 45, 49, 60, 84):
                entry = bytearray(listing[resource * 20:resource * 20 + 20])
                bank, offset = entry[7], int.from_bytes(entry[8:12], "big")
                packed, size = int.from_bytes(entry[14:16], "big"), int.from_bytes(entry[18:20], "big")
                assert bank and packed and size and size < 64000
                source = (args.data / f"BANK{bank:02X}").read_bytes()[offset:offset + packed]
                assert len(source) == packed
                expected = unpack(source, size)
                entry[7] = 1; entry[8:12] = b"\0" * 4; entry += b"\xff"
                for demand in (0, 1):
                    machine = Machine(elf, stack_bytes=32768, instruction_budget=500000000)
                    machine.uc.hook_del(machine.write_hook)
                    machine.uc.mem_write(machine.elf.symbols["fixture_list"], bytes(entry))
                    machine.uc.mem_write(machine.elf.symbols["fixture_bank"], source)
                    returned = machine.call("fixture_run", demand, width=32)[0] & 0xFFFFFFFF
                    actual = bytes(machine.uc.mem_read(machine.elf.symbols["fixture_store"], size))
                    assert returned == 0 and actual == expected, (slots, resource, demand, returned)
    print("ARMv6-M prefetch: 6 resources, 1/5 cache slots, background and on-demand resume passed")


if __name__ == "__main__":
    main()
