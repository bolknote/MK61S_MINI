#!/usr/bin/env python3
"""Build Spectrum/Pentagon as an ordinary PicoCalc APP and prepare its SD folder."""

import sys as _repo_sys
from pathlib import Path as _RepoPath
_repo_sys.path.insert(0, str(_RepoPath(__file__).resolve().parents[3]))
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
from tools.apps.spectrum.fetch_spectrum_devices import prepare as prepare_devices
from tools.apps.spectrum.spectrum_rom_cache import prepare as prepare_rom_cache
from tools.apps.spectrum.build_spectrum_library import prepare as prepare_games
from tools.apps.spectrum.build_spectrum_m3 import build as build_sound_module

from tools.firmware.picocalc.build_picocalc import compiler_bin
from explorer_icons import copy_icon

ROOT = Path(__file__).resolve().parents[3]
SOURCES = ["examples/portable-apps/SPECTRUM/main.c",
           "examples/portable-apps/SPECTRUM/spectrum.c", "examples/portable-apps/SPECTRUM/memory.c",
           "examples/portable-apps/SPECTRUM/peripherals.c",
           "examples/portable-apps/SPECTRUM/fdc.c", "examples/portable-apps/SPECTRUM/spi.c",
           "examples/portable-apps/SPECTRUM/mapper.c",
           "examples/portable-apps/SPECTRUM/media.c",
           "examples/portable-apps/SPECTRUM/ui.c",
           "examples/portable-apps/SPECTRUM/rom_cache.c",
           "third_party/z80/z80.c", "third_party/emu2149/emu2149.c"]


def demo_snapshot(pentagon=False):
    """Original Z80 demo; IM2 interrupt handler, animated colors, ROM font."""
    ram = bytearray(49152)
    for y in range(192):
        at = ((y & 192) << 5) | ((y & 7) << 8) | ((y & 56) << 2)
        for x in range(32):
            ram[at + x] = 0xAA if (y // 8 + x) & 1 else 0x55
    for y in range(24):
        for x in range(32):
            ram[6144 + y * 32 + x] = 64 | (x & 7) | (((x + y + 1) & 7) << 3)
    font = (ROOT / "third_party/spectrum-rom/48.rom").read_bytes()[0x3D00:0x4000]
    for row, label in ((5, "PENTAGON 512K" if pentagon else "SPECTRUM 48K"), (8, "MK61S / PICOCALC APP"),
                       (12, "Z80 + COLOUR + SD"), (17, "ESC: MENU   F10: EXIT")):
        left = (32 - len(label)) // 2
        for x, char in enumerate(label, left):
            ram[6144 + row * 32 + x] = 0x47
            for line in range(8):
                y = row * 8 + line
                at = ((y & 192) << 5) | ((y & 7) << 8) | ((y & 56) << 2)
                ram[at + x] = font[(ord(char) - 32) * 8 + line]
    # DI; LD SP,FFFE; LD A,93; LD I,A; IM 2; EI; HALT; load counter;
    # border=counter&7; animate one attribute row; repeat.
    program = bytearray.fromhex("F3 31 FE FF 3E 93 ED 47 ED 5E")
    if pentagon:
        # Three tone generators, noise on C, and a repeating envelope on C.
        registers = [0xA2, 1, 0x4C, 1, 0x17, 1, 8, 0x18, 15, 13, 16, 128, 0, 10]
        for reg, value in enumerate(registers):
            program += bytes.fromhex("01 FD FF 3E") + bytes([reg]) + bytes.fromhex("ED 79 06 BF 3E") + bytes([value]) + bytes.fromhex("ED 79")
    program += b"\xFB"
    loop = 0x8000 + len(program)
    program += bytes.fromhex("76 3A 00 90 E6 07 D3 FE 21 00 58 06 20 77 23 3C 10 FB C3") + struct.pack("<H", loop)
    ram[0x4000:0x4000 + len(program)] = program
    handler = bytes.fromhex("F5 3A 00 90 3C 32 00 90 F1 FB ED 4D")
    ram[0x5090:0x5090 + len(handler)] = handler
    ram[0x5300:0x5401] = bytes([0x90]) * 257
    # SNA restores PC with RETN from the stack.
    ram[0xBFFC:0xBFFE] = struct.pack("<H", 0x8000)
    header = bytearray(27)
    struct.pack_into("<H", header, 23, 0xFFFC)
    header[25] = 1
    if pentagon:
        struct.pack_into("<H", header, 23, 0xFFFE)
        # 128K SNA: visible banks 5,2,0, explicit PC, then banks 1,3,4,6,7.
        return bytes(header + ram + struct.pack("<HBB", 0x8000, 16, 0) + bytes(5 * 16384))
    return bytes(header + ram)


def copy_assets(output):
    output.mkdir(parents=True, exist_ok=True)
    for name in ("48.rom", "128-0.rom", "128-1.rom"):
        shutil.copy2(ROOT / "third_party/spectrum-rom" / name, output / name)
    (output / "DEMO.sna").write_bytes(demo_snapshot())
    (output / "DEMO128.sna").write_bytes(demo_snapshot(True))
    shutil.copy2(ROOT / "examples/portable-apps/SPECTRUM/README.md", output / "README.md")
    shutil.copy2(ROOT / "examples/portable-apps/SPECTRUM/TEST-GAMES.md", output / "TEST-GAMES.md")
    licenses = output / "licenses"
    licenses.mkdir(exist_ok=True)
    shutil.copy2(ROOT / "third_party/z80/LICENSE", licenses / "z80-MIT.txt")
    shutil.copy2(ROOT / "third_party/emu2149/LICENSE", licenses / "emu2149-MIT.txt")
    shutil.copy2(ROOT / "third_party/spectrum-rom/README.copyright", licenses / "ROM-copyright.txt")
    copy_icon("applications",output / "autoexec.wbmp")
    copy_icon("license",licenses / "autoexec.wbmp")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain", type=Path)
    parser.add_argument("--build-dir", type=Path, default=ROOT / ".build/spectrum-app")
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".build/firmware/picocalc-pico-h/apps/SPECTRUM")
    parser.add_argument("--device-assets", type=Path, help="prepared folder from fetch_spectrum_devices.py")
    parser.add_argument("--fetch-devices", action="store_true", help="fetch pinned ROMs and create disk images")
    args = parser.parse_args()
    command = [sys.executable, str(ROOT / "tools/apps/portable/build_portable_app.py"),
               "--target", "picocalc-pico-h", "--shared-runtime", "--name", "SPECTRUM", "--handled-magic", "Z1",
               "--arm-toolchain-bin", str(compiler_bin(args.toolchain)),
               "--output-dir", str(args.build_dir)]
    for source in SOURCES:
        command += ["--source", str(ROOT / source)]
    subprocess.run(command, check=True)
    copy_assets(args.output_dir)
    sound_module=build_sound_module(args.build_dir/'m3',toolchain=args.toolchain,optimization='-O2',
        fast_init=120,slice_samples=16,step_budget_us=1250,init_budget_us=1250,silent_batch=True)
    shutil.copy2(sound_module['package'],args.output_dir/'AY.S3M')
    assets = args.device_assets
    if args.fetch_devices:
        assets = args.build_dir / "devices"
        prepare_devices(assets)
    if assets:
        for name in ("trdos.rom", "esxmmc.rom", "ESXDOS.img", "BLANK.trd", "devices.json"):
            shutil.copy2(assets / name, args.output_dir / name)
        shutil.copytree(assets / "licenses", args.output_dir / "licenses", dirs_exist_ok=True)
    rom_cache = prepare_rom_cache(args.output_dir)
    esxdos = assets / "esxdos089.zip" if assets else None
    prepare_games(args.output_dir / "games", esxdos if esxdos and esxdos.exists() else None)
    shutil.copy2(args.build_dir / "SPECTRUM.APP", args.output_dir / "SPECTRUM.APP")
    report = json.loads((args.build_dir / "SPECTRUM.json").read_text())
    report["sources"] = SOURCES
    report["app_sha256"] = hashlib.sha256((args.output_dir / "SPECTRUM.APP").read_bytes()).hexdigest()
    inputs = sorted(set(SOURCES) | {
        str(p.relative_to(ROOT)) for folder in ("examples/portable-apps/SPECTRUM", "third_party/z80", "third_party/emu2149")
        for p in (ROOT / folder).glob("*.h")})
    report["source_sha256"] = {source: hashlib.sha256((ROOT / source).read_bytes()).hexdigest() for source in inputs}
    report["hardware_verified"] = False
    report["rom_cache"] = rom_cache
    report["m3_sound_module"] = sound_module
    report["files"] = {str(p.relative_to(args.output_dir)): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in sorted(args.output_dir.rglob("*")) if p.is_file() and p.name != "manifest.json"}
    (args.output_dir / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Spectrum SD folder: " + str(args.output_dir))


if __name__ == "__main__":
    main()
