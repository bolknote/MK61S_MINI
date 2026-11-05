#!/usr/bin/env python3
"""Build the bounded URQ player and copy its ready-to-open text library."""

import sys as _repo_sys
from pathlib import Path as _RepoPath
_repo_sys.path.insert(0, str(_RepoPath(__file__).resolve().parents[3]))
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "dev/tools"), str(ROOT / "dev/lib")]
from tools.firmware.picocalc.build_picocalc import compiler_bin
from tools.apps.urq.library import copy_device_library, copy_licenses


def build(target, toolchain, work, output, library=None, licenses=None):
    names = ["URQ"] + (["URQUI"] if target == "stm32" else [])
    reports = []
    for name in names:
        source = "main.cpp" if name == "URQ" else "cold.cpp"
        directory = work / name
        command = [sys.executable, str(ROOT / "tools/apps/portable/build_portable_app.py"), "--target", target,
                   "--name", name, "--shared-runtime", "--optimize-size", "--arm-toolchain-bin", str(toolchain),
                   "--output-dir", str(directory), "--source", str(ROOT / "examples/portable-apps/URQ" / source)]
        for path in ["code/urq/engine.cpp", "code/urq/pack.cpp", "code/zx0.cpp"]:
            command += ["--source", str(ROOT / path)]
        if name == "URQ": command += ["--handled-magic", "C2"]
        subprocess.run(command, check=True)
        subprocess.run([sys.executable,str(ROOT/"tests/analyze_stack_usage.py"),
            "--compile-commands",str(directory/"compile_commands.json"),
            "--source-root",str(ROOT/"examples/portable-apps/URQ"),"--source-root",str(ROOT/"code/urq"),
            "--max-frame","5120","--top","1","--summary-json",str(directory/"stack-usage.json")],check=True)
        report = json.loads((directory / (name + ".json")).read_text())
        limit = 20480 if target == "stm32" else 49152
        if report["memory_bytes"] > limit: raise ValueError(f"{name}: APP memory limit")
        report["app_sha256"] = hashlib.sha256((directory / (name + ".APP")).read_bytes()).hexdigest()
        report["resources"]={"workspace_limit":8192,"shell_limit":1600 if target=="stm32" else 3072,
            "optional_history":0 if target=="stm32" else 262144,
            "page_cache_in_workspace":512,"expression_scratch_in_workspace":1536,
            "maximum_frame":json.loads((directory/"stack-usage.json").read_text())["max_frame"]}
        reports.append(report)
    output.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copy2(work / name / (name + ".APP"), output / (name + ".APP"))
        shutil.copy2(work / name / (name + ".json"), output / (name + ".json"))
    (output / "urq-build.json").write_text(json.dumps(reports, indent=2) + "\n")
    if library:
        copy_device_library(library)
    if licenses:
        copy_licenses(licenses)
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=["stm32", "picocalc-pico-h"], default="stm32")
    parser.add_argument("--toolchain", type=Path)
    parser.add_argument("--build-dir", type=Path, default=ROOT / ".build/urq-apps")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--library-output", type=Path)
    parser.add_argument("--licenses-output", type=Path)
    args = parser.parse_args()
    build(args.target, compiler_bin(args.toolchain), args.build_dir / args.target,
          args.output_dir, args.library_output, args.licenses_output)


if __name__ == "__main__": main()
