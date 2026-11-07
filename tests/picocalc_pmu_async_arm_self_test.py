#!/usr/bin/env python3
"""Execute the real PMU driver and legacy IRQ code as Cortex-M3 Thumb code.

Only the HAL/PMU peripheral model is substituted, as in the HOST fault tests.
This is architectural execution proof, not physical bus or timing validation.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools/firmware/picocalc"), str(ROOT / "sdk/coproc")]
from build_picocalc import compiler_bin
from elf32 import ELF
from picocalc_pmu_async_self_test import prepare_fixture
from unicorn_runtime import Uc
from unicorn import UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="mk61-pmu-arm-") as folder:
        work = Path(folder)
        staged, mock = prepare_fixture(work)
        binary = work / "test.elf"
        sources = [ROOT / "ports/picocalc/bios/pmu_async.c", staged / "Core/Src/axp2101.c",
                   staged / "Core/Src/batt.c", ROOT / "tests/picocalc_pmu_async_self_test.c",
                   mock / "arm_test_support.c"]
        subprocess.run([str(compiler_bin(args.toolchain) / "arm-none-eabi-gcc"),
            "-mcpu=cortex-m3", "-mthumb", "-mfloat-abi=soft", "-std=c11", "-O2", "-g",
            "-ffreestanding", "-fno-builtin", "-fno-stack-protector", "-fno-unwind-tables",
            "-fno-asynchronous-unwind-tables", "-DMK61_PMU_TEST_ARM", "-Wall", "-Wextra", "-Werror",
            "-Wno-unused-function", "-Wno-misleading-indentation", "-nostdlib",
            "-I" + str(mock), "-I" + str(ROOT / "ports/picocalc/bios"),
            *map(str, sources), "-Wl,-T," + str(mock / "arm_test.ld"), "-lgcc", "-o", str(binary)], check=True)
        elf = ELF(binary)
        counts = {}
        for case in ["normal", "wrap", "offline"]:
            u = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
            u.mem_map(0x08000000, 128 * 1024)
            u.mem_map(0x20000000, 64 * 1024)
            for segment in elf.segments:
                u.mem_write(segment["address"], segment["data"])
            scratch, stop = 0x2000E000, 0x0801F000
            u.mem_write(scratch, struct.pack("<III", scratch + 16, scratch + 24, 0))
            u.mem_write(scratch + 16, b"test\0")
            u.mem_write(scratch + 24, case.encode() + b"\0")
            u.reg_write(UC_ARM_REG_SP, 0x2000D000)
            u.reg_write(UC_ARM_REG_LR, stop | 1)
            u.reg_write(UC_ARM_REG_R0, 2)
            u.reg_write(UC_ARM_REG_R1, scratch)
            executed = [0]

            def instruction(uc, address, size, unused):
                executed[0] += 1
                if address == (elf.symbols["test_arm_fail"]["value"] & ~1):
                    line, at = uc.reg_read(UC_ARM_REG_R0), uc.reg_read(UC_ARM_REG_R1)
                    expression = bytes(uc.mem_read(at, 256)).split(b"\0", 1)[0].decode()
                    raise AssertionError(f"{case}: C assertion at line {line}: {expression}")

            u.hook_add(UC_HOOK_CODE, instruction)
            u.emu_start(elf.symbols["main"]["value"] | 1, stop, count=8_000_000)
            assert u.reg_read(UC_ARM_REG_PC) == stop, "Execution did not return within the instruction budget"
            assert u.reg_read(UC_ARM_REG_R0) == 0
            counts[case] = executed[0]
        result = {"status": "ARM_PMU_MODEL_PASS", "physical_io": False, "physical_timing": False,
                  "instruction_counts": counts, "target": "Cortex-M3 Thumb", "hal_model": True,
                  "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                    for p in sources if p.is_relative_to(ROOT)}}
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result))


if __name__ == "__main__":
    main()
