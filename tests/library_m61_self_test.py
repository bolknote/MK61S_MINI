#!/usr/bin/env python3
"""Verify the former resident programs and their initial state exactly."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "programs" / "library"
HIN = re.compile(r"hin ([0-9]{4}) ([0-9A-F]{2,})")


def hex_bytes(text: str) -> bytes:
    return bytes.fromhex(text)


EXPECTED_CODE = {
    "Factorial.m61": hex_bytes("34 40 01 60 12 5D 03 50"),
    "Double interpolation.m61": hex_bytes("00 47 61 0E 64 11 0E 69 0E 68 11 0E 25 25 25 12 40 69 0E 6A 11 0E 61 0E 6B 11 0E 25 25 25 12 0E 65 12 0E 67 10 47 6A 0E 68 11 0E 61 0E 6B 11 0E 25 25 25 12 0E 66 12 0E 67 10 47 69 0E 6A 11 0E 6B 0E 64 11 0E 25 25 25 12 0E 62 12 0E 67 10 47 6A 0E 68 11 0E 6B 0E 64 11 0E 25 25 25 12 0E 63 12 0E 67 10 47 0E 60 13 50"),
    "Prime numbers.m61": hex_bytes("44 D4 64 21 01 10 40 47 D7 14 67 11 5D 18 64 50 51 00 5E 22 51 01 64 60 13 51 07"),
    "Compute e.m61": hex_bytes("0D 06 05 0E 07 15 0E 60 53 81 40 61 53 81 41 62 53 81 42 63 53 81 43 64 53 81 44 65 53 81 45 66 53 81 46 67 53 81 47 68 53 81 48 69 53 81 49 6A 53 81 4A 6B 53 81 4B 6C 53 81 4C 6D 53 81 4D 6E 53 81 4E 25 25 01 11 5E 04 60 07 15 13 01 10 40 50 14 25 10 14 0E 0F 14 13 34 0E 25 14 12 0F 25 11 06 15 12 14 52"),
    "Decimal to natural.m61": hex_bytes("40 41 34 43 01 42 46 00 45 61 35 23 41 61 34 63 12 62 10 44 61 34 66 12 65 10 47 63 42 64 43 66 45 67 46 64 67 13 60 11 31 69 11 5C 09 67 64 50 51 00"),
    "Power from U and R.m61": hex_bytes("08 0A 05 04 04 06 06 06 03 4E 0D 50 22 08 0A 02 04 04 07 09 07 07 0C 06 03 4E 0D 50 14 25 13 08 0A 07 04 04 06 06 08 04 0C 06 01 4E 14 50"),
}

EXPECTED_INITIALIZERS = {
    "Factorial.m61": [],
    "Double interpolation.m61": [
        "R1= 40", "R2= 800", "R3= 1000", "R4= 20", "R5= 500",
        "R6= 600", "R8= 300", "R9= 1000", "RA= 800", "RB= 22",
    ],
    "Prime numbers.m61": [],
    "Compute e.m61": [],
    "Decimal to natural.m61": ["R9= 1e-7"],
    "Power from U and R.m61": [],
}


def parse(path: Path) -> tuple[list[str], bytes]:
    raw = path.read_bytes()
    assert len(raw) <= 1536, f"{path.name}: exceeds M61 storage limit"
    text = raw.decode("ascii")
    lines = text.splitlines()
    assert lines and lines[0] == "reinit", f"{path.name}: must start cleanly"
    assert "measure" not in lines, f"{path.name}: obsolete timing command remains"
    assert all(len(line) <= 239 for line in lines), f"{path.name}: line too long"

    initializers = []
    program = bytearray()
    saw_hin = False
    for line in lines[1:]:
        if line.startswith("R"):
            assert not saw_hin, f"{path.name}: register setup must precede code"
            initializers.append(line)
            continue
        match = HIN.fullmatch(line)
        assert match, f"{path.name}: unexpected command {line!r}"
        saw_hin = True
        address = int(match.group(1), 10)
        payload = bytes.fromhex(match.group(2))
        assert payload and len(payload) <= 24, f"{path.name}: invalid HIN chunk"
        assert address == len(program), f"{path.name}: non-contiguous HIN address"
        program.extend(payload)
    return initializers, bytes(program)


def main() -> None:
    files = {path.name for path in LIBRARY.iterdir() if path.is_file()}
    assert files == set(EXPECTED_CODE), (
        f"library contents differ: missing={set(EXPECTED_CODE) - files}, "
        f"extra={files - set(EXPECTED_CODE)}"
    )
    for name, expected_code in EXPECTED_CODE.items():
        initializers, code = parse(LIBRARY / name)
        assert initializers == EXPECTED_INITIALIZERS[name], (
            f"{name}: migrated register setup differs"
        )
        assert code == expected_code, f"{name}: migrated bytes differ"
    print("library_m61_self_test: ok")


if __name__ == "__main__":
    main()
