#!/usr/bin/env python3
"""Build the canonical /System directory with the unified current APP ABI."""

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = (
    "FOCAL.APP", "BASIC.APP", "WBMP.APP", "MARKDOWN.APP", "CHIP8.APP",
    "SETUP.APP", "USBDISK.APP", "HELP0.TXT", "HELP1.TXT",
)
MODULES = (
    ("setup", "SETUP.APP", "setup"),
    ("focal", "FOCAL.APP", "focal"),
    ("basic", "BASIC.APP", "tinybasic"),
    ("wbmp", "WBMP.APP", "wbmp-viewer"),
    ("markdown", "MARKDOWN.APP", "markdown-viewer"),
    ("chip8", "CHIP8.APP", "chip8"),
    ("usbdisk", "USBDISK.APP", "usbdisk"),
)


def run(command: list[str | Path]) -> None:
    result = subprocess.run([str(item) for item in command])
    if result.returncode:
        raise RuntimeError(
            f"{Path(str(command[0])).name} failed with exit code "
            f"{result.returncode}")


def compiler_from_database(path: Path) -> Path:
    entries = json.loads(path.read_text(encoding="utf-8"))
    for entry in entries:
        arguments = entry.get("arguments")
        if arguments:
            candidate = str(arguments[0])
        else:
            command = entry.get("command", "")
            parts = shlex.split(command, posix=os.name != "nt") if command else []
            candidate = parts[0].strip('"') if parts else ""
        resolved = shutil.which(candidate) or candidate
        if resolved and Path(resolved).is_file():
            return Path(resolved).resolve()
    raise ValueError("ARM compiler is missing from compile_commands.json")


def boolean(value: str) -> bool:
    if value not in ("0", "1"):
        raise argparse.ArgumentTypeError("expected 0 or 1")
    return value == "1"


def build(args: argparse.Namespace) -> dict:
    resident = args.resident_elf.resolve()
    if not resident.is_file():
        raise ValueError(f"resident ELF not found: {resident}")
    if args.arm_toolchain_bin:
        toolchain = args.arm_toolchain_bin.resolve()
    else:
        if not args.compile_commands:
            raise ValueError("provide --compile-commands or --arm-toolchain-bin")
        database = args.compile_commands.resolve()
        if not database.is_file():
            raise ValueError(f"compile database not found: {database}")
        toolchain = compiler_from_database(database).parent
    suffix = ".exe" if os.name == "nt" else ""
    if not (toolchain / ("arm-none-eabi-gcc" + suffix)).is_file():
        raise ValueError(f"ARM GCC toolchain not found in: {toolchain}")

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    enabled = {
        "setup": True,
        "focal": args.focal,
        "basic": args.basic,
        "wbmp": args.wbmp and not args.markdown,
        "markdown": args.markdown,
        "chip8": args.chip8,
        "usbdisk": True,
    }
    built: list[str] = []
    with tempfile.TemporaryDirectory(prefix="mk61-system-app-") as temporary:
        work = Path(temporary)
        stage = work / "System"
        stage.mkdir()
        for key, filename, system in MODULES:
            if not enabled[key]:
                continue
            command: list[str | Path] = [
                sys.executable, ROOT / "tools/build_portable_app.py",
                "--system", system,
                "--arm-toolchain-bin", toolchain,
                "--output-dir", work / key,
            ]
            if args.packer:
                command += ["--packer", args.packer.resolve()]
            if not args.ui_fonts:
                command.append("--no-ui-fonts")
            if system == "markdown-viewer" and not args.graphics:
                command.append("--text-only")
            if args.local_float_math and system in ("focal", "tinybasic"):
                command.append("--local-float-math")
            run(command)
            shutil.copy2(work / key / filename, stage / filename)
            built.append(filename)

        run([sys.executable, ROOT / "tools/.mk61-app/build_terminal_help.py",
             "--resident-elf", resident, "--output-dir", stage])
        built += ["HELP0.TXT", "HELP1.TXT"]

        # Replace only files owned by this builder. Other /System files, if
        # any, belong to the caller and are deliberately left untouched.
        for filename in CANONICAL:
            destination = output / filename
            source = stage / filename
            if source.is_file():
                temporary_file = output / (filename + ".tmp")
                shutil.copy2(source, temporary_file)
                os.replace(temporary_file, destination)
            elif destination.exists():
                destination.unlink()

    result = {
        "abi": 6,
        "resident": str(resident),
        "output": str(output),
        "apps": built,
        "graphics": args.graphics,
        "ui_fonts": args.ui_fonts,
        "local_float_math": args.local_float_math,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resident-elf", type=Path, required=True)
    parser.add_argument("--compile-commands", type=Path)
    parser.add_argument("--arm-toolchain-bin", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--packer", type=Path)
    parser.add_argument("--graphics", type=boolean, default=True)
    parser.add_argument("--ui-fonts", type=boolean, default=True)
    parser.add_argument("--focal", type=boolean, default=True)
    parser.add_argument("--basic", type=boolean, default=True)
    parser.add_argument("--wbmp", type=boolean, default=True)
    parser.add_argument("--markdown", type=boolean, default=True)
    parser.add_argument("--chip8", type=boolean, default=True)
    parser.add_argument("--local-float-math", type=boolean, default=False)
    args = parser.parse_args()
    try:
        build(args)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        parser.exit(1, f"System APP build: {error}\n")


if __name__ == "__main__":
    main()
