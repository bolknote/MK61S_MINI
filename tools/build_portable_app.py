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
    "source-editor": ("SRCEDIT", "SOURCE_EDITOR", ["language_source_editor_entry.cpp", "language_bytecode.cpp"], None),
    "vm-file-cache": ("VMSTORE", "VM_FILE_CACHE", ["language_vm_file_cache_entry.cpp",
        "language_vm_file_cache.cpp", "language_compiler_flow.cpp", "language_vm.cpp",
        "language_bytecode.cpp"], None),
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

# CI-only regression ceilings for intentionally compact system interpreters.
# Ordinary builds rely on the linker's and packer's hard APP format limits.
# memory_bytes is the complete loaded image plus BSS; the editor/runtime
# workspace leased by the firmware is accounted separately.
SYSTEM_SIZE_BUDGETS = {
    # SETUP owns all FMK validation and compilation.  Keep enough headroom in
    # the 20-KiB APP arena for that decoder plus its full 8-KiB source buffer.
    "setup": {"app_bytes": 10_000, "memory_bytes": 20_480},
    "focal": {"app_bytes": 12_000, "memory_bytes": 17_000},
    "explorer": {"app_bytes": 8_000, "memory_bytes": 10_000},
    # The cold module owns retry, resource verification and INPUT rendering.
    # Shared expression parsing now includes the bounded source cursor.
    "language-input": {"app_bytes": 16_000, "memory_bytes": 20_480},
    "source-editor": {"app_bytes": 13_568, "memory_bytes": 18_304},
}
LOCAL_FLOAT_SIZE_BUDGETS = {
    "focal": {"app_bytes": 14_000, "memory_bytes": 20_000},
    "tinybasic": {"app_bytes": 12_000, "memory_bytes": 17_500},
}
# The optional Python packer uses a bounded greedy ZX0 parser. POSIX callers
# can select it explicitly with --packer. Windows builds use PowerShell/.NET.
# Keep separate measured storage ceilings, with the same memory_bytes limits.
GREEDY_APP_SIZE_BUDGETS = {
    (False, "focal"): 13_500,
    (True, "focal"): 15_100,
    (True, "tinybasic"): 13_000,
    (False, "language-input"): 17_000,
    (False, "source-editor"): 14_848,
}
# Compiler FLOW_STEP owns source selection, translation and literal interning.
# Leave ordinary interpreter ceilings unchanged; only external compiler APPs
# pay for this policy. The shared APP arena remains the same 20 KiB.
COMPILER_SIZE_BUDGETS = {
    "tinybasic": {"app_bytes": 15_000, "memory_bytes": 20_480},
    # The FOCAL frontend now emits the shared graphics instructions as well.
    # The measured 19,404-byte image still fits the unchanged 20-KiB arena.
    "focal": {"app_bytes": 14_560, "memory_bytes": 19_648},
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
    if os.environ.get("CI", "").strip().lower() not in ("true", "1"):
        return
    budgets = LOCAL_FLOAT_SIZE_BUDGETS if local_float_math else SYSTEM_SIZE_BUDGETS
    budget = budgets.get(system)
    if language_vm_compiler:
        budget = COMPILER_SIZE_BUDGETS.get(system, budget)
    if system == "language-vm" and split_language_vm:
        # The hot integer-span executor trades APP bytes for fewer dispatches.
        # This is a regression ceiling, not an allocator partition. The loader
        # and strict whole-firmware RAM gate still cap every APP at 20 KiB.
        # BASIC graphics adds raster events, PRINT AT and a pure GRAPH loop.
        budget = {"memory_bytes": 20_480}
    if budget is None:
        return
    budget = dict(budget)
    if system == "focal" and language_vm_compiler and report.get("focal_trace"):
        budget["memory_bytes"] = 19_840
    if greedy_packer:
        greedy_limit = GREEDY_APP_SIZE_BUDGETS.get((local_float_math, system))
        if language_vm_compiler and system == "focal":
            greedy_limit = 15_360  # separate storage ceiling for the .NET parser
        if greedy_limit is not None:
            budget["app_bytes"] = greedy_limit
    exceeded = [f"{field}={report[field]} > {limit}"
                for field, limit in budget.items()
                if report[field] > limit]
    if exceeded:
        raise ValueError(f"{system} size budget exceeded: " + ", ".join(exceeded))


def build(args: argparse.Namespace) -> dict:
    if sys.platform == "win32":
        raise ValueError(
            "Windows APP builds use tools/build-portable-app.ps1 "
            "(PowerShell/.NET). Close Arduino IDE, reinstall its board "
            "with tools/mk61-arduino-board.cmd from the updated project, "
            "then restart Arduino IDE.")
    # FOCAL is now a VM frontend, never a self-contained native interpreter.
    if args.system == "focal":
        args.language_vm_compiler = True
    system = SYSTEM_MODULES.get(args.system)
    resident_language = args.system in ("focal", "tinybasic", "language-vm", "language-input", "source-editor")
    if resident_language and args.local_float_math:
        raise ValueError("language APPs use the resident runtime; local libm is disabled")
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
    if args.system == "vm-file-cache":
        sources += [ROOT / "code/loadable_module_format.cpp", ROOT / "code/zx0.cpp"]
    if args.system == "setup":
        sources += [ROOT / "sdk/portable/system/setup_compat.cpp"]
    if args.system in ("usbdisk", "source-editor"):
        sources += [ROOT / "sdk/portable/system/usbdisk_compat.cpp"]
    sources += [ROOT / "sdk/portable/memory.c"]
    shared_system_runtime = args.system in (
        "focal", "tinybasic", "language-vm", "language-input", "usbdisk", "setup", "markdown-viewer", "vm-file-cache", "source-editor")
    if shared_system_runtime:
        sources += [ROOT / "sdk/portable/system/runtime.S"]
    if args.system in ("focal", "tinybasic", "language-vm", "language-input", "source-editor"):
        sources += [ROOT / "sdk/portable/system/editor.cpp"]
    if args.shared_runtime:
        sources += [ROOT / "sdk/portable/shared_runtime.c", ROOT / "sdk/portable/system/runtime.S"]
    if len(set(sources)) != len(sources):
        raise ValueError("duplicate source")
    pico_target = getattr(args,"target","stm32") == "picocalc-pico-h"
    if pico_target and (args.system or args.shared_runtime):
        raise ValueError("PicoCalc builds use the resident system services; --system/--shared-runtime require STM32")
    cpu_flags = (["-mcpu=cortex-m0plus","-mthumb","-mfloat-abi=soft"] if pico_target else
                 ["-mcpu=cortex-m4","-mthumb","-mfpu=fpv4-sp-d16","-mfloat-abi=hard"])
    rust_target = "thumbv6m-none-eabi" if pico_target else "thumbv7em-none-eabihf"
    flags = [*cpu_flags, "-Oz" if system else "-Os", "-flto", "-fipa-pta",
             "-mword-relocations", "-fno-builtin", "-ffunction-sections", "-fdata-sections",
             "-Wall", "-Wextra", "-Werror"]
    if getattr(args,"focal_trace",False):
        if args.system not in ("focal", "language-vm"):
            raise ValueError("--focal-trace applies only to FOCAL or its shared VM")
        flags.append("-DMK61_FOCAL_TRACE=1")
    if getattr(args, "vm_opcode_profile", False):
        if args.system != "language-vm":
            raise ValueError("--vm-opcode-profile applies only to language-vm")
        flags.append("-DMK61_VM_OPCODE_PROFILE=1")
        if getattr(args,"vm_opcode_profile_no_integer_counts",False):
            flags.append("-DMK61_VM_OPCODE_PROFILE_INTEGER_COUNTS=0")
        if getattr(args,"vm_opcode_profile_counts_only",False):
            flags.append("-DMK61_VM_OPCODE_PROFILE_TIMING=0")
    elif getattr(args,"vm_opcode_profile_no_integer_counts",False) or getattr(args,"vm_opcode_profile_counts_only",False):
        raise ValueError("opcode profile options require --vm-opcode-profile")
    integer_block = getattr(args, "vm_integer_block", None)
    if integer_block is not None:
        if args.system != "language-vm":
            raise ValueError("--vm-integer-block requires language-vm")
        flags.append(f"-DMK61_VM_INTEGER_BLOCK={int(integer_block)}")
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
                       "--target", rust_target,
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
                        f"Rust target {rust_target} is missing; run "
                        f"rustup target add {rust_target}"
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
        if shared_system_runtime and source == ROOT / "sdk/portable/memory.c":
            # Keep SDK strcmp, which has no resident runtime slot. Its compact
            # byte loop avoids linking newlib's much larger ARM routine.
            support += ["-DMK61_APP_SHARED_RUNTIME=1"]
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
         *(["-Wl,--defsym=MK61_MODULE_BYTES=49152"] if pico_target else []),
         "-Wl,--gc-sections,--emit-relocs", "-Wl,--defsym=MK61_MODULE_ORIGIN=0x20000000",
         "-Wl,-T," + str(ROOT / "tools/.mk61-app/mk61_module.ld"),
         "-Wl,-Map," + str(out / (args.name + ".map")),
         *objects, *args.library, *(["-lm"] if args.local_float_math else []),
         *([] if resident_language else (["-lc"] if system else []) + ["-lgcc"]), "-o", elf])
    if run([tool("nm"), "--undefined-only", elf]).strip():
        raise ValueError("APP has unresolved imports")
    if resident_language:
        print(run([sys.executable, ROOT / "tests/check_native_runtime_libraries.py",
                   "--app", out / (args.name + ".map")]), end="")
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
    if pico_target and packer is None:
        packer = python_packer
    if packer is None:
        configured = os.environ.get("MK61_MODULE_PACK_BIN")
        packer = (Path(configured).expanduser() if configured else
                  ROOT / (".build/tools/mk61_module_pack" + suffix))
        run(["bash", ROOT / "tools/build_mk61_module_pack.sh", "--help"])
    greedy_packer = packer.resolve() == python_packer
    command = [packer]
    if pico_target and greedy_packer:
        command += ["--target", "picocalc-pico-h"]
    command += ["--portable", "--kind", "app" if args.system in ("vm-file-cache", "source-editor") else args.system or "app", "--image", image,
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
    if pico_target:
        import zlib
        container = bytearray(app.read_bytes())
        struct.pack_into("<I",container,16,struct.unpack_from("<I",container,16)[0] | 8)
        struct.pack_into("<I",container,60,zlib.crc32(container[:60]) & 0xffffffff)
        app.write_bytes(container)
    image_flags = struct.unpack_from("<I", app.read_bytes(), 16)[0]
    report = {"name": args.name, "target": getattr(args,"target","stm32"), "abi": 6, "load_address": base,
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
    if getattr(args, "vm_opcode_profile", False):
        report["vm_opcode_profile"] = True
        report["vm_opcode_profile_raw_service"] = True
        report["vm_opcode_profile_integer_counts"] = not getattr(args,"vm_opcode_profile_no_integer_counts",False)
        report["vm_opcode_profile_timing"] = not getattr(args,"vm_opcode_profile_counts_only",False)
        report["vm_opcode_profile_phase"] = "body-including-decode-dispatch"
    if args.system in ("language-vm", "language-input"):
        report["vm_integer_block"] = (
            not args.local_float_math if integer_block is None else integer_block)
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
    parser.add_argument("--target", choices=("stm32","picocalc-pico-h"), default="stm32")
    parser.add_argument("--name")
    parser.add_argument("--source", type=Path, action="append", default=[])
    parser.add_argument("--system", choices=SYSTEM_MODULES)
    parser.add_argument("--focal-trace", action="store_true", help="enable opt-in FOCAL Serial diagnostics in frontend/VM")
    parser.add_argument("--vm-opcode-profile", action="store_true",
                        help="diagnostic DWT opcode groups; requires resident opcode-profile service")
    parser.add_argument("--vm-opcode-profile-no-integer-counts",action="store_true",
                        help="omit scalar operand-type census for a compact cycle-attribution pass")
    parser.add_argument("--vm-opcode-profile-counts-only",action="store_true",
                        help="count groups/types without cycle sampling; same executor and size ceilings")
    parser.add_argument("--vm-integer-block", action=argparse.BooleanOptionalAction,
                        default=None, help="guarded integer sequence (on except local float); unchanged bytecode/ABI")
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
                        help="retired: language APPs always use the resident math runtime")
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
