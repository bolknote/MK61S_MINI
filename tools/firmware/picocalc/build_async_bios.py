#!/usr/bin/env python3
"""Build an async-PMU candidate from the versioned Southbridge source archive.

No device is opened. The installed/archived baseline image is never overwritten.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(Path(__file__).resolve().parent), str(ROOT / "sdk/coproc")]
from build_picocalc import compiler_bin
from bios_pmu_async import stage_async_pmu
from bios_stm3_input import stage_stm3_input
from bios_stm3_reply import stage_stm3_reply
from bios_stm3_crc import stage_stm3_crc
from elf32 import ELF


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".build/picocalc-pmu-async")
    parser.add_argument("--drivers", type=Path, default=ROOT / ".build/stm32-module-runtime-20261107/community-southbridge/Drivers")
    parser.add_argument("--toolchain")
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output == ROOT / ".build" or not output.is_relative_to(ROOT / ".build") or args.jobs < 1:
        parser.error("Use a separate output under .build and a positive job count")
    baseline = ROOT / "firmware/picocalc-southbridge"
    if output == baseline or (output / ".git").exists():
        parser.error("Output must be an isolated build directory")
    metadata = json.loads((baseline / "manifest.json").read_text())
    archive = baseline / "source.zip"
    if sha(archive) != metadata["source_archive_sha256"]:
        raise ValueError("Baseline source archive checksum mismatch")
    if sha(baseline / "firmware.bin") != metadata["image_sha256"]:
        raise ValueError("Baseline image checksum mismatch")
    drivers = args.drivers.resolve()
    for part, revision in metadata["upstream"].items():
        checkout = drivers.parent if part == "." else drivers.parent / part
        actual = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
        if actual != revision:
            raise ValueError(f"Driver/source revision mismatch: {part}")
        if part != "." and subprocess.check_output(
                ["git", "-C", str(checkout), "status", "--porcelain", "--untracked-files=no"], text=True):
            raise ValueError(f"Driver checkout has local changes: {part}")
    tool = compiler_bin(args.toolchain)
    source = output / "source"
    source.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as package:
        for item in package.infolist():
            if not item.filename.startswith("source/") or item.is_dir():
                continue
            relative = Path(item.filename).relative_to("source")
            if ".." in relative.parts:
                raise ValueError("Unsafe source archive path")
            target = source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(package.read(item))
    if not (source / "Drivers").exists():
        (source / "Drivers").symlink_to(drivers, target_is_directory=True)
    delta = stage_async_pmu(source)
    delta.update(stage_stm3_input(source))
    delta.update(stage_stm3_reply(source))
    delta.update(stage_stm3_crc(source))
    sources = {str(p.relative_to(source)): sha(p) for p in source.rglob("*")
               if p.is_file() and not p.is_relative_to(source / "Drivers") and not p.is_relative_to(source / "build")}
    output.mkdir(parents=True, exist_ok=True)
    (output / "staged-sources.json").write_text(json.dumps(sources, indent=2) + "\n")
    with (output / "build.log").open("w") as log:
        subprocess.run(["make", "-C", str(source), f"-j{args.jobs}", "GCC_PATH=" + str(tool),
                        "OPT=-Os -flto", "BUILD_DIR=build"], check=True, stdout=log, stderr=subprocess.STDOUT)
    elf_path = source / "build/picocalc_BIOS_jcs.elf"
    binary = source / "build/picocalc_BIOS_jcs.bin"
    elf = ELF(elf_path)
    image = binary.read_bytes()
    for irq, name in [(33, "I2C2_EV_IRQHandler"), (34, "I2C2_ER_IRQHandler")]:
        vector = struct.unpack_from("<I", image, (16 + irq) * 4)[0]
        if vector != elf.symbols[name]["value"] or vector == elf.symbols["Default_Handler"]["value"]:
            raise ValueError(f"Async PMU IRQ vector is not connected: {name}")
    globals_bytes = (elf.symbols["_edata"]["value"] - elf.symbols["_sdata"]["value"] +
                     elf.symbols["_ebss"]["value"] - elf.symbols["_sbss"]["value"])
    gap = 20480 - globals_bytes - 4096
    if binary.stat().st_size > 62 * 1024 or gap < 2048:
        raise ValueError("Async PMU candidate exceeds the existing Flash/RAM/stack budgets")
    result = {"status": "COMPILED_NOT_DEPLOYED", "target": "STM32F103R8", "async_pmu": True,
              "stm3_start_result_input": True,
              "clock_hz": 72000000, "uart_baud": 2250000,
              "base_image_sha256": metadata["image_sha256"], "bin": str(binary), "elf": str(elf_path),
              "bin_sha256": sha(binary), "image_bytes": binary.stat().st_size, "global_ram_bytes": globals_bytes,
              "stack_reserved_bytes": 4096, "ram_unallocated_bytes": gap, "pmu_power_protocol": 1,
              "delta": delta, "source_archive_sha256": sha(archive), "staged_sources_sha256": sha(output / "staged-sources.json"),
              "physical_io": False, "option_byte_programming": False, "upstream": metadata["upstream"]}
    result["i2c2_irq_vectors_verified"] = True
    result["toolchain"] = subprocess.check_output([str(tool / "arm-none-eabi-gcc"), "--version"], text=True).splitlines()[0]
    # These addresses are diagnostic data for this exact BIN, never a callable
    # ABI. LTO may specialize private functions and change their arguments.
    result["diagnostic_symbols"] = {
        name: {"address": f"0x{elf.symbols[name]['value']:08x}", "bytes": elf.symbols[name]["size"]}
        for name in ["hi2c2", "regs", "statistics", "pmu_irq", "pmu_online", "io_active", "recovering"]}
    (output / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
