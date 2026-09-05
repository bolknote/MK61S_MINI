#!/usr/bin/env python3
"""Exercise the actual packer and production reader, including damaged files."""
import argparse
import re
import struct
import subprocess
import tempfile
import zlib
from pathlib import Path


def run(command):
    return subprocess.run([str(x) for x in command], capture_output=True,
                          text=True, check=True).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packer", type=Path)
    parser.add_argument("reader", type=Path)
    parser.add_argument("legacy_reader", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="mk61-package-") as directory:
        work = Path(directory)
        resident = work / "resident.bin"
        resident.write_bytes(bytes(range(64)))
        image, app, memory = (work / x for x in ("image.bin", "test.APP", "memory.bin"))
        calls = bytearray()
        for offset in range(0, 1024, 4):
            target = ((1000 - offset - 4) >> 1) & 0x3FFFFF
            calls.extend(((target >> 11) & 255, 0xF0 | (target >> 19),
                          target & 255, 0xF8 | ((target >> 8) & 7)))
        fixtures = [(bytes(calls), "BCJ"), (bytes(1024), "tie"),
                    (bytes.fromhex("00f000f8") * 256, "plain")]
        for original, choice in fixtures:
            image.write_bytes(original)
            command = [args.packer, "--kind", "app", "--image", image,
                       "--memory-size", len(original) + 37, "--entry-offset", 0,
                       "--output", app]
            report = run([*command, "--portable"])
            match = re.search(r"plain=(\d+) BCJ=(\d+); selected=(\w+)", report)
            assert match, report
            plain, bcj = map(int, match.groups()[:2])
            assert {"BCJ": bcj < plain, "tie": bcj == plain,
                    "plain": plain < bcj}[choice], report
            packed = app.read_bytes()
            assert len(packed) == 64 + min(plain, bcj)
            assert packed[12:16] == bytes((3, 0, 4, 1))  # ABI, kind, ZX0
            assert struct.unpack_from("<III", packed, 16) == (
                3 if bcj < plain else 1, 0x20000000, min(plain, bcj))
            assert packed[40:48] == bytes(8)  # No resident binding.
            assert struct.unpack_from("<I", packed, 52)[0] == zlib.crc32(original)
            run([args.reader, app, memory])
            assert memory.read_bytes() == original + bytes(37)
            assert subprocess.run([str(args.legacy_reader), str(app), str(memory)]).returncode == 3

            if choice == "BCJ":
                good = packed

            # The legacy path still emits ABI 2 and decodes on both readers.
            run([*command, "--resident", resident, "--load-address", "0x20001000",
                 "--require-zx0"])
            legacy = app.read_bytes()
            assert legacy[12] == 2 and legacy[16:20] == bytes(4)
            for reader in (args.reader, args.legacy_reader):
                run([reader, app, memory])
                assert memory.read_bytes() == original + bytes(37)

        def reject(data):
            app.write_bytes(data)
            result = subprocess.run([str(args.reader), str(app), str(memory)])
            assert result.returncode in (3, 4), result.returncode

        def changed(offset, value, width=4):
            data = bytearray(good)
            data[offset:offset + width] = value.to_bytes(width, "little")
            struct.pack_into("<I", data, 60, zlib.crc32(data[:60]))
            return data

        # Every truncation, extraneous bytes, and CRC corruption are rejected.
        for size in range(len(good)):
            reject(good[:size])
        reject(good + b"\0")
        for offset in (0, 12, 16, 48, 52, 60, 64, len(good) - 1):
            damaged = bytearray(good)
            damaged[offset] ^= 1
            reject(damaged)
        # Valid header CRC must not let invalid ABI/flags/bounds through.
        for offset, value, width in ((12, 2, 2), (12, 4, 2), (16, 0, 4),
                (16, 2, 4), (16, 7, 4), (20, 0x20000008, 4),
                (32, 20481, 4), (36, 1024, 4), (40, 1, 4),
                (44, 1, 4), (48, 0, 4), (52, 0, 4), (58, 1, 2)):
            reject(changed(offset, value, width))
        # Omitting the inverse BCJ pass must fail the ORIGINAL image CRC.
        reject(changed(16, 1))
        trailing = bytearray(good + b"\0")
        struct.pack_into("<I", trailing, 24, len(trailing) - 64)
        struct.pack_into("<I", trailing, 48, zlib.crc32(trailing[64:]))
        struct.pack_into("<I", trailing, 60, zlib.crc32(trailing[:60]))
        reject(trailing)
    print("portable APP packages: BCJ/plain/tie selection, BSS, legacy and corruption PASS")


if __name__ == "__main__":
    main()
