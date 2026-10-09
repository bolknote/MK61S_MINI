#!/usr/bin/env python3
"""Build a standalone relocatable C, C++ or Rust APP; no resident ELF/BIN.

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
    "setup": ("SETUP", "SETUP", ["setup_ui.cpp", "setup_module_entry.cpp",
        "setup_font_compiler.cpp", "fmk_font.cpp", "fmk_prepare.cpp",
        "prepared_font.cpp"], None),
    "focal": ("FOCAL", "FOCAL", ["focal.cpp", "focal_module_entry.cpp"], None),
    "tinybasic": ("BASIC", "TINYBASIC", ["tinybasic.cpp", "tinybasic_module_entry.cpp"], None),
    "wbmp-viewer": ("WBMP", "WBMP", ["image1_viewer.cpp", "image1_viewer_module_entry.cpp", "wbmp.cpp"], "I1"),
    "markdown-viewer": ("MARKDOWN", "MARKDOWN", ["markdown_document.cpp", "markdown_viewer.cpp", "markdown_viewer_module_entry.cpp", "image1_viewer.cpp", "wbmp.cpp"], "T2"),
    "chip8": ("CHIP8", "CHIP8", ["chip8.cpp", "chip8_runner.cpp", "chip8_module_entry.cpp"], "C1"),
    "usbdisk": ("USBDISK", "USBDISK", ["virtual_fat.cpp",
        "virtual_fat_diagnostic.cpp", "usbdisk_module_entry.cpp"], None),
    "explorer": ("EXPLORER", "EXPLORER", ["explorer_ui.cpp",
        "explorer_autoexec.cpp", "explorer_module_entry.cpp"], None),
    "language-vm": ("LANGVM", "LANGUAGE_VM", ["language_bytecode.cpp",
        "language_vm.cpp", "language_vm_module_entry.cpp"], None),
    "language-input": ("LANGIN", "LANGUAGE_INPUT", ["language_bytecode.cpp",
        "language_vm.cpp", "language_vm_validation.cpp", "language_vm_input_entry.cpp",
        "language_vm_flow.cpp", "language_compiler_flow.cpp"], None),
}

# These ceilings protect intentionally compact system interpreters from silent
# code-size regressions.  memory_bytes is the complete loaded image plus BSS;
# the editor/runtime workspace leased by the firmware is accounted separately.
SYSTEM_SIZE_BUDGETS = {
    # SETUP owns all FMK validation and compilation.  Keep enough headroom in
    # the 20-KiB APP arena for that decoder plus its full 8-KiB source buffer.
    "setup": {"app_bytes": 10_000, "memory_bytes": 20_480},
    "focal": {"app_bytes": 12_000, "memory_bytes": 17_000},
    "explorer": {"app_bytes": 8_000, "memory_bytes": 10_000},
    # The cold module owns retry, resource verification and INPUT rendering.
    "language-input": {"app_bytes": 12_000, "memory_bytes": 16_000},
}
LOCAL_FLOAT_SIZE_BUDGETS = {
    "focal": {"app_bytes": 14_000, "memory_bytes": 20_000},
    "tinybasic": {"app_bytes": 12_000, "memory_bytes": 17_500},
}
# The dependency-free Windows packer deliberately uses a bounded greedy ZX0
# parser: Arduino IDE users must not need MSVC/MinGW just to build APP files.
# It produces the same decoded image but a somewhat larger C6 file than the
# desktop optimal parser.  Keep separate measured ceilings for that storage
# representation while retaining the same memory_bytes limits above.
GREEDY_APP_SIZE_BUDGETS = {
    (False, "focal"): 13_500,
    (True, "focal"): 15_100,
    (True, "tinybasic"): 13_000,
}
# Compiler FLOW_STEP owns source selection, translation and literal interning.
# Leave ordinary interpreter ceilings unchanged; only external compiler APPs
# pay for this policy. The shared APP arena remains the same 20 KiB.
COMPILER_SIZE_BUDGETS = {
    "focal": {"app_bytes": 13_800, "memory_bytes": 18_688},
}
DEFAULT_LOCAL_FLOAT_MASK = 0x3C0  # ln, log10, exp, sqrt


def run(command: list[str | Path]) -> str:
    result = subprocess.run([str(x) for x in command], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise ValueError(result.stdout + result.stderr)
    return result.stdout


def enforce_system_size_budget(system: str | None, report: dict,
                               local_float_math: bool = False,
                               greedy_packer: bool = False,
                               split_language_vm: bool = False,
                               language_vm_compiler: bool = False) -> None:
    budgets = LOCAL_FLOAT_SIZE_BUDGETS if local_float_math else SYSTEM_SIZE_BUDGETS
    budget = budgets.get(system)
    if language_vm_compiler:
        budget = COMPILER_SIZE_BUDGETS.get(system, budget)
    if system == "language-vm" and split_language_vm:
        # Includes FLOW_STEP, resource delivery and continuation policy.
        # Six FOCAL v5 operations add parameter frames, sparse array access
        # and precision events. The measured split kernel uses 14,452 bytes;
        # these ceilings do not enlarge the common 20-KiB APP arena.
        budget = {"memory_bytes": 17_408 if local_float_math else 15_360}
    if budget is None:
        return
    budget = dict(budget)
    if system == "focal" and language_vm_compiler and report.get("focal_trace"):
        budget["memory_bytes"] = 19_200
    if greedy_packer:
        greedy_limit = GREEDY_APP_SIZE_BUDGETS.get((local_float_math, system))
        if language_vm_compiler and system == "focal":
            greedy_limit = 14_100
        if greedy_limit is not None:
            budget["app_bytes"] = greedy_limit
    exceeded = [f"{field}={report[field]} > {limit}"
                for field, limit in budget.items()
                if report[field] > limit]
    if exceeded:
        raise ValueError(f"{system} size budget exceeded: " + ", ".join(exceeded))


def build(args: argparse.Namespace) -> dict:
    # FOCAL is now a VM frontend, never a self-contained native interpreter.
    if args.system == "focal":
        args.language_vm_compiler = True
    system = SYSTEM_MODULES.get(args.system)
    if getattr(args, "split_language_vm", False):
        if args.system != "language-vm":
            raise ValueError("--split-language-vm applies only to language-vm")
        system = ("LANGVM", "LANGUAGE_VM", ["language_vm.cpp",
                  "language_vm_overlay_entry.cpp", "language_vm_flow.cpp"], None)
    if args.text_only and args.system != "markdown-viewer":
        raise ValueError("--text-only applies to markdown-viewer")
    if args.no_ui_fonts and not system:
        raise ValueError("--no-ui-fonts applies to system APPs")
    if args.local_float_math and args.system not in ("focal", "tinybasic", "language-vm"):
        raise ValueError("--local-float-math applies only to FOCAL, TinyBASIC or language-vm")
    if args.language_vm_compiler and args.local_float_math:
        raise ValueError("compiler-only APP delegates math to LANGVM; select local math on LANGVM")
    if system and args.source:
        raise ValueError("--system selects its own sources")
    if system and args.shared_runtime:
        raise ValueError("System APP selects its runtime automatically")
    if not system and not args.source:
        raise ValueError("--source is required for a user APP")
    args.name = args.name or (system[0] if system else None)
    if not args.name:
        raise ValueError("--name is required for a user APP")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,30}", args.name):
        raise ValueError("name must be an ASCII APP basename (1..31 characters)")
    if re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]", args.name, re.I):
        raise ValueError("name is reserved by C6 and Windows")
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
    sources = ([ROOT / "sdk/portable/start.c",
                ROOT / "sdk/portable/system/system_compat.cpp",
                *[ROOT / "code" / x for x in system[2]]] if system else
               [ROOT / "sdk/portable/start.c", *[x.resolve() for x in args.source]])
    if args.language_vm_compiler:
        if args.system not in ("tinybasic", "focal"):
            raise ValueError("--language-vm-compiler applies only to BASIC/FOCAL")
        sources += [ROOT / "code/language_bytecode.cpp", ROOT / "code/language_vm_frontend.cpp",
                    ROOT / "code/language_compiler_flow.cpp"]
    if args.system in ("language-vm", "language-input"):
        sources += [ROOT / "sdk/portable/system/resource.cpp"]
    if args.system == "setup":
        sources += [ROOT / "sdk/portable/system/setup_compat.cpp"]
    if args.system == "usbdisk":
        sources += [ROOT / "sdk/portable/system/usbdisk_compat.cpp"]
    if args.system not in ("focal", "tinybasic", "language-vm", "language-input"):
        sources += [ROOT / "sdk/portable/memory.c"]
    if args.system in ("focal", "tinybasic", "language-vm", "language-input"):
        sources += [ROOT / "sdk/portable/system/runtime.S", ROOT / "sdk/portable/system/editor.cpp"]
    if args.shared_runtime:
        sources += [ROOT / "sdk/portable/shared_runtime.c", ROOT / "sdk/portable/system/runtime.S"]
    if len(set(sources)) != len(sources):
        raise ValueError("duplicate source")
    flags = ["-mcpu=cortex-m4", "-mthumb", "-mfpu=fpv4-sp-d16",
             "-mfloat-abi=hard", "-Oz" if system else "-Os", "-flto", "-fipa-pta",
             "-mword-relocations", "-fno-builtin", "-ffunction-sections", "-fdata-sections",
             "-Wall", "-Wextra", "-Werror"]
    if getattr(args,"focal_trace",False):
        if args.system not in ("focal", "language-vm"):
            raise ValueError("--focal-trace applies only to FOCAL or its shared VM")
        flags.append("-DMK61_FOCAL_TRACE=1")
    if not system:
        flags.append("-ffreestanding")
    if args.shared_runtime:
        flags += ["-DMK61_APP_SHARED_RUNTIME=1", "-DMK61_RUNTIME_POINTER=mk61_app_runtime"]
    includes = ([ROOT / "sdk/portable/system"] if system else []) + [
        ROOT / "sdk/portable/include", ROOT / "code", *args.include]
    include_flags = ["-I" + str(x.resolve()) for x in includes]
    objects = []
    compile_commands = []
    rust_compiler = None
    for index, source in enumerate(sources):
        if source.suffix not in (".c", ".cpp", ".rs", ".S") or not source.is_file():
            raise ValueError(f"expected an existing .c, .cpp, .rs or .S source: {source}")
        obj = out / f"{index}-{source.name}.o"
        if source.suffix == ".rs":
            if rust_compiler is None:
                rust_compiler = args.rustc
                if rust_compiler is None:
                    found = shutil.which("rustc")
                    if found is None:
                        raise ValueError("Rust source requires rustc on PATH")
                    rust_compiler = Path(found)
                else:
                    rust_compiler = rust_compiler.resolve()
                if not rust_compiler.is_file():
                    raise ValueError(f"Rust compiler is missing: {rust_compiler}")
            command = [rust_compiler, "--edition", "2021",
                       "--target", "thumbv7em-none-eabihf",
                       "--crate-type", "lib", "--emit", "obj",
                       "--crate-name", f"mk61_app_{index}",
                       "-C", "opt-level=s", "-C", "panic=abort",
                       "-C", "relocation-model=static",
                       # APP relocation records support word pointers. This is
                       # LLVM's equivalent of ARM GCC -mword-relocations.
                       "-C", "target-feature=+no-movt",
                       source, "-o", obj]
            try:
                run(command)
            except ValueError as exc:
                if "can't find crate for `core`" in str(exc):
                    raise ValueError(
                        "Rust target thumbv7em-none-eabihf is missing; run "
                        "rustup target add thumbv7em-none-eabihf"
                    ) from exc
                raise
            compile_commands.append({"directory": str(ROOT), "file": str(source),
                                     "arguments": [str(x) for x in command]})
            objects.append(obj)
            continue
        cpp = source.suffix == ".cpp"
        language = (["-std=c++17", "-fno-exceptions", "-fno-rtti",
                     "-fno-threadsafe-statics", "-fno-use-cxa-atexit"] if cpp
                    else ["-std=c11"] if source.suffix == ".c" else [])
        # GCC can synthesize memset/memcpy after LTO's symbol pruning.
        # Keep their freestanding definitions in a normal object.
        support = ["-fno-lto"] if source == ROOT / "sdk/portable/memory.c" else []
        if system and cpp:
            support += ["-DMK61_BUILD_PORTABLE_SYSTEM", "-DMK61_BUILD_" + system[1] + "_MODULE",
                        "-include", str(ROOT / "sdk/portable/system/system_compat.hpp")]
            if args.language_vm_compiler:
                support += ["-DMK61_LANGUAGE_VM_COMPILER=1"]
            if args.local_float_math:
                local_mask = (args.local_float_math_mask
                              if args.local_float_math_mask is not None
                              else DEFAULT_LOCAL_FLOAT_MASK)
                support += ["-DMK61_APP_LOCAL_FLOAT_MATH=1",
                            "-DMK61_APP_LOCAL_FLOAT_MATH_MASK=" +
                            hex(local_mask)]
            if args.no_ui_fonts:
                support += ["-DMK61_PORTABLE_UI_FONTS=0"]
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
         *objects, *args.library, *(["-lm"] if args.local_float_math else []),
         *(["-lc"] if system else []), "-lgcc", "-o", elf])
    if run([tool("nm"), "--undefined-only", elf]).strip():
        raise ValueError("APP has unresolved imports")
    symbols = {}
    for line in run([tool("nm"), "--defined-only", elf]).splitlines():
        parts = line.split()
        if len(parts) == 3:
            symbols[parts[2]] = int(parts[0], 16)
    base = symbols["__module_image_start"]
    memory_size = symbols["__module_memory_end"] - base
    entry_offset = (symbols["mk61_module_entry"] & ~1) - base
    if base != 0x20000000:
        raise ValueError("portable SRAM base changed")
    image = out / (args.name + ".bin")
    app = out / (args.name + ".APP")
    run([tool("objcopy"), "-O", "binary", "-j", ".module_image", elf, image])
    packer = args.packer
    python_packer = (ROOT / "tools/.mk61-app/mk61_module_pack.py").resolve()
    greedy_packer = False
    if packer is None and os.name == "nt":
        # Arduino's ARM GCC cannot produce a host Windows executable and the
        # IDE does not install MSVC/LLVM.  Use the dependency-free Python
        # packer instead of requiring a second C++ toolchain from end users.
        command = [sys.executable, python_packer]
        greedy_packer = True
    else:
        if packer is None:
            configured = os.environ.get("MK61_MODULE_PACK_BIN")
            packer = (Path(configured).expanduser() if configured else
                      ROOT / (".build/tools/mk61_module_pack" + suffix))
            run(["bash", ROOT / "tools/build_mk61_module_pack.sh", "--help"])
        elif packer.resolve() == python_packer:
            greedy_packer = True
        command = [packer]
    command += ["--portable", "--kind", args.system or "app", "--image", image,
               "--memory-size", str(memory_size), "--entry-offset",
               str(entry_offset), "--output", app]
    offsets, table = extract(elf, base, image.stat().st_size, memory_size)
    relocations = out / (args.name + ".rel")
    relocations.write_bytes(table)
    command += ["--relocations", relocations]
    handled_magic = args.handled_magic or (system[3] if system else None)
    if handled_magic:
        command += ["--handled-magic", handled_magic]
    print(run(command), end="")
    image_flags = struct.unpack_from("<I", app.read_bytes(), 16)[0]
    report = {"name": args.name, "abi": 6, "load_address": base,
              "relocations": len(offsets),
              "relocation_bytes": len(table),
              "entry_offset": entry_offset, "image_bytes": image.stat().st_size,
              "bss_bytes": memory_size - image.stat().st_size,
              "memory_bytes": memory_size, "app_bytes": app.stat().st_size,
              "compression": "ZX0+BCJ" if image_flags & 2 else "ZX0",
              "zx0_parser": "greedy" if greedy_packer else "optimal",
              "resident_imports": 0,
              "compiler": run([tool("gcc"), "--version"]).splitlines()[0]}
    if args.local_float_math:
        report["local_float_math_mask"] = (
            args.local_float_math_mask
            if args.local_float_math_mask is not None
            else DEFAULT_LOCAL_FLOAT_MASK)
    if getattr(args,"focal_trace",False):
        report["focal_trace"] = True
    if args.language_vm_compiler:
        report["language_vm_compiler"] = True
    if rust_compiler is not None:
        report["rust_compiler"] = run([rust_compiler, "--version"]).strip()
    (out / (args.name + ".json")).write_text(json.dumps(report, indent=2) + "\n")
    enforce_system_size_budget(args.system, report, args.local_float_math,
                               greedy_packer, getattr(args, "split_language_vm", False),
                               args.language_vm_compiler)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name")
    parser.add_argument("--source", type=Path, action="append", default=[])
    parser.add_argument("--system", choices=SYSTEM_MODULES)
    parser.add_argument("--focal-trace", action="store_true", help="enable opt-in FOCAL Serial diagnostics in frontend/VM")
    parser.add_argument("--language-vm-compiler", action="store_true",
                        help="experimental compiler-only BASIC/FOCAL; requires a VM-aware resident")
    parser.add_argument("--split-language-vm", action="store_true",
                        help="hot VM without editor/parser; INPUT is a separate LANGIN.APP")
    parser.add_argument("--shared-runtime", action="store_true",
                        help="use resident ARM EABI/string helpers; require runtime service at startup")
    parser.add_argument("--text-only", action="store_true",
                        help="compact Markdown without graphical rendering or WBMP")
    parser.add_argument("--no-ui-fonts", action="store_true",
                        help="omit the optional proportional UI client from a system APP")
    parser.add_argument("--local-float-math", action="store_true",
                        help="link local single-precision libm into FOCAL, TinyBASIC or LANGVM")
    parser.add_argument("--local-float-math-mask", type=lambda value: int(value, 0),
                        help=argparse.SUPPRESS)
    parser.add_argument("--include", type=Path, action="append", default=[])
    parser.add_argument("--library", type=Path, action="append", default=[])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--arm-toolchain-bin", type=Path)
    parser.add_argument("--rustc", type=Path,
                        help="rustc executable; required only for .rs sources if not on PATH")
    parser.add_argument("--packer", type=Path)
    parser.add_argument("--handled-magic")
    args = parser.parse_args()
    if args.local_float_math_mask is not None and not args.local_float_math:
        parser.error("--local-float-math-mask requires --local-float-math")
    if args.local_float_math_mask is not None and \
       args.local_float_math_mask & ~0x7FF:
        parser.error("--local-float-math-mask must fit 11 operation bits")
    try:
        print(json.dumps(build(args), indent=2))
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"portable APP build: {exc}\n")


if __name__ == "__main__":
    main()
