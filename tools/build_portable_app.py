#!/usr/bin/env python3
"""Build a standalone relocatable APP using ARM GCC; no resident ELF/BIN.

Examples and the ABI contract are in sdk/portable/README.md.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/.mk61-app"))
from app_relocations import extract
SYSTEM_MODULES = {
    "setup": ("SETUP", "SETUP", ["setup_ui.cpp", "setup_module_entry.cpp", "fmk_font.cpp"], None),
    "focal": ("FOCAL", "FOCAL", ["focal.cpp", "focal_module_entry.cpp"], None),
    "tinybasic": ("BASIC", "TINYBASIC", ["tinybasic.cpp", "tinybasic_module_entry.cpp"], None),
    "wbmp-viewer": ("WBMP", "WBMP", ["image1_viewer.cpp", "image1_viewer_module_entry.cpp", "wbmp.cpp"], "I1"),
    "markdown-viewer": ("MARKDOWN", "MARKDOWN", ["markdown_document.cpp", "markdown_plain.cpp", "markdown_viewer.cpp", "markdown_viewer_module_entry.cpp", "image1_viewer.cpp", "wbmp.cpp"], "T2"),
    "chip8": ("CHIP8", "CHIP8", ["chip8.cpp", "chip8_runner.cpp", "chip8_module_entry.cpp"], "C1"),
}


def run(command: list[str | Path]) -> str:
    result = subprocess.run([str(x) for x in command], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise ValueError(result.stdout + result.stderr)
    return result.stdout


def build(args: argparse.Namespace) -> dict:
    system = SYSTEM_MODULES.get(args.system)
    if args.text_only and args.system != "markdown-viewer":
        raise ValueError("--text-only applies to markdown-viewer")
    if system and args.source:
        raise ValueError("--system selects its own sources")
    if not system and not args.source:
        raise ValueError("--source is required for a user APP")
    args.name = args.name or (system[0] if system else None)
    if not args.name:
        raise ValueError("--name is required for a user APP")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,30}", args.name):
        raise ValueError("name must be an ASCII APP basename (1..31 characters)")
    if re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]", args.name, re.I):
        raise ValueError("name is reserved by C5 and Windows")
    tool_dir = args.arm_toolchain_bin
    if tool_dir is None:
        gcc = shutil.which("arm-none-eabi-gcc")
        if gcc is None:
            raise ValueError("specify --arm-toolchain-bin or put ARM GCC on PATH")
        tool_dir = Path(gcc).parent
    suffix = ".exe" if os.name == "nt" else ""

    def tool(name: str) -> Path:
        path = tool_dir / ("arm-none-eabi-" + name + suffix)
        if not path.is_file():
            raise ValueError(f"ARM tool is missing: {path}")
        return path

    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    sources = ([ROOT / "sdk/portable/system/system_compat.cpp",
                *[ROOT / "code" / x for x in system[2]]] if system else
               [ROOT / "sdk/portable/start.c", *[x.resolve() for x in args.source]])
    if args.system == "setup":
        sources += [ROOT / "sdk/portable/system/setup_compat.cpp"]
    sources += [ROOT / "sdk/portable/memory.c"]
    if args.system in ("focal", "tinybasic"):
        sources += [ROOT / "sdk/portable/system/runtime.S", ROOT / "sdk/portable/system/editor.cpp"]
    if len(set(sources)) != len(sources):
        raise ValueError("duplicate source")
    flags = ["-mcpu=cortex-m4", "-mthumb", "-mfpu=fpv4-sp-d16",
             "-mfloat-abi=hard", "-Oz" if system else "-Os", "-flto", "-fipa-pta",
             "-mword-relocations", "-fno-builtin", "-ffunction-sections", "-fdata-sections",
             "-Wall", "-Wextra", "-Werror"]
    if not system:
        flags.append("-ffreestanding")
    includes = ([ROOT / "sdk/portable/system"] if system else []) + [
        ROOT / "sdk/portable/include", ROOT / "code", *args.include]
    include_flags = ["-I" + str(x.resolve()) for x in includes]
    objects = []
    compile_commands = []
    for index, source in enumerate(sources):
        if source.suffix not in (".c", ".cpp", ".S") or not source.is_file():
            raise ValueError(f"expected an existing .c, .cpp or .S source: {source}")
        cpp = source.suffix == ".cpp"
        language = (["-std=c++17", "-fno-exceptions", "-fno-rtti",
                     "-fno-threadsafe-statics", "-fno-use-cxa-atexit"] if cpp
                    else ["-std=c11"] if source.suffix == ".c" else [])
        obj = out / f"{index}-{source.name}.o"
        # GCC can synthesize memset/memcpy after LTO's symbol pruning.
        # Keep their freestanding definitions in a normal object.
        support = ["-fno-lto"] if source == ROOT / "sdk/portable/memory.c" else []
        if system and cpp:
            support += ["-DMK61_BUILD_PORTABLE_SYSTEM", "-DMK61_BUILD_" + system[1] + "_MODULE",
                        "-include", str(ROOT / "sdk/portable/system/system_compat.hpp")]
            if args.text_only:
                support += ["-DMK61_PORTABLE_TEXT_ONLY=1"]
        command = [tool("g++" if cpp else "gcc"), *flags, *support, *language, *include_flags,
                   "-c", source, "-o", obj]
        run(command)
        if source.suffix != ".S":
            compile_commands.append({"directory": str(ROOT), "file": str(source),
                                     "arguments": [str(x) for x in command]})
        objects.append(obj)
    if system:
        database = out / "compile_commands.json"
        database.write_text(json.dumps(compile_commands, indent=2) + "\n")
        stack_command = [sys.executable, ROOT / "tests/analyze_stack_usage.py",
                         "--compile-commands", database, "--max-frame", "5120", "--top", "1",
                         "--summary-json", out / "stack-usage.json"]
        for command in compile_commands:
            stack_command += ["--source", command["file"]]
        print(run(stack_command), end="")
    elf = out / (args.name + ".elf")
    run([tool("g++"), *flags, "-nostdlib", "-nostartfiles",
         "-Wl,--gc-sections,--emit-relocs", "-Wl,--defsym=MK61_MODULE_ORIGIN=0x20000000",
         "-Wl,-T," + str(ROOT / "tools/.mk61-app/mk61_module.ld"),
         "-Wl,-Map," + str(out / (args.name + ".map")),
         *objects, *args.library, *(["-lc"] if system else []), "-lgcc", "-o", elf])
    if run([tool("nm"), "--undefined-only", elf]).strip():
        raise ValueError("APP has unresolved imports")
    symbols = {}
    for line in run([tool("nm"), "--defined-only", elf]).splitlines():
        parts = line.split()
        if len(parts) == 3:
            symbols[parts[2]] = int(parts[0], 16)
    for line in run([tool("size"), "-A", elf]).splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith("."):
            if parts[0] not in (".module_image", ".module_bss") and not parts[0].startswith(".rel.") and int(parts[1]):
                raise ValueError(f"unpacked ELF section: {parts[0]}")
    base = symbols["__module_image_start"]
    memory_size = symbols["__module_memory_end"] - base
    entry_offset = (symbols["mk61_module_entry"] & ~1) - base
    if base != 0x20000000:
        raise ValueError("portable SRAM base changed")
    image = out / (args.name + ".bin")
    app = out / (args.name + ".APP")
    run([tool("objcopy"), "-O", "binary", "-j", ".module_image", elf, image])
    packer = args.packer
    if packer is None:
        packer = ROOT / (".build/tools/mk61_module_pack" + suffix)
        if os.name == "nt":
            run(["powershell", "-NoProfile", "-File",
                 ROOT / "tools/.mk61-app/build.ps1", "-OutputPath", packer])
        else:
            run(["bash", ROOT / "tools/build_mk61_module_pack.sh", "--help"])
    command = [packer, "--portable", "--kind", args.system or "app", "--image", image,
               "--memory-size", str(memory_size), "--entry-offset",
               str(entry_offset), "--output", app]
    offsets, table = extract(elf, base, image.stat().st_size, memory_size)
    if not args.fixed_address:
        relocations = out / (args.name + ".rel")
        relocations.write_bytes(table)
        command += ["--relocations", relocations]
    handled_magic = args.handled_magic or (system[3] if system else None)
    if handled_magic:
        command += ["--handled-magic", handled_magic]
    print(run(command), end="")
    image_flags = struct.unpack_from("<I", app.read_bytes(), 16)[0]
    report = {"name": args.name, "abi": 3 if args.fixed_address else 4, "load_address": base,
              "relocations": 0 if args.fixed_address else len(offsets),
              "relocation_bytes": 0 if args.fixed_address else len(table),
              "entry_offset": entry_offset, "image_bytes": image.stat().st_size,
              "bss_bytes": memory_size - image.stat().st_size,
              "memory_bytes": memory_size, "app_bytes": app.stat().st_size,
              "compression": "ZX0+BCJ" if image_flags & 2 else "ZX0",
              "resident_imports": 0,
              "compiler": run([tool("gcc"), "--version"]).splitlines()[0]}
    (out / (args.name + ".json")).write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name")
    parser.add_argument("--fixed-address", action="store_true", help="emit legacy portable ABI 3")
    parser.add_argument("--source", type=Path, action="append", default=[])
    parser.add_argument("--system", choices=SYSTEM_MODULES)
    parser.add_argument("--text-only", action="store_true",
                        help="compact Markdown without graphical rendering or WBMP")
    parser.add_argument("--include", type=Path, action="append", default=[])
    parser.add_argument("--library", type=Path, action="append", default=[])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--arm-toolchain-bin", type=Path)
    parser.add_argument("--packer", type=Path)
    parser.add_argument("--handled-magic")
    args = parser.parse_args()
    try:
        print(json.dumps(build(args), indent=2))
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"portable APP build: {exc}\n")


if __name__ == "__main__":
    main()
