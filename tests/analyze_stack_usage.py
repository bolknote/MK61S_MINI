#!/usr/bin/env python3
"""Compile a non-shipping ``-fstack-usage`` pass from compile_commands.json.

The production command is never modified or re-linked. This matters for LTO:
asking GCC for stack reports during the shipping link can change partitioning,
code size and the exact resident symbols consumed by F401 System APPs.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import ctypes
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

import check_stack_usage


VALUE_OPTIONS = {"-o", "-MF", "-MT", "-MQ", "-MJ"}
DROP_OPTIONS = {"-MMD", "-MD", "-MP", "-MG", "-ffat-lto-objects",
                "-fno-fat-lto-objects", "-fstack-usage", "-fno-lto"}


def windows_command_line(command: str) -> list[str]:
    count = ctypes.c_int()
    argv = ctypes.windll.shell32.CommandLineToArgvW(command, ctypes.byref(count))
    if not argv:
        raise OSError("CommandLineToArgvW failed")
    try:
        return [argv[index] for index in range(count.value)]
    finally:
        ctypes.windll.kernel32.LocalFree(argv)


def entry_arguments(entry: dict[str, object]) -> list[str]:
    arguments = entry.get("arguments")
    if isinstance(arguments, list) and all(
        isinstance(argument, str) for argument in arguments
    ):
        return list(arguments)
    command = entry.get("command")
    if not isinstance(command, str) or not command:
        raise ValueError("compile database entry has no arguments or command")
    return windows_command_line(command) if os.name == "nt" else shlex.split(command)


def same_path(left: str, right: Path, directory: Path) -> bool:
    try:
        candidate = Path(left)
        if not candidate.is_absolute():
            candidate = directory / candidate
        return candidate.resolve() == right.resolve()
    except (OSError, RuntimeError):
        return False


def analysis_arguments(
    entry: dict[str, object], output_object: Path
) -> tuple[list[str], Path]:
    source_value = entry.get("file")
    directory_value = entry.get("directory")
    if not isinstance(source_value, str) or not isinstance(directory_value, str):
        raise ValueError("compile database entry lacks file/directory")
    source = Path(source_value)
    directory = Path(directory_value)
    if not source.is_absolute():
        source = directory / source
    source = source.resolve()

    original = entry_arguments(entry)
    if not original:
        raise ValueError(f"empty compiler command for {source}")
    rewritten = [original[0]]
    index = 1
    have_compile_only = False
    while index < len(original):
        argument = original[index]
        if argument in VALUE_OPTIONS:
            index += 2
            continue
        if argument in DROP_OPTIONS or argument.startswith("-flto"):
            index += 1
            continue
        if same_path(argument, source, directory):
            index += 1
            continue
        if argument == "-c":
            have_compile_only = True
        rewritten.append(argument)
        index += 1
    if not have_compile_only:
        rewritten.append("-c")
    rewritten.extend(("-fno-lto", "-fstack-usage", str(source),
                      "-o", str(output_object)))
    return rewritten, directory


def is_below(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def selected_entries(
    entries: list[dict[str, object]], roots: list[Path], sources: list[Path]
) -> list[dict[str, object]]:
    exact = {source.resolve() for source in sources}
    selected: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        source_value = entry.get("file")
        directory_value = entry.get("directory")
        if not isinstance(source_value, str) or not isinstance(directory_value, str):
            continue
        source = Path(source_value)
        if not source.is_absolute():
            source = Path(directory_value) / source
        source = source.resolve()
        if source not in exact and not any(is_below(source, root) for root in roots):
            continue
        key = (str(source), json.dumps(entry, sort_keys=True))
        if key not in seen:
            selected.append(entry)
            seen.add(key)
    return selected


def compile_one(
    entry: dict[str, object], output_object: Path
) -> tuple[Path, str]:
    arguments, directory = analysis_arguments(entry, output_object)
    completed = subprocess.run(
        arguments, cwd=directory, capture_output=True, text=True, check=False
    )
    output = completed.stdout + completed.stderr
    if completed.returncode != 0:
        source = entry.get("file", "unknown")
        raise RuntimeError(
            f"stack analysis compile failed for {source} "
            f"({completed.returncode}):\n{output}"
        )
    return output_object, output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compile-commands", required=True, type=Path)
    parser.add_argument("--source-root", action="append", type=Path, default=[])
    parser.add_argument("--source", action="append", type=Path, default=[])
    parser.add_argument("--jobs", type=int, default=min(os.cpu_count() or 1, 8))
    parser.add_argument("--max-frame", type=int,
                        default=check_stack_usage.DEFAULT_MAX_FRAME)
    parser.add_argument("--top", type=int, default=5)
    args = parser.parse_args()
    if not args.source_root and not args.source:
        parser.error("at least one --source-root or --source is required")
    if args.jobs <= 0:
        parser.error("--jobs must be positive")

    try:
        raw = json.loads(args.compile_commands.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("compile database root is not an array")
        entries = selected_entries(raw, args.source_root, args.source)
        if not entries:
            raise ValueError("no selected translation units in compile database")
        with tempfile.TemporaryDirectory(prefix="mk61-stack-analysis-") as temporary:
            work = Path(temporary)
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=min(args.jobs, len(entries))
            ) as executor:
                futures = [
                    executor.submit(compile_one, entry, work / f"unit-{index}.o")
                    for index, entry in enumerate(entries)
                ]
                for future in futures:
                    _object, output = future.result()
                    if output:
                        print(output, end="", file=sys.stderr)
            reports, records = check_stack_usage.read_records(work)
            print(f"stack analysis: compiled={len(entries)} shipping_artifact=untouched")
            return 0 if check_stack_usage.print_report(
                reports, records, args.max_frame, args.top
            ) else 1
    except (OSError, UnicodeError, ValueError, RuntimeError,
            json.JSONDecodeError, check_stack_usage.StackUsageError) as error:
        print(f"stack analysis: FAIL: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
