#!/usr/bin/env python3
"""Reproduce the experimental language-VM size gate, without flashing hardware.

Includes the existing editors in both native compiler APPs, the complete VM
APP (input, rendering, validation, control stacks), and full bytecode images.
The JSON explicitly distinguishes native-image savings from loaded APP RAM.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import m8_codec


def run(command: list[str | Path]) -> str:
    result = subprocess.run([str(x) for x in command], cwd=ROOT, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


def corpus(destination: Path) -> list[tuple[str, Path, str]]:
    sources = []
    for path in sorted((ROOT / "programs/games/High Noon").glob("*.tbi")):
        sources.append(("basic", path, path.read_text(encoding="utf-8")))
    # Existing test programs are the FOCAL corpus; extract adjacent C++ string
    # literals only from source-taking calls, never editor/name expectations.
    expression = re.compile(
        r'(?:add_program|TinyBasicTestAddProgram)\(\s*'
        r'((?:"(?:[^"\\]|\\.)*"\s*)+)', re.MULTILINE)
    literal = re.compile(r'"(?:[^"\\]|\\.)*"')
    for language, name in (("basic", "tinybasic"), ("focal", "focal")):
        text = (ROOT / f"tests/{name}_self_test.cpp").read_text(encoding="utf-8")
        seen = set()
        for index, match in enumerate(expression.finditer(text)):
            source = "".join(ast.literal_eval(x) for x in literal.findall(match.group(1)))
            if source in seen:
                continue
            seen.add(source)
            sources.append((language, Path(f"{name}-test-{index:03d}"), source))
    for language, name, source in sources:
        output = destination / (name.stem + (".tbi" if language == "basic" else ".foc"))
        output.write_bytes(m8_codec.encode(source))
        yield language, output, str(name.relative_to(ROOT)) if name.is_absolute() else str(name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm-toolchain-bin", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "tmp/language-vm")
    parser.add_argument("--reuse-builds", action="store_true")
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    native = {}
    builds = [
        ("baseline/tinybasic", "tinybasic", "BASIC", []),
        ("baseline/focal", "focal", "FOCAL", []),
        ("baseline-local/tinybasic", "tinybasic", "BASIC", ["--local-float-math"]),
        ("baseline-local/focal", "focal", "FOCAL", ["--local-float-math"]),
        ("compiler/tinybasic", "tinybasic", "BASIC", ["--language-vm-compiler"]),
        ("compiler/focal", "focal", "FOCAL", ["--language-vm-compiler"]),
        ("runner/core", "language-vm", "LANGVM", []),
        ("runner/local", "language-vm", "LANGVM", ["--local-float-math"]),
    ]
    for directory, system, basename, flags in builds:
        report = out / directory / f"{basename}.json"
        if not args.reuse_builds or not report.is_file():
            print(f"building {directory}", flush=True)
            run([sys.executable, ROOT / "tools/build_portable_app.py", "--system", system,
                 "--output-dir", report.parent, "--arm-toolchain-bin", args.arm_toolchain_bin,
                 *flags])
        native[directory] = json.loads(report.read_text())
    probe = out / "probe"
    compiler = shutil.which("clang++") or shutil.which("c++")
    if not compiler:
        raise RuntimeError("host C++ compiler required")
    run([compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
         "-I" + str(ROOT / "code"), ROOT / "tools/language_vm_probe.cpp",
         ROOT / "code/language_bytecode.cpp", ROOT / "code/language_vm.cpp",
         ROOT / "code/zx0_encode.cpp", "-o", probe])
    programs_dir = out / "corpus"
    programs_dir.mkdir(exist_ok=True)
    programs = []
    for language, path, origin in corpus(programs_dir):
        measured = json.loads(run([probe, language, path, path.with_suffix(".bvm")]))
        programs.append({"language": language, "origin": origin, **measured,
                         "growth_percent": round(100 * (measured["bytecode_bytes"] /
                                                       measured["source_bytes"] - 1), 2)})
    comparisons = {}
    for mode, prefix, runner in (("resident_math", "baseline", "runner/core"),
                                  ("local_float", "baseline-local", "runner/local")):
        before = [native[f"{prefix}/tinybasic"], native[f"{prefix}/focal"]]
        after = [native["compiler/tinybasic"], native["compiler/focal"], native[runner]]
        comparison = {}
        for field in ("image_bytes", "app_bytes"):
            a, b = sum(x[field] for x in before), sum(x[field] for x in after)
            comparison[field] = {"before": a, "after": b, "delta": b - a}
        comparison["loaded_app_ram_savings"] = {
            "basic": before[0]["memory_bytes"] - native[runner]["memory_bytes"],
            "focal": before[1]["memory_bytes"] - native[runner]["memory_bytes"],
        }
        comparison["excludes"] = ["resident handoff delta", "source/output staging",
                                  "workspace layout changes", "C-stack high-water"]
        comparison["size_gate_passed"] = comparison["image_bytes"]["delta"] < 0
        comparisons[mode] = comparison
    report = {
        "head": run(["git", "rev-parse", "HEAD"]).strip(),
        "status": "experimental; not enabled in resident; no persistent cache",
        "native": native, "comparisons": comparisons, "programs": programs,
        "workspace_bytes": 8192,
        "notes": ["Compiler APPs retain the existing editors.",
                  "VM APP includes expression input, verifier, rendering and BSS.",
                  "RAM savings describe replacement of the loaded APP only, not whole-device peaks.",
                  "Resident LIBM/CORE share the same service-based APP; arithmetic behavior is tested separately.",
                  "Source and bytecode compression use the existing bounded ZX0 encoder."]}
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"comparisons": comparisons, "programs": len(programs)}, indent=2))


if __name__ == "__main__":
    main()
