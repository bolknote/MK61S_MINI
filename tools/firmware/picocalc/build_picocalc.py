#!/usr/bin/env python3
"""Build the isolated PicoCalc/Pico H prototype with the shared MK61S core."""

# Resolve shared host helpers independently of the current command directory.
import sys as _tool_sys
from pathlib import Path as _ToolPath
_tool_root = _ToolPath(__file__).resolve().parents[3]
_tool_sys.path[:0] = [str(_tool_root), str(_tool_root / "dev/lib"), str(_tool_root / "dev/tools")]
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
SDK_VERSION = "2.2.0"
SDK_COMMIT = "a1438dff1d38bd9c65dbd693f0e5db4b9ae91779"
TARGET = "mk61s-picocalc-pico-h"
FIRMWARE_FLASH_LIMIT = 0x1C0000


def firmware_flash_budget(image_bytes):
    # Spectrum ROM assets persist above this address across firmware updates.
    if not 0 < image_bytes <= FIRMWARE_FLASH_LIMIT:
        raise ValueError("Firmware overlaps the persistent Spectrum ROM cache at 0x101C0000")


def audio_memory_budget(static_ram_bytes, enabled):
    # Full48KiB APP + two15KiB fixed banks + two8KiB cache leases.
    # Include4KiB for native/shared allocations and8KiB growth headroom.
    minimum = (48 + 30 + 16 + 4 + 8) * 1024
    available = 224 * 1024 - static_ram_bytes
    if enabled and available < minimum:
        raise ValueError(f"real-time audio APP SRAM budget: heap {available} < required {minimum} bytes")
    return {"minimum_heap_bytes": minimum if enabled else None,
            "heap_capacity_bytes": available}


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
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".build/firmware/picocalc-pico-h")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--compiler-runtime", action="store_true",
                        help="Control build using GCC arithmetic instead of the owned M0 runtime")
    parser.add_argument("--sampling-profile", action="store_true", help="Build diagnostic-only core 0 PC sampling")
    parser.add_argument("--psram-spi", action="store_true", help="Control build without four-bit PSRAM")
    parser.add_argument("--cosmic-clock-diagnostic", action="store_true", help="Prepare temporary125/200/250MHz diagnostic image")
    parser.add_argument("--ai-overclock-diagnostic", action="store_true", help="AI diagnostic at qualified270MHz; stock voltage")
    parser.add_argument("--ai-fast-clock", action=argparse.BooleanOptionalAction, default=True,
                        help="Enable qualified270MHz during ordinary AI generation")
    parser.add_argument("--ai-fast-math", action=argparse.BooleanOptionalAction, default=True,
                        help="Use measured AI-only math backends with the project runtime")
    parser.add_argument("--ai-psram-late-read", action="store_true",
                        help="Experimental33.3MHz PSRAM reads with later PIO sampling; not hardware qualified")
    parser.add_argument("--audio-clock", action=argparse.BooleanOptionalAction, default=True,
                        help="Use200MHz while a real-time APP synth runs; restore125MHz on close")
    parser.add_argument("--audio-dma", action=argparse.BooleanOptionalAction, default=False,
                        help="Build block-DMA synthesis candidate for hardware qualification")
    parser.add_argument("--m0-libc-candidate", type=int, choices=(0,1,2,4,8,16), default=0,
                        help="Diagnostic eight-function libc candidate; no hardware winner is implied")
    parser.add_argument("--lcd-color-chain", action=argparse.BooleanOptionalAction, default=True,
                        help="Use strip DMA and constant RGB565 fills; disable for a control build")
    parser.add_argument("--lcd-spi-hz", type=int, default=12500000,
                        help="Requested LCD SPI clock, rounded down by SDK (24MHz is experimental)")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    if not 1 <= args.lcd_spi_hz <= 62500000:
        parser.error("--lcd-spi-hz must be from 1 to 62500000")
    if args.ai_psram_late_read and (args.psram_spi or not (args.ai_fast_clock or args.ai_overclock_diagnostic)):
        parser.error("--ai-psram-late-read requires QPI and AI270MHz support")
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
        for source in sorted([ROOT / 'tools/firmware/picocalc/build_picocalc.py', ROOT / 'dev/lib/seal_picocalc.py',
                              *(p for folder in ('code', 'ports/picocalc', 'sdk/coproc', 'third_party/fatfs', 'third_party/core_math')
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
        if args.cosmic_clock_diagnostic: source_hash.update(b"cosmic-clock-diagnostic=1\0")
        ai_clock_support=args.ai_fast_clock or args.ai_overclock_diagnostic
        if ai_clock_support: source_hash.update(b"ai-clock270=1\0")
        ai_fast_math = args.ai_fast_math and not args.compiler_runtime
        source_hash.update(f"ai-fast-math={int(ai_fast_math)}\0".encode())
        if args.ai_psram_late_read: source_hash.update(b"ai-psram-late-read=1\0")
        if args.audio_clock and not args.cosmic_clock_diagnostic and not ai_clock_support: source_hash.update(b"audio-clock=200\0")
        if args.audio_dma: source_hash.update(b"audio-dma=1\0")
        if args.m0_libc_candidate: source_hash.update(f"m0-libc-candidate={args.m0_libc_candidate}\0".encode())
        source_hash.update(f"lcd-color-chain={int(args.lcd_color_chain)}\0lcd-spi-request={args.lcd_spi_hz}\0".encode())
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
             f"-DMK61_PICOCALC_COSMIC_CLOCK_DIAG={'ON' if args.cosmic_clock_diagnostic else 'OFF'}",
             f"-DMK61_PICOCALC_AI_OVERCLOCK={'ON' if ai_clock_support else 'OFF'}",
             f"-DMK61_PICOCALC_AI_FAST_MATH={'ON' if ai_fast_math else 'OFF'}",
             f"-DMK61_PICOCALC_AI_PSRAM_LATE_READ={'ON' if args.ai_psram_late_read else 'OFF'}",
             f"-DMK61_PICOCALC_AUDIO_CLOCK={'ON' if args.audio_clock else 'OFF'}",
             f"-DMK61_PICOCALC_AUDIO_DMA={'ON' if args.audio_dma else 'OFF'}",
             f"-DMK61_PICOCALC_M0_LIBC_CANDIDATE={args.m0_libc_candidate}",
             f"-DMK61_PICOCALC_LCD_COLOR_CHAIN={'ON' if args.lcd_color_chain else 'OFF'}",
             f"-DMK61_PICOCALC_LCD_SPI_HZ={args.lcd_spi_hz}",
             f"-DMK61_PICOCALC_SAMPLE_PROFILE={'ON' if args.sampling_profile else 'OFF'}"])
        run([cmake, "--build", build, "--parallel", args.jobs])
        suffix = ".exe" if os.name == "nt" else ""
        attributes = run([toolchain / ("arm-none-eabi-readelf" + suffix), "-A", build / (TARGET + ".elf")],
                         capture_output=True, text=True).stdout
        if "v6S-M" not in attributes or "VFP registers" in attributes:
            raise ValueError("ELF must target ARMv6-M with the soft-float ABI")
        image = (build / (TARGET + ".bin")).read_bytes()
        firmware_flash_budget(len(image))
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
        foreground_budget=audio_memory_budget(static_ram_bytes,args.audio_clock and not args.cosmic_clock_diagnostic)
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
            "automatic_audio_clock_mhz": 200 if args.audio_clock and not args.cosmic_clock_diagnostic and not ai_clock_support else None,
            "ai_overclock_diagnostic": args.ai_overclock_diagnostic,
            "ai_fast_clock": ai_clock_support,
            "ai_fast_math": ai_fast_math,
            "ai_psram_late_read": args.ai_psram_late_read,
            "block_audio_dma": args.audio_dma,
            "m0_libc_candidate": args.m0_libc_candidate,
            "lcd_color_chain": args.lcd_color_chain,
            "lcd_spi_requested_hz": args.lcd_spi_hz,
            "psram_bus": "spi" if args.psram_spi else "qpi-with-spi-fallback",
            "board": "ClockworkPi PicoCalc + Raspberry Pi Pico H", "cpu": "cortex-m0plus",
            "float_abi": "soft", "math": "compact_math + " + (
                "GCC IEEE float/double helpers" if args.compiler_runtime else "owned ARMv6-M IEEE runtime"),
            "arithmetic_runtime": "gcc" if args.compiler_runtime else "owned-m0",
            "pico_sdk": SDK_VERSION, "pico_sdk_commit": sdk_revision,
            "compiler": run([toolchain / ("arm-none-eabi-gcc" + suffix), "-dumpfullversion"],
                            capture_output=True, text=True).stdout.strip(),
            "flash_bytes": len(image), "flash_limit": FIRMWARE_FLASH_LIMIT,
            "static_ram_bytes": static_ram_bytes,
            "foreground_memory_budget": foreground_budget,
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
        from program_collection import compiled_pico_features, pico_capabilities
        program_cap = pico_capabilities(metadata, output / (TARGET + '.uf2'),
                                        compiled_pico_features(build / 'compile_commands.json'))
        (output / 'program-capabilities.json').write_text(json.dumps(program_cap, indent=2) + '\n')
        print(sizes, end="")
        print(f"UF2: {output / (TARGET + '.uf2')}")
        print(f"Flash: {len(image)} / {metadata['flash_limit']} bytes; static RAM: {metadata['static_ram_bytes']} bytes")
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"PicoCalc build failed: {error}\n")


if __name__ == "__main__":
    main()
