#!/usr/bin/env python3
"""Verify isolated Q2/Q4 kernels and compile them for Pico H; no device I/O."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from tools.firmware.picocalc.build_picocalc import compiler_bin


def run(command):
    return subprocess.run([str(v) for v in command], check=True, text=True,
                          capture_output=True).stdout.strip()


def check_model(path, library):
    """Use real MKQ4v1 codes, without importing or altering training code."""
    data = path.read_bytes()
    if data[:8] != b"MKQ4v1\0\0":
        raise ValueError("Expected MKQ4v1")
    header_size = struct.unpack_from("<I", data, 8)[0]
    header = json.loads(data[12:12 + header_size])
    start = 12 + header_size
    u8 = ctypes.c_uint8
    i8 = ctypes.c_int8

    class Table(ctypes.Structure):
        _fields_ = [("subset", (ctypes.c_int16 * 16) * 8), ("sum", ctypes.c_int16)]

    lib = ctypes.CDLL(str(library))
    lib.mk61ai_prepare_lut32.argtypes = [ctypes.POINTER(i8), ctypes.POINTER(Table)]
    lib.mk61ai_pack_q4_planes32.argtypes = [ctypes.POINTER(u8), ctypes.POINTER(u8)]
    lib.mk61ai_dot_q4_a8_32.argtypes = [ctypes.POINTER(u8), ctypes.POINTER(i8)]
    lib.mk61ai_dot_q4_a8_32.restype = ctypes.c_int32
    lib.mk61ai_dot_lut_q4_a8_32.argtypes = [ctypes.POINTER(u8), ctypes.POINTER(Table)]
    lib.mk61ai_dot_lut_q4_a8_32.restype = ctypes.c_int32
    rng = random.Random(61)
    checked = tensors = 0
    for record in header["tensors"]:
        if record["format"] != "q4_group32":
            continue
        tensors += 1
        groups = record["codes_bytes"] // 16
        for group in sorted({0, groups - 1, *(rng.randrange(groups) for _ in range(32))}):
            offset = start + record["offset"] + group * 16
            packed = data[offset:offset + 16]
            assert len(packed) == 16
            weights = [((packed[i // 2] >> (4 * (i % 2))) & 15) - 8 for i in range(32)]
            values = [rng.randrange(-128, 128) for _ in range(32)]
            expected = sum(w * x for w, x in zip(weights, values))
            codes, planes, x, table = (u8 * 16)(*packed), (u8 * 16)(), (i8 * 32)(*values), Table()
            lib.mk61ai_pack_q4_planes32(codes, planes)
            lib.mk61ai_prepare_lut32(x, ctypes.byref(table))
            assert lib.mk61ai_dot_q4_a8_32(codes, x) == expected, record["name"]
            assert lib.mk61ai_dot_lut_q4_a8_32(planes, ctypes.byref(table)) == expected, record["name"]
            checked += 1
    assert tensors and checked
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(),
            "q4_tensors": tensors, "sampled_groups": checked,
            "scope": "Exact integer dot products on existing weight codes; scales and model logits untested"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".build/picocalc-ai-runtime-20261106")
    parser.add_argument("--mkq4", type=Path)
    parser.add_argument("--toolchain", type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    cc = os.environ.get("CC") or shutil.which("clang") or shutil.which("cc")
    if not cc:
        raise RuntimeError("C compiler unavailable")
    common = ["-std=c11", "-Wall", "-Wextra", "-Werror", "-O2"]
    binary = out / "kernel-tests"
    run([cc, *common, "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
         HERE / "kernels.c", HERE / "test_kernels.c", "-o", binary])
    report = {"host": json.loads(run([binary])), "hardware_timing": None,
              "full_model_inference": False}
    toolchain = compiler_bin(args.toolchain)
    obj = out / "kernels-m0.o"
    flags = ["-std=c11", "-Wall", "-Wextra", "-Werror", "-O2", "-mcpu=cortex-m0plus",
             "-mthumb", "-mfloat-abi=soft", "-ffreestanding", "-fno-builtin",
             "-ffunction-sections", "-fdata-sections", "-fstack-usage"]
    run([toolchain / "arm-none-eabi-gcc", *flags, "-c", HERE / "kernels.c", "-o", obj])
    report["arm"] = {"compiler": run([toolchain / "arm-none-eabi-gcc", "-dumpfullversion"]),
                     "flags": flags, "size": run([toolchain / "arm-none-eabi-size", obj]),
                     "undefined_symbols": run([toolchain / "arm-none-eabi-nm", "-u", obj]),
                     "stack_usage": (out / "kernels-m0.su").read_text(),
                     "scope": "Cross compilation only; ARM execution and RP2040 timing not measured"}
    if args.mkq4:
        library = out / ("kernels.dylib" if sys.platform == "darwin" else "kernels.so")
        run([cc, *common, "-shared", "-fPIC", HERE / "kernels.c", "-o", library])
        report["model_codes"] = check_model(args.mkq4.resolve(), library)
    (out / "checks.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
