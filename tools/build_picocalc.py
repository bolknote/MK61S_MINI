#!/usr/bin/env python3
"""Build the isolated PicoCalc/Pico H prototype with the shared MK61S core."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SDK_VERSION = "2.2.0"
SDK_COMMIT = "a1438dff1d38bd9c65dbd693f0e5db4b9ae91779"
TARGET = "mk61s-picocalc-pico-h"


def run(command, **kwargs):
    return subprocess.run([str(x) for x in command], check=True, **kwargs)


def compiler_bin(value):
    suffix = ".exe" if os.name == "nt" else ""
    if value:
        base = Path(value).expanduser().resolve()
        candidates = [base, base / "bin"]
    else:
        compiler = shutil.which("arm-none-eabi-gcc")
        candidates = [Path(compiler).parent] if compiler else []
        candidates += sorted((ROOT / ".build/toolchains").glob("*/bin"), reverse=True)
        # Reuse an existing Arduino-installed compiler; no Arduino source or
        # board package participates in the Pico build.
        for packages in (Path.home() / "Library/Arduino15/packages",
                         Path.home() / ".arduino15/packages",
                         Path.home() / "AppData/Local/Arduino15/packages"):
            candidates += sorted(packages.glob("*/tools/*arm-none-eabi-gcc/*/bin"), reverse=True)
    for candidate in candidates:
        if all((candidate / ("arm-none-eabi-" + name + suffix)).is_file()
               for name in ("gcc", "g++", "size", "readelf")):
            return candidate
    raise ValueError("GNU Arm GCC missing; pass --toolchain /path/to/bin or set MK61_GCC_TOOLCHAIN")


def prepare_sdk(path, fetch):
    if not (path / "pico_sdk_init.cmake").is_file():
        if not fetch:
            raise ValueError("Pico SDK missing; pass --fetch-sdk or --sdk /path/to/pico-sdk")
        path.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--depth", "1", "--branch", SDK_VERSION,
             "https://github.com/raspberrypi/pico-sdk.git", path])
    version = (path / "pico_sdk_version.cmake").read_text()
    actual = ".".join(re.search(rf"set\(PICO_SDK_VERSION_{part} (\d+)\)", version)[1]
                      for part in ("MAJOR", "MINOR", "REVISION"))
    if actual != SDK_VERSION:
        raise ValueError(f"Tested Pico SDK is {SDK_VERSION}; found {actual}")
    revision = None
    if (path / ".git").exists():
        revision = run(["git", "-C", path, "rev-parse", "HEAD"],
                       capture_output=True, text=True).stdout.strip()
        if revision != SDK_COMMIT:
            raise ValueError(f"Pico SDK {SDK_VERSION} commit differs from the pinned release")
    if not (path / "lib/tinyusb/src/tusb.h").is_file():
        if not fetch:
            raise ValueError("TinyUSB missing; rerun with --fetch-sdk or initialize lib/tinyusb")
        run(["git", "-C", path, "submodule", "update", "--init", "--depth", "1", "lib/tinyusb"])
    return revision


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=["picocalc-pico-h"], default="picocalc-pico-h")
    parser.add_argument("--sdk", type=Path, default=Path(os.environ.get(
        "PICO_SDK_PATH", ROOT / ".build/picocalc-deps/pico-sdk")))
    parser.add_argument("--fetch-sdk", action="store_true", help="Fetch pinned SDK and TinyUSB if missing")
    parser.add_argument("--toolchain", default=os.environ.get("MK61_GCC_TOOLCHAIN"))
    parser.add_argument("--build-path", type=Path, default=ROOT / ".build/picocalc-pico-h")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "binary/picocalc-pico-h")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--compiler-runtime", action="store_true",
                        help="Control build using GCC arithmetic instead of the owned M0 runtime")
    parser.add_argument("--sampling-profile", action="store_true", help="Build diagnostic-only core 0 PC sampling")
    parser.add_argument("--psram-spi", action="store_true", help="Control build without four-bit PSRAM")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    try:
        sdk = args.sdk.expanduser().resolve()
        sdk_revision = prepare_sdk(sdk, args.fetch_sdk)
        toolchain = compiler_bin(args.toolchain)
        cmake = shutil.which("cmake")
        ninja = shutil.which("ninja")
        if not cmake or not ninja:
            raise ValueError("Install CMake and Ninja and put them on PATH")
        build = args.build_path.expanduser().resolve()
        output = args.output_dir.expanduser().resolve()
        source_hash = hashlib.sha256()
        for source in sorted([ROOT / 'tools/build_picocalc.py', ROOT / 'tools/seal_picocalc.py',
                              *(p for folder in ('code', 'ports/picocalc', 'third_party/fatfs', 'third_party/core_math')
                                for p in (ROOT / folder).rglob('*')
                                if p.is_file() and (p.suffix in ('.c', '.cpp', '.h', '.hpp', '.S', '.inc', '.ld', '.pio')
                                                    or p.name == 'CMakeLists.txt'))]):
            source_hash.update(str(source.relative_to(ROOT)).encode() + b'\0')
            source_hash.update(source.read_bytes())
        if args.sampling_profile:
            source_hash.update(b'picocalc-sampling-profile=1\0')
        if args.compiler_runtime:
            source_hash.update(b'picocalc-compiler-runtime=1\0')
        if args.psram_spi:
            source_hash.update(b'picocalc-psram-qpi=0\0')
        source_digest = source_hash.hexdigest()
        build_digest = hashlib.sha256((source_digest + '\0' + (
            'gcc' if args.compiler_runtime else 'owned-m0')).encode()).hexdigest()
        build_id = '0x' + build_digest[:8] + 'U'
        run([cmake, "-S", ROOT / "ports/picocalc", "-B", build, "-G", "Ninja",
             "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
             f"-DCMAKE_MAKE_PROGRAM={ninja}", f"-DPICO_SDK_PATH={sdk}",
             f"-DPICO_TOOLCHAIN_PATH={toolchain}", f"-DPython3_EXECUTABLE={sys.executable}",
             f"-DMK61_PICOCALC_M0_EABI={'OFF' if args.compiler_runtime else 'ON'}",
             f"-DMK61_PICOCALC_PSRAM_QPI={'OFF' if args.psram_spi else 'ON'}",
             f"-DMK61_PICOCALC_BUILD_ID={build_id}",
             f"-DMK61_PICOCALC_SAMPLE_PROFILE={'ON' if args.sampling_profile else 'OFF'}"])
        run([cmake, "--build", build, "--parallel", args.jobs])
        suffix = ".exe" if os.name == "nt" else ""
        attributes = run([toolchain / ("arm-none-eabi-readelf" + suffix), "-A", build / (TARGET + ".elf")],
                         capture_output=True, text=True).stdout
        if "v6S-M" not in attributes or "VFP registers" in attributes:
            raise ValueError("ELF must target ARMv6-M with the soft-float ABI")
        image = (build / (TARGET + ".bin")).read_bytes()
        if len(image) > 2 * 1024 * 1024 - 8192:
            raise ValueError("Firmware overlaps the PicoCalc settings journal")
        from seal_picocalc import seal, verify, FOOTER, BASE, patch_elf_footer
        symbols=run([toolchain / ("arm-none-eabi-nm" + suffix),"--defined-only",build / (TARGET + ".elf")],capture_output=True,text=True).stdout
        ram_end=re.search(r'^([0-9a-fA-F]+) [A-Za-z] __end__$',symbols,re.M)
        if not ram_end:
            raise ValueError('required SRAM end symbol is missing')
        # GNU size classifies executable SRAM sections as text. Account for
        # the vector table, RAM code and alignment as well as data/BSS.
        static_ram_bytes=int(ram_end[1],16)-0x20000000
        if not 0 < static_ram_bytes <= 224 * 1024:
            raise ValueError('static SRAM overlaps the reserved stack region')
        match=re.search(r'^([0-9a-fA-F]+) [A-Za-z] mk61_picocalc_firmware_footer$',symbols,re.M)
        if not match:raise ValueError('required firmware footer was discarded by the linker')
        footer_offset=int(match[1],16)-BASE
        image=seal(image,footer_offset)
        integrity=verify(image,footer_offset)
        sys.path.insert(0, str(ROOT / "ports/picocalc"))
        from uf2 import encode, validate
        transport = encode(image)
        validate(transport, image)
        output.mkdir(parents=True, exist_ok=True)
        shutil.copy2(build / (TARGET + ".elf.map"), output / (TARGET + ".elf.map"))
        footer_file=build/'sealed-footer.bin'
        footer_file.write_bytes(image[footer_offset:footer_offset+FOOTER.size])
        (output/(TARGET+'.elf')).write_bytes(patch_elf_footer(
            (build/(TARGET+'.elf')).read_bytes(),footer_file.read_bytes()))
        run([toolchain / ("arm-none-eabi-objcopy"+suffix),'-O','binary',output/(TARGET+'.elf'),output/(TARGET+'.bin')])
        if (output/(TARGET+'.bin')).read_bytes()!=image:
            raise ValueError('sealed ELF and BIN differ')
        (output / (TARGET + ".uf2")).write_bytes(transport)
        sizes = run([toolchain / ("arm-none-eabi-size" + suffix), "-B", build / (TARGET + ".elf")],
                    capture_output=True, text=True).stdout
        fields = sizes.splitlines()[-1].split()
        metadata = {
            "profile": args.profile, "prototype_version": re.search(r'VERSION\[\]\s*=\s*"(\d+\.\d+\.\d+)"',
                (ROOT / 'ports/picocalc/version.hpp').read_text())[1], "mcu": "RP2040",
            "sampling_profile": args.sampling_profile,
            "psram_bus": "spi" if args.psram_spi else "qpi-with-spi-fallback",
            "board": "ClockworkPi PicoCalc + Raspberry Pi Pico H", "cpu": "cortex-m0plus",
            "float_abi": "soft", "math": "compact_math + " + (
                "GCC IEEE float/double helpers" if args.compiler_runtime else "owned ARMv6-M IEEE runtime"),
            "arithmetic_runtime": "gcc" if args.compiler_runtime else "owned-m0",
            "pico_sdk": SDK_VERSION, "pico_sdk_commit": sdk_revision,
            "compiler": run([toolchain / ("arm-none-eabi-gcc" + suffix), "-dumpfullversion"],
                            capture_output=True, text=True).stdout.strip(),
            "flash_bytes": len(image), "flash_limit": 2 * 1024 * 1024,
            "static_ram_bytes": static_ram_bytes,
            "static_ram_data_bss_bytes": int(fields[1]) + int(fields[2]),
            "main_ram_region_bytes": 224 * 1024,
            "stack_reserved_bytes": 32 * 1024,
            "source_editor_capacity_bytes": 65534,
            "settings_flash_offset": 2 * 1024 * 1024 - 8192,
            "settings_flash_bytes": 8192,
            "uf2_bytes": len(transport),
            "bin_sha256": hashlib.sha256(image).hexdigest(),
            "uf2_sha256": hashlib.sha256(transport).hexdigest(),
            "hardware_verified": False,
            "source_sha256": source_digest, "build_id": build_digest[:8],
            "firmware_integrity": integrity,
        }
        (output / "manifest.json").write_text(json.dumps(metadata, indent=2) + "\n")
        print(sizes, end="")
        print(f"UF2: {output / (TARGET + '.uf2')}")
        print(f"Flash: {len(image)} / {metadata['flash_limit']} bytes; static RAM: {metadata['static_ram_bytes']} bytes")
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"PicoCalc build failed: {error}\n")


if __name__ == "__main__":
    main()
