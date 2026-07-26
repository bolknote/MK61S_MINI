#!/usr/bin/env python3
"""Small, dependency-free assembler for base CHIP-8 ROMs.

The syntax is intentionally narrow: it covers the original CHIP-8 instruction
set, labels, integer constants, byte data, compact 3x5 text and ASCII bitmaps
whose width is a multiple of eight. It is used to keep the ECHO-8 example
readable and reproducible.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
import re
import sys


ROM_ADDRESS = 0x200
MAX_ROM_SIZE = 3584
GLYPHS = " ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-"


class AssemblyError(Exception):
    pass


@dataclass
class Statement:
    kind: str
    line: int
    value: object
    address: int = 0


def strip_comment(line: str) -> str:
    quoted = False
    escaped = False
    for index, character in enumerate(line):
        if escaped:
            escaped = False
        elif character == "\\" and quoted:
            escaped = True
        elif character == '"':
            quoted = not quoted
        elif character == ";" and not quoted:
            return line[:index]
    return line


def parse_string(text: str, line: int) -> str:
    try:
        value = ast.literal_eval(text)
    except (SyntaxError, ValueError) as error:
        raise AssemblyError(f"line {line}: invalid string: {error}") from error
    if not isinstance(value, str):
        raise AssemblyError(f"line {line}: expected a quoted string")
    return value


def split_operands(text: str) -> list[str]:
    if not text.strip():
        return []
    return [part.strip() for part in text.split(",")]


def parse_source(path: Path) -> tuple[list[Statement], dict[str, int]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    statements: list[Statement] = []
    constants: dict[str, int] = {}
    index = 0

    while index < len(lines):
        line_number = index + 1
        text = strip_comment(lines[index]).strip()
        index += 1
        if not text:
            continue

        constant = re.fullmatch(
            r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)", text
        )
        if constant:
            name, expression = constant.groups()
            constants[name] = evaluate(expression, constants, line_number)
            continue

        while True:
            label = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):", text)
            if not label:
                break
            statements.append(Statement("label", line_number, label.group(1)))
            text = text[label.end() :].strip()
            if not text:
                break
        if not text:
            continue

        bitmap_directive = re.fullmatch(r"\.bitmap([1-9][0-9]*)", text.lower())
        if bitmap_directive:
            width = int(bitmap_directive.group(1))
            if width % 8 != 0:
                raise AssemblyError(
                    f"line {line_number}: bitmap width must be a multiple of 8"
                )
            rows: list[str] = []
            while index < len(lines):
                bitmap_line_number = index + 1
                row = strip_comment(lines[index]).strip()
                index += 1
                if row.lower() == ".end":
                    break
                if not row:
                    continue
                if row.startswith('"'):
                    row = parse_string(row, bitmap_line_number)
                if len(row) != width or any(pixel not in ".#" for pixel in row):
                    raise AssemblyError(
                        f"line {bitmap_line_number}: bitmap rows must contain "
                        f"exactly {width} '.' or '#' pixels"
                    )
                rows.append(row)
            else:
                raise AssemblyError(
                    f"line {line_number}: unterminated .bitmap{width} block"
                )
            if not rows:
                raise AssemblyError(f"line {line_number}: empty bitmap")
            statements.append(Statement("bitmap", line_number, (width, rows)))
            continue

        directive, separator, payload = text.partition(" ")
        directive = directive.lower()
        if directive == ".byte":
            values = split_operands(payload if separator else "")
            if not values:
                raise AssemblyError(f"line {line_number}: empty .byte")
            statements.append(Statement("bytes", line_number, values))
            continue
        if directive == ".glyphs":
            value = parse_string(payload.strip(), line_number)
            unknown = sorted(set(value) - set(GLYPHS))
            if unknown:
                raise AssemblyError(
                    f"line {line_number}: unsupported glyphs: {unknown!r}"
                )
            statements.append(Statement("glyphs", line_number, value))
            continue
        if directive == ".align":
            statements.append(
                Statement("align", line_number, payload.strip())
            )
            continue
        if directive.startswith("."):
            raise AssemblyError(
                f"line {line_number}: unknown directive {directive}"
            )

        mnemonic, _, operands = text.partition(" ")
        statements.append(
            Statement(
                "instruction",
                line_number,
                (mnemonic.lower(), split_operands(operands)),
            )
        )

    return statements, constants


def evaluate(
    expression: str, symbols: dict[str, int], line: int | None = None
) -> int:
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as error:
        prefix = f"line {line}: " if line else ""
        raise AssemblyError(f"{prefix}invalid expression {expression!r}") from error

    def visit(node: ast.AST) -> int:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in symbols:
                raise AssemblyError(f"unknown symbol {node.id!r}")
            return symbols[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(
            node.op, (ast.UAdd, ast.USub)
        ):
            value = visit(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp) and isinstance(
            node.op, (ast.Add, ast.Sub, ast.Mult)
        ):
            left = visit(node.left)
            right = visit(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            return left * right
        raise AssemblyError(f"unsupported expression {expression!r}")

    try:
        return visit(tree)
    except AssemblyError as error:
        prefix = f"line {line}: " if line else ""
        raise AssemblyError(f"{prefix}{error}") from error


def statement_size(
    statement: Statement, address: int, symbols: dict[str, int]
) -> int:
    if statement.kind == "instruction":
        return 2
    if statement.kind == "bytes":
        return len(statement.value)  # type: ignore[arg-type]
    if statement.kind == "glyphs":
        return len(statement.value)  # type: ignore[arg-type]
    if statement.kind == "bitmap":
        width, rows = statement.value  # type: ignore[misc]
        return len(rows) * (width // 8)
    if statement.kind == "align":
        alignment = evaluate(str(statement.value), symbols, statement.line)
        if alignment <= 0:
            raise AssemblyError(
                f"line {statement.line}: alignment must be positive"
            )
        return (-address) % alignment
    return 0


def register(token: str, line: int) -> int:
    match = re.fullmatch(r"[vV]([0-9a-fA-F])", token)
    if not match:
        raise AssemblyError(f"line {line}: expected V0..VF, got {token!r}")
    return int(match.group(1), 16)


def checked(value: int, maximum: int, description: str, line: int) -> int:
    if value < 0 or value > maximum:
        raise AssemblyError(
            f"line {line}: {description} {value:#x} is outside 0..{maximum:#x}"
        )
    return value


def encode_instruction(
    mnemonic: str,
    operands: list[str],
    symbols: dict[str, int],
    line: int,
) -> int:
    def value(text: str, maximum: int, description: str) -> int:
        return checked(
            evaluate(text, symbols, line), maximum, description, line
        )

    if mnemonic == "cls" and not operands:
        return 0x00E0
    if mnemonic == "ret" and not operands:
        return 0x00EE
    if mnemonic in ("jp", "call") and len(operands) == 1:
        base = 0x1000 if mnemonic == "jp" else 0x2000
        return base | value(operands[0], 0xFFF, "address")
    if mnemonic in ("se", "sne") and len(operands) == 2:
        x = register(operands[0], line)
        if re.fullmatch(r"[vV][0-9a-fA-F]", operands[1]):
            y = register(operands[1], line)
            return (0x5000 if mnemonic == "se" else 0x9000) | x << 8 | y << 4
        return (
            (0x3000 if mnemonic == "se" else 0x4000)
            | x << 8
            | value(operands[1], 0xFF, "byte")
        )
    if mnemonic == "ld" and len(operands) == 2:
        left, right = operands
        if left.lower() == "i":
            return 0xA000 | value(right, 0xFFF, "address")
        if left.lower() == "dt":
            return 0xF015 | register(right, line) << 8
        if left.lower() == "st":
            return 0xF018 | register(right, line) << 8
        if left.lower() == "f":
            return 0xF029 | register(right, line) << 8
        if left.lower() == "b":
            return 0xF033 | register(right, line) << 8
        if left.lower() == "[i]":
            return 0xF055 | register(right, line) << 8
        x = register(left, line)
        lowered = right.lower()
        if lowered == "dt":
            return 0xF007 | x << 8
        if lowered == "k":
            return 0xF00A | x << 8
        if lowered == "[i]":
            return 0xF065 | x << 8
        if re.fullmatch(r"[vV][0-9a-fA-F]", right):
            return 0x8000 | x << 8 | register(right, line) << 4
        return 0x6000 | x << 8 | value(right, 0xFF, "byte")
    if mnemonic == "add" and len(operands) == 2:
        left, right = operands
        if left.lower() == "i":
            return 0xF01E | register(right, line) << 8
        x = register(left, line)
        if re.fullmatch(r"[vV][0-9a-fA-F]", right):
            return 0x8004 | x << 8 | register(right, line) << 4
        return 0x7000 | x << 8 | value(right, 0xFF, "byte")
    if mnemonic in ("or", "and", "xor", "sub", "subn"):
        if len(operands) != 2:
            raise AssemblyError(
                f"line {line}: {mnemonic} expects two registers"
            )
        low = {"or": 1, "and": 2, "xor": 3, "sub": 5, "subn": 7}[mnemonic]
        return (
            0x8000
            | register(operands[0], line) << 8
            | register(operands[1], line) << 4
            | low
        )
    if mnemonic in ("shr", "shl") and len(operands) == 1:
        return (
            0x8000
            | register(operands[0], line) << 8
            | (6 if mnemonic == "shr" else 0xE)
        )
    if mnemonic == "rnd" and len(operands) == 2:
        return (
            0xC000
            | register(operands[0], line) << 8
            | value(operands[1], 0xFF, "byte")
        )
    if mnemonic == "drw" and len(operands) == 3:
        return (
            0xD000
            | register(operands[0], line) << 8
            | register(operands[1], line) << 4
            | value(operands[2], 0xF, "sprite height")
        )
    if mnemonic in ("skp", "sknp") and len(operands) == 1:
        return (
            0xE09E if mnemonic == "skp" else 0xE0A1
        ) | register(operands[0], line) << 8
    raise AssemblyError(
        f"line {line}: unsupported instruction "
        f"{mnemonic} {' ,'.join(operands)}".rstrip()
    )


def assemble(path: Path) -> tuple[bytes, dict[str, int]]:
    statements, constants = parse_source(path)
    symbols = dict(constants)
    address = ROM_ADDRESS
    for statement in statements:
        statement.address = address
        if statement.kind == "label":
            name = str(statement.value)
            if name in symbols:
                raise AssemblyError(
                    f"line {statement.line}: duplicate symbol {name!r}"
                )
            symbols[name] = address
            continue
        address += statement_size(statement, address, symbols)
        if address > 0x1000:
            raise AssemblyError(
                f"line {statement.line}: program exceeds CHIP-8 memory"
            )

    output = bytearray()
    address = ROM_ADDRESS
    for statement in statements:
        if statement.kind == "label":
            continue
        if statement.kind == "instruction":
            mnemonic, operands = statement.value  # type: ignore[misc]
            opcode = encode_instruction(
                mnemonic, operands, symbols, statement.line
            )
            output.extend((opcode >> 8, opcode & 0xFF))
        elif statement.kind == "bytes":
            for expression in statement.value:  # type: ignore[union-attr]
                output.append(
                    checked(
                        evaluate(expression, symbols, statement.line),
                        0xFF,
                        "byte",
                        statement.line,
                    )
                )
        elif statement.kind == "glyphs":
            output.extend(GLYPHS.index(character) for character in statement.value)
        elif statement.kind == "bitmap":
            width, rows = statement.value
            for left in range(0, width, 8):
                for row in rows:
                    byte = 0
                    for bit, pixel in enumerate(row[left : left + 8]):
                        if pixel == "#":
                            byte |= 0x80 >> bit
                    output.append(byte)
        elif statement.kind == "align":
            output.extend(
                b"\0" * statement_size(statement, address, symbols)
            )
        address = ROM_ADDRESS + len(output)

    if not output:
        raise AssemblyError("source produced an empty ROM")
    if len(output) > MAX_ROM_SIZE:
        raise AssemblyError(
            f"ROM is {len(output)} bytes; base CHIP-8 permits {MAX_ROM_SIZE}"
        )
    return bytes(output), symbols


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--symbols", type=Path, help="write a sorted address map"
    )
    arguments = parser.parse_args()
    try:
        rom, symbols = assemble(arguments.source)
    except (AssemblyError, OSError) as error:
        print(f"chip8_assemble: {error}", file=sys.stderr)
        return 1

    arguments.output.write_bytes(rom)
    if arguments.symbols:
        lines = [
            f"{address:03X} {name}\n"
            for name, address in sorted(
                symbols.items(), key=lambda item: (item[1], item[0])
            )
            if address >= ROM_ADDRESS
        ]
        arguments.symbols.write_text("".join(lines), encoding="utf-8")
    print(
        f"assembled {arguments.source} -> {arguments.output} "
        f"({len(rom)} bytes, {MAX_ROM_SIZE - len(rom)} free)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
