#!/usr/bin/env python3
"""Copy the verified MK61 resident footer from a sealed BIN into its ELF.

The linker knows the load addresses recorded by ELF, while the resident image
CRC can only be calculated after objcopy has produced the final flat BIN.  This
tool joins those two post-link products: it patches the dedicated 40-byte
footer in the ELF, converts the result back to BIN with the target objcopy and
requires an exact byte-for-byte match with the already verified sealed BIN.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import stat
import struct
import subprocess
import tempfile
import zlib


MAGIC = b"MK61FWC\0"
VERSION = 1
FOOTER_SIZE = 40
IMAGE_START = 0x08000000
CRC_REQUIRED = 1
KNOWN_FLAGS = CRC_REQUIRED
FOOTER = struct.Struct("<8sHH7I")


class SealError(RuntimeError):
    pass


def footer_offsets(data: bytes) -> list[int]:
    result: list[int] = []
    cursor = 0
    while True:
        offset = data.find(MAGIC, cursor)
        if offset < 0:
            break
        cursor = offset + 1
        if offset + FOOTER_SIZE > len(data):
            continue
        fields = FOOTER.unpack_from(data, offset)
        if (fields[1] == VERSION and fields[2] == FOOTER_SIZE and
                fields[3] == IMAGE_START and offset % 4 == 0):
            result.append(offset)
    return result


def unique_footer(data: bytes, label: str) -> tuple[int, tuple]:
    offsets = footer_offsets(data)
    if not offsets:
        raise SealError(f"resident firmware footer not found in {label}")
    if len(offsets) != 1:
        raise SealError(f"multiple resident firmware footers in {label}")
    offset = offsets[0]
    return offset, FOOTER.unpack_from(data, offset)


def canonical_crc(data: bytes, footer: int) -> int:
    canonical = bytearray(data)
    canonical[footer + 20:footer + 28] = b"\0" * 8
    return zlib.crc32(canonical) & 0xFFFFFFFF


def validate_bin(data: bytes, offset: int, fields: tuple) -> None:
    (_magic, _version, _size, _start, image_size, expected_crc, build_id,
     profile_id, flags, reserved) = fields
    if image_size != len(data):
        raise SealError("resident footer image size does not match BIN")
    if not profile_id:
        raise SealError("resident footer has an invalid profile identity")
    if not (flags & CRC_REQUIRED):
        raise SealError("resident BIN was not compiled with CRC required")
    if flags & ~KNOWN_FLAGS or reserved:
        raise SealError("resident footer has unsupported flags/reserved data")
    actual = canonical_crc(data, offset)
    if not expected_crc or actual != expected_crc:
        raise SealError("resident firmware CRC mismatch")
    if build_id != expected_crc:
        raise SealError("resident firmware build identity mismatch")


def verify_pair(bin_fields: tuple, elf_fields: tuple) -> None:
    # Magic/version/size/start and profile/flags/reserved are fixed by the
    # same link.  image_size/CRC/build are the three post-link values copied
    # below.
    for index in (0, 1, 2, 3, 7, 8, 9):
        if bin_fields[index] != elf_fields[index]:
            raise SealError("BIN and ELF resident footers do not match")


def run_objcopy(objcopy: Path, elf: Path, output: Path) -> None:
    command = [str(objcopy), "-O", "binary", str(elf), str(output)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        suffix = f": {detail}" if detail else ""
        raise SealError(f"{objcopy.name} failed with exit code "
                        f"{result.returncode}{suffix}")


def objcopy_from_database(path: Path) -> Path:
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SealError(f"cannot read compile database {path}: {error}")
    for entry in entries:
        arguments = entry.get("arguments")
        if arguments:
            compiler = str(arguments[0])
        else:
            command = entry.get("command", "")
            parts = shlex.split(command, posix=os.name != "nt") \
                if command else []
            compiler = parts[0].strip('"') if parts else ""
        resolved = shutil.which(compiler) or compiler
        if not resolved or not Path(resolved).is_file():
            continue
        suffix = ".exe" if Path(resolved).suffix.lower() == ".exe" else ""
        candidate = Path(resolved).resolve().parent / \
            ("arm-none-eabi-objcopy" + suffix)
        if candidate.is_file():
            return candidate
    raise SealError(f"ARM objcopy is missing from compile database: {path}")


def seal(bin_path: Path, elf_path: Path, output_path: Path,
         objcopy: Path) -> None:
    bin_data = bin_path.read_bytes()
    elf_data = elf_path.read_bytes()
    bin_offset, bin_fields = unique_footer(bin_data, "BIN")
    elf_offset, elf_fields = unique_footer(elf_data, "ELF")
    validate_bin(bin_data, bin_offset, bin_fields)
    verify_pair(bin_fields, elf_fields)

    patched = bytearray(elf_data)
    # image_size, expected_crc32 and build_id occupy bytes 16..27.
    patched[elf_offset + 16:elf_offset + 28] = \
        bin_data[bin_offset + 16:bin_offset + 28]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    source_mode = stat.S_IMODE(elf_path.stat().st_mode)
    temporary_elf: Path | None = None
    temporary_bin: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
                prefix=output_path.name + ".", suffix=".tmp",
                dir=output_path.parent, delete=False) as stream:
            stream.write(patched)
            temporary_elf = Path(stream.name)
        os.chmod(temporary_elf, source_mode)
        with tempfile.NamedTemporaryFile(
                prefix=output_path.name + ".verify.", suffix=".bin",
                dir=output_path.parent, delete=False) as stream:
            temporary_bin = Path(stream.name)
        run_objcopy(objcopy, temporary_elf, temporary_bin)
        rebuilt = temporary_bin.read_bytes()
        if rebuilt != bin_data:
            limit = min(len(rebuilt), len(bin_data))
            mismatch = next((index for index in range(limit)
                             if rebuilt[index] != bin_data[index]), limit)
            raise SealError(
                "sealed ELF does not reproduce sealed BIN exactly "
                f"(first mismatch {mismatch}, ELF BIN {len(rebuilt)} bytes, "
                f"expected {len(bin_data)} bytes)")
        os.replace(temporary_elf, output_path)
        temporary_elf = None
    finally:
        for temporary in (temporary_elf, temporary_bin):
            if temporary is not None:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass

    print("resident firmware ELF: sealed "
          f"size={len(bin_data)} footer={bin_offset} "
          f"crc={bin_fields[5]:08X} profile={bin_fields[7]:08X}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bin", type=Path, required=True,
                        help="verified sealed resident BIN")
    parser.add_argument("--elf", type=Path, required=True,
                        help="matching linked resident ELF")
    parser.add_argument("--output", type=Path,
                        help="sealed ELF (defaults to patching --elf in place)")
    tools = parser.add_mutually_exclusive_group(required=True)
    tools.add_argument("--objcopy", type=Path,
                       help="matching arm-none-eabi-objcopy executable")
    tools.add_argument("--compile-commands", type=Path,
                       help="compile_commands.json used to locate objcopy")
    args = parser.parse_args()
    output = args.output or args.elf
    try:
        for path, label in ((args.bin, "BIN"), (args.elf, "ELF")):
            if not path.is_file():
                raise SealError(f"{label} not found: {path}")
        objcopy = args.objcopy
        if objcopy is None:
            if not args.compile_commands.is_file():
                raise SealError(
                    f"compile database not found: {args.compile_commands}")
            objcopy = objcopy_from_database(args.compile_commands.resolve())
        if not objcopy.is_file():
            raise SealError(f"objcopy not found: {objcopy}")
        seal(args.bin.resolve(), args.elf.resolve(), output.resolve(),
             objcopy.resolve())
    except (OSError, SealError) as error:
        parser.exit(2, f"seal-firmware-elf: {error}\n")


if __name__ == "__main__":
    main()
