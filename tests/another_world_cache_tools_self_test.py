#!/usr/bin/env python3
"""Check native game-cache builders without downloading or distributing games."""
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/games"))
from another_cache import prepare


def compressed() -> bytes:
    bits = []
    def field(value: int, count: int) -> None:
        bits.extend((value >> bit) & 1 for bit in reversed(range(count)))
    field(0, 2); field(0, 3); field(ord("A"), 8)
    field(1, 1); field(2, 2); field(22, 8); field(1, 12)
    assert len(bits) == 36
    initial = 0x80000000 | sum(value << i for i, value in enumerate(bits[:31]))
    previous = sum(value << i for i, value in enumerate(bits[31:]))
    return struct.pack(">IIII", previous, initial, previous ^ initial, 24)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="another-cache-tools-") as tmp:
        folder = Path(tmp)
        listing = bytearray(41)
        listing[7] = listing[27] = 1
        listing[14:16] = listing[18:20] = (24).to_bytes(2, "big")
        listing[28:32] = (32).to_bytes(4, "big")
        listing[34:36] = (16).to_bytes(2, "big")
        listing[38:40] = (24).to_bytes(2, "big")
        listing[40] = 0xFF
        bank = bytearray(64)
        bank[:24] = bytes(range(1, 25)); bank[32:48] = compressed()
        (folder / "MEMLIST.BIN").write_bytes(listing)
        (folder / "BANK01").write_bytes(bank)
        assert prepare(folder) == (2, 48)
        expected = (folder / "AWCACHE.BIN").read_bytes()
        magic, version, count, length, _, table = struct.unpack_from("<4sIIIII", expected)
        assert (magic, version, count, length, table) == (b"AWC1", 1, 2, 41, 24)
        assert expected[48:72] == bank[:24] and expected[72:96] == b"A" * 24
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if shell:
            command = [shell, "-NoProfile", "-File", str(ROOT / "tools/games/games.ps1"),
                       "prepare-another", str(folder)]
            subprocess.run(command, check=True, capture_output=True)
            assert (folder / "AWCACHE.BIN").read_bytes() == expected
        bank[43] ^= 1
        (folder / "BANK01").write_bytes(bank)
        try:
            prepare(folder)
            raise AssertionError("corrupt compressed resource accepted")
        except ValueError:
            pass
        assert (folder / "AWCACHE.BIN").read_bytes() == expected
        if shell:
            result = subprocess.run(command, capture_output=True)
            assert result.returncode != 0
            assert (folder / "AWCACHE.BIN").read_bytes() == expected
        print("Cache builders: identical output and atomic rejection of corrupt input passed")


if __name__ == "__main__":
    main()
