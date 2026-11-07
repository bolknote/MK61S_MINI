"""Bounded execution through the production MK-61 core; no Python opcode simulation."""
from __future__ import annotations

import ctypes
from decimal import Decimal, ROUND_HALF_EVEN
import hashlib
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def build(destination: Path | None = None) -> Path:
    destination = destination or REPO / ".build/mk61-agent-20261106/libmk61.so"
    destination.parent.mkdir(parents=True, exist_ok=True)
    sources = [HERE / "core_bridge.cpp", REPO / "code/mk61emu_core.cpp"]
    fingerprint = hashlib.sha256()
    for source in [*sources, *sorted((REPO / "code").glob("*.h")), *sorted((REPO / "code").glob("*.hpp"))]:
        fingerprint.update(source.read_bytes())
    stamp = destination.with_suffix(".sha256")
    digest = fingerprint.hexdigest()
    if destination.exists() and stamp.exists() and stamp.read_text().strip() == digest:
        return destination
    command = [os.environ.get("CXX", "c++"), "-std=c++17", "-O2", "-fPIC", "-shared",
               "-DMK61_CORE_STANDALONE=1", "-DMK61_CORE_HOT_TABLES_IN_SRAM=0",
               "-I", str(REPO / "code"), *map(str, sources), "-o", str(destination)]
    subprocess.run(command, check=True, capture_output=True)
    stamp.write_text(digest + "\n")
    return destination


def decimal_parts(value: str | int | float) -> tuple[bool, str, int]:
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError("Only finite decimal inputs are supported")
    if number == 0:
        return number.is_signed(), "00000000", 0
    exponent = number.copy_abs().adjusted()
    mantissa = number.copy_abs().scaleb(7 - exponent).quantize(Decimal(1), rounding=ROUND_HALF_EVEN)
    if mantissa >= 100000000:
        exponent += 1
        mantissa /= 10
    if not -99 <= exponent <= 99:
        raise ValueError("MK-61 exponent is outside -99..99")
    return number.is_signed(), f"{int(mantissa):08d}", exponent


def read_decimal(raw: bytes) -> str:
    text = raw.decode("ascii").strip()
    fields = text.split()
    if len(fields) != 2:
        raise ValueError(f"Invalid MK-61 number: {text!r}")
    value = Decimal(fields[0]).scaleb(int(fields[1]))
    return "0" if value == 0 else format(value.normalize(), "f")


class Emulator:
    """The native core is global: use one instance per OS process."""
    def __init__(self, library: Path | None = None):
        self.lib = ctypes.CDLL(str(library or build()))
        self.lib.mk_load.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint]
        self.lib.mk_set_register.argtypes = [ctypes.c_uint, ctypes.POINTER(ctypes.c_ubyte)]
        self.lib.mk_set_stack.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
        self.lib.mk_read_stack.argtypes = [ctypes.c_uint, ctypes.c_char_p]
        self.lib.mk_read_register.argtypes = [ctypes.c_uint, ctypes.c_char_p]
        self.lib.mk_trace_x.argtypes = [ctypes.c_uint, ctypes.c_char_p]

    def run(self, program: list[int], registers: dict[str, object] | None = None,
            *, max_commands: int = 256, max_frames: int = 2048, trace: bool = False, memory: bool = False) -> dict:
        if not program or len(program) > 105 or any(type(x) is not int or not 0 <= x <= 255 for x in program):
            return {"status": "invalid_program"}
        if self.lib.mk_reset() != 0:
            raise RuntimeError("Cannot reset MK-61 core")
        code = (ctypes.c_ubyte * len(program))(*program)
        if self.lib.mk_load(code, len(program)) != 0:
            raise RuntimeError("Cannot load MK-61 program")
        for name, value in (registers or {}).items():
            negative, digits, exponent = decimal_parts(value)
            if name.upper() in {"X", "Y", "Z", "T", "X1"}:
                index = {"X1": 0, "X": 1, "Y": 2, "Z": 3, "T": 4}[name.upper()]
                result = self.lib.mk_set_stack(index, negative, digits.encode(), exponent)
            else:
                index = int(name.upper().removeprefix("R"), 16)
                if not 0 <= index < 15:
                    raise ValueError(f"Invalid register {name}")
                encoded_exponent = exponent if exponent >= 0 else 100 + exponent
                packed = [4 | (128 if negative else 0) | (64 if exponent < 0 else 0),
                          (encoded_exponent // 10) * 16 + encoded_exponent % 10,
                          *[int(digits[i:i + 2], 10) // 10 * 16 + int(digits[i:i + 2]) % 10 for i in range(0, 8, 2)]]
                result = self.lib.mk_set_register(index, (ctypes.c_ubyte * len(packed))(*packed))
            if result != 0:
                raise RuntimeError(f"Cannot initialize {name}")
        result = self.lib.mk_run(max_commands, max_frames)
        state = {"status": {0: "stopped", 1: "limit", 2: "error", -1: "internal_error"}[result],
                 "pc": self.lib.mk_pc(), "commands": self.lib.mk_trace_size()}
        for index, name in enumerate(["X1", "X", "Y", "Z", "T"]):
            out = ctypes.create_string_buffer(32)
            self.lib.mk_read_stack(index, out)
            try:
                state[name] = read_decimal(out.value)
            except (ValueError, ArithmeticError):
                state[name] = out.value.decode("ascii", errors="replace").strip()
        if memory:
            for index in range(15):
                out = ctypes.create_string_buffer(32)
                self.lib.mk_read_register(index, out)
                try:
                    state[f"R{index:X}"] = read_decimal(out.value)
                except (ValueError, ArithmeticError):
                    state[f"R{index:X}"] = out.value.decode("ascii", errors="replace").strip()
        if trace:
            state["trace"] = []
            for index in range(self.lib.mk_trace_size()):
                out = ctypes.create_string_buffer(32)
                self.lib.mk_trace_x(index, out)
                try:
                    x = read_decimal(out.value)
                except (ValueError, ArithmeticError):
                    x = out.value.decode("ascii", errors="replace").strip()
                state["trace"].append({"pc": self.lib.mk_trace_address(index),
                                       "opcode": self.lib.mk_trace_opcode(index), "X": x})
        return state


if __name__ == "__main__":
    import json
    try:
        emulator = Emulator()
        for program, registers in [([0x60, 0x61, 0x10, 0x50], {"R0": 7, "R1": 5}),
                                   ([0x60, 0x61, 0x11, 0x50], {"R0": 7, "R1": 5}),
                                   ([0x51, 0x00], {})]:
            print(json.dumps(emulator.run(program, registers, max_commands=20, trace=True)))
    except subprocess.CalledProcessError as error:
        sys.stderr.write(error.stderr.decode())
        raise
