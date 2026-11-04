#!/usr/bin/env python3
"""Reject accidental reads from an installed Arduino/STM32duino package."""
import argparse
import json
from pathlib import Path
import re
import shlex
from analyze_stack_usage import entry_arguments
import subprocess

FORBIDDEN = re.compile(r"(?:^|/)(?:arduino15|\.arduino15|cores/arduino|libraries/srcwrapper)(?:/|$)", re.I)


def check_paths(paths):
    bad = [str(p) for p in paths if FORBIDDEN.search(str(p).replace("\\", "/"))]
    if bad:
        raise ValueError("Installed Arduino package entered native build: " + ", ".join(bad[:5]))


def include_paths(arguments):
    result = []
    index = 0
    while index < len(arguments):
        value = arguments[index]
        if value in ('-I', '-isystem', '-iquote'):
            index += 1
            result.append(Path(arguments[index]))
        elif value.startswith('-I'):
            result.append(Path(value[2:]))
        index += 1
    return result


def make_dependencies(text):
    text = re.sub(r'\\\r?\n', '', text)
    separator = re.search(r'(?<!\\):[ \t]', text)
    if not separator:
        raise ValueError('GNU dependency target is missing')
    return shlex.split(text[separator.end():])


def check(database, dependencies=True, arduino=False):
    entries = json.loads(Path(database).read_text())
    assert entries, "compile database is empty"
    sdk = None
    for entry in entries:
        args = entry_arguments(entry)
        check_paths([entry["file"], *args])
        includes = include_paths(args)
        candidates = [p.parent.parent for p in includes if p.as_posix().endswith("/cmsis/include")]
        assert len(candidates) == 1, "native CMSIS include root is missing or ambiguous"
        if sdk is None:
            sdk = candidates[0]
        assert candidates[0] == sdk, "translation units use different SDKs"
        assert (sdk / "manifest.json").is_file(), "native SDK manifest missing"
        assert not any("CMSIS_DSP" in str(v) for v in includes), "unused external DSP path returned"
    if dependencies and arduino:
        headers = []
        for entry in entries:
            args = entry_arguments(entry)
            assert '-o' in args, 'native Arduino object output is missing'
            output = Path(args[args.index('-o') + 1])
            dependency = output.with_suffix('.d')
            if not dependency.is_file():
                # The empty, installed core anchor may be reused from the
                # Arduino core archive cache. Its source/includes above and
                # installed payload are still checked; it has no headers.
                source = str(entry['file']).replace('\\', '/')
                assert source.endswith('/cores/mk61/core.cpp'), ('native header dependency missing', dependency)
                continue
            headers += make_dependencies(dependency.read_text())
        assert headers, 'Arduino header dependencies are missing'
        check_paths(headers)
    elif dependencies:
        text = subprocess.check_output(["ninja", "-C", str(Path(database).resolve().parent), "-t", "deps"], text=True)
        headers = [v.strip() for v in text.splitlines() if v.startswith(" ")]
        assert headers, "Ninja header dependencies are missing"
        check_paths(headers)
    return sdk


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument('--arduino', action='store_true', help='check native Arduino .d files instead of Ninja deps')
    args = parser.parse_args()
    print("Independent native SDK and header dependency gate PASS:", check(args.database, arduino=args.arduino))
