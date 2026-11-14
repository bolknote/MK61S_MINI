#!/usr/bin/env python3
"""Build the experimental Another World mono PCM coprocessor module."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import zlib

ROOT = Path(__file__).resolve().parents[3]
RUNTIME = ROOT / "sdk/coproc"
sys.path[:0] = [str(ROOT), str(RUNTIME)]
from elf32 import ELF
from tools.firmware.picocalc.build_picocalc import compiler_bin


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain", type=Path)
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".build/another-app/m3")
    args = parser.parse_args()
    tools = compiler_bin(args.toolchain)
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    source = ROOT / "examples/portable-apps/ANOTHER/m3_pcm.c"
    elf, binary, package = (out / name for name in ("AWPCM.elf", "AWPCM.bin", "AWPCM.S3M"))
    subprocess.run([str(tools / "arm-none-eabi-gcc"), "-mcpu=cortex-m3", "-mthumb", "-mfloat-abi=soft",
                    "-std=c11", "-O2", "-g", "-mword-relocations", "-ffreestanding", "-fno-builtin",
                    "-fno-common", "-fno-stack-protector", "-fno-unwind-tables", "-fno-asynchronous-unwind-tables",
                    "-ffunction-sections", "-fdata-sections", "-Wall", "-Wextra", "-Werror", "-I" + str(RUNTIME),
                    "-nostdlib", str(source), "-Wl,-T," + str(RUNTIME / "module.ld"),
                    "-Wl,--emit-relocs,--gc-sections,-Map=" + str(out / "AWPCM.map"), "-o", str(elf)], check=True)
    subprocess.run([str(tools / "arm-none-eabi-objcopy"), "-O", "binary", "-j", ".image", str(elf), str(binary)], check=True)
    parsed = ELF(elf)
    image = binary.read_bytes()
    memory = parsed.symbols["__memory_end"]["value"] - 0x20000000
    relocations = []
    for address, kind in parsed.relocations():
        if kind == 2:
            relocations.append(address - 0x20000000)
        elif kind not in (3, 10, 30, 42):
            raise ValueError("Unsupported M3 relocation " + str(kind))
    relocations = sorted(set(relocations))
    if memory > 6144 or len(relocations) > 64 or memory < len(image):
        raise ValueError("M3 image exceeds resident limits")
    for offset in relocations:
        if offset % 4 or offset + 4 > len(image) or not 0x20000000 <= struct.unpack_from("<I", image, offset)[0] <= 0x20000000 + memory:
            raise ValueError("Invalid image relocation")
    if any(symbol["index"] == 0 for symbol in parsed.symbols.values()):
        raise ValueError("Undefined M3 module symbol")
    payload = image + b"".join(struct.pack("<I", offset) for offset in relocations)
    words = [0x314D3353, 1, 64, 64 + len(payload), len(image), memory - len(image),
             parsed.entry - 0x20000000, len(relocations), 512, 512, 512, 2000,
             zlib.crc32(payload), 0, 0x70301]
    header = struct.pack("<15I", *words)
    package.write_bytes(header + struct.pack("<I", zlib.crc32(header)) + payload)
    report = {"package": str(package), "sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
              "image_bytes": len(image), "memory_bytes": memory, "memory_limit": 6144,
              "relocations": relocations, "maximum_frames": 64,
              "integrated": False, "hardware_verified": False}
    (out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
