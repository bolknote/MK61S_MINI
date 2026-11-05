#!/usr/bin/env python3
"""Run a repository ARM test with a safe host preflight and the current Python.

This launcher does not elevate permissions. On macOS sandbox denial, rerun
this same command through the caller's ordinary approval mechanism.
"""
import argparse
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tests'))
from unicorn_runtime import UnicornHostError, ensure_compatible_host


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('script', type=Path, help='repository Python test or measurement script')
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    script = args.script.resolve()
    if not script.is_file() or script.suffix != '.py' or not script.is_relative_to(ROOT):
        parser.error('script must be a Python file in this repository')
    try:
        ensure_compatible_host()
    except UnicornHostError as error:
        parser.exit(2, str(error)+'\n')
    # Preserve direct-script import/argv behavior, including nested test folders.
    sys.path.insert(0, str(script.parent))
    sys.argv = [str(script), *args.arguments]
    runpy.run_path(str(script), run_name='__main__')


if __name__ == '__main__':
    main()
