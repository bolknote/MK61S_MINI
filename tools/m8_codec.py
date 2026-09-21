#!/usr/bin/env python3
"""Strict host-side codec for the MK-61S single-byte M8 text format."""

from __future__ import annotations

import argparse
from pathlib import Path


SPECIAL_TO_BYTE = {
    "←": 0x0E,
    "→": 0x0F,
    "↑": 0x10,
    "↓": 0x11,
    "π": 0x12,
    "√": 0x13,
    "↻": 0x14,
    "≠": 0x15,
    "≤": 0x16,
    "≥": 0x17,
    "×": 0x18,
    "÷": 0x19,
    "²": 0x1A,
    "ʸ": 0x1B,
    "ˣ": 0x1C,
    "⊻": 0x1D,
    "⁻": 0x1E,
    "↵": 0x1F,
}
BYTE_TO_SPECIAL = {value: key for key, value in SPECIAL_TO_BYTE.items()}


def valid_byte(byte: int) -> bool:
    return byte in (9, 10, 13) or 0x0E <= byte <= 0x7E or (
        byte >= 0x80 and byte != 0x98
    )


def encode(text: str) -> bytes:
    """Encode Unicode to M8 or raise UnicodeEncodeError."""
    result = bytearray()
    for offset, character in enumerate(text):
        special = SPECIAL_TO_BYTE.get(character)
        if special is not None:
            result.append(special)
            continue
        try:
            encoded = character.encode("cp1251")
        except UnicodeEncodeError as error:
            raise UnicodeEncodeError(
                "m8", text, offset, offset + 1,
                f"character {character!r} is not representable in M8",
            ) from error
        if len(encoded) != 1 or not valid_byte(encoded[0]):
            raise UnicodeEncodeError(
                "m8", text, offset, offset + 1,
                f"character {character!r} has no M8 assignment",
            )
        result.extend(encoded)
    return bytes(result)


def decode(data: bytes) -> str:
    """Decode strict M8 to Unicode or raise UnicodeDecodeError."""
    output: list[str] = []
    for offset, byte in enumerate(data):
        special = BYTE_TO_SPECIAL.get(byte)
        if special is not None:
            output.append(special)
            continue
        if not valid_byte(byte):
            raise UnicodeDecodeError(
                "m8", data, offset, offset + 1,
                f"byte 0x{byte:02x} has no M8 assignment",
            )
        output.append(bytes((byte,)).decode("cp1251"))
    return "".join(output)


def encode_file(source: Path, output: Path) -> None:
    text = source.read_text(encoding="utf-8-sig")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(encode(text))


def decode_file(source: Path, output: Path) -> None:
    text = decode(source.read_bytes())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("encode", "decode", "check"))
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path, nargs="?")
    args = parser.parse_args()
    try:
        if args.mode == "encode":
            if args.output is None:
                parser.error("encode requires OUTPUT")
            encode_file(args.source, args.output)
        elif args.mode == "decode":
            if args.output is None:
                parser.error("decode requires OUTPUT")
            decode_file(args.source, args.output)
        else:
            encode(args.source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError) as error:
        parser.exit(1, f"M8 conversion: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
