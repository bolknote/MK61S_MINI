#!/usr/bin/env python3
"""Evaluate a frozen native model on predeclared Russian tasks and hidden cases.

This reads checkpoints, never trains them. Dev conditions and held-out
conditions are separate. The JSONL SHA is recorded before the executable runs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import shutil

ROOT = Path(__file__).resolve().parents[3]


def evaluate(executable, package, cases, output, prefix=None, planning=True, arithmetic="lut-fp32", linear="reference", filter_head=False):
    raw = cases.read_bytes()
    tasks = [json.loads(line) for line in raw.decode().splitlines() if line.strip()]
    if len({task["id"] for task in tasks}) != len(tasks):
        raise ValueError("duplicate task IDs")
    output.mkdir(parents=True, exist_ok=True)
    if (output / "results.jsonl").exists():
        raise ValueError("results already exist; use a new output directory")
    runtime_sources = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                       for path in sorted((ROOT / "code").glob("mk61_ai*")) if path.is_file()}
    frozen = {"sha256": hashlib.sha256(raw).hexdigest(), "rows": len(tasks),
              "model_sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
              "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
              "prefix_sha256": hashlib.sha256(prefix.read_bytes()).hexdigest() if prefix else "firmware-default",
              "runtime_sources": runtime_sources,
              "planning": planning,
              "arithmetic": arithmetic,
              "linear": linear, "filter_head": filter_head,
              "policy": "All declared rows count; runtime errors and context failures fail. No reruns or best-of selection."}
    (output / "frozen.json").write_text(json.dumps(frozen, ensure_ascii=False, indent=2) + "\n")
    lines = []
    for task in tasks:
        columns = [task["id"], task["task"], task.get("code", ""), *task["cases"]]
        if any("\n" in item or "\t" in item or "\r" in item for item in columns):
            raise ValueError("TSV control character in condition")
        lines.append("\t".join(columns))
    tsv = output / "conditions.tsv"
    tsv.write_text("\n".join(lines) + "\n")
    command = [str(executable.resolve()), str(package.resolve()), str(tsv.resolve())]
    if prefix:
        command.append(str(prefix.resolve()))
    if not planning:
        command.append("--no-plan")
    command.append("--arithmetic=" + arithmetic)
    command.append("--linear=" + linear)
    if filter_head:
        command.append("--filter-head")
    with (output / "results.jsonl").open("w") as results, (output / "progress.log").open("w") as progress:
        subprocess.run(command, stdout=results, stderr=progress, check=True)
    rows = [json.loads(line) for line in (output / "results.jsonl").read_text().splitlines()]
    if [row["id"] for row in rows] != [task["id"] for task in tasks]:
        raise ValueError("incomplete or reordered evaluation")
    total_replies = sum(row["replies"] for row in rows)
    passed = sum(row["passed"] for row in rows)
    report = {**frozen, "passed": passed, "total": len(rows), "accuracy": passed / len(rows),
              "valid_replies": sum(row["valid_replies"] for row in rows), "replies": total_replies,
              "public_cases": sum("PUBLIC=0" not in case for task in tasks for case in task["cases"]),
              "hidden_cases": sum("PUBLIC=0" in case for task in tasks for case in task["cases"]),
              "source": str(cases), "scope": "Functional outcomes, including register/preserve/scenario assertions; no claim of novel algorithm families or device speed."}
    report["families"] = {}
    for task, row in zip(tasks, rows):
        item = report["families"].setdefault(task["family"], {"passed": 0, "total": 0})
        item["passed"] += row["passed"]
        item["total"] += 1
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"passed": passed, "total": len(rows), "accuracy": report["accuracy"], "valid_replies": report["valid_replies"], "replies": total_replies}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, default=ROOT / ".build/mk61ai/evaluator")
    parser.add_argument("--build", action="store_true", help="Compile the native host evaluator")
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prefix", type=Path)
    parser.add_argument("--no-plan", action="store_true")
    parser.add_argument("--arithmetic", choices=["lut-fp32", "fp32", "int8", "lut-int8"], default="lut-fp32")
    parser.add_argument("--linear", choices=["reference", "flash", "sram"], default="reference")
    parser.add_argument("--filter-head", action="store_true")
    args = parser.parse_args()
    if args.build or not args.executable.exists():
        compiler, cc = shutil.which("clang++"), shutil.which("clang")
        if not compiler or not cc:
            parser.error("clang/clang++ are required to build the host evaluator")
        args.executable.parent.mkdir(parents=True, exist_ok=True)
        obj = args.executable.with_suffix(".kernels.o")
        subprocess.run([cc, "-std=c11", "-O2", "-c", str(ROOT / "code/mk61_ai_kernels.c"), "-o", str(obj)], check=True)
        sources = ["mk61_ai_model.cpp", "mk61_ai_linear.cpp", "mk61_ai_tokenizer.cpp", "mk61_ai_harness.cpp", "mk61_ai_tools.cpp", "mk61_ai_agent.cpp", "mk61_ai_grammar.cpp", "mk61emu_core.cpp"]
        subprocess.run([compiler, "-std=c++17", "-O2", "-ffp-contract=off", "-DMK61_CORE_STANDALONE=1", "-DMK61_CORE_HOT_TABLES_IN_SRAM=0", "-I" + str(ROOT / "code"),
                        *(str(ROOT / "code" / name) for name in sources), str(obj), str(ROOT / "tests/mk61_ai_eval.cpp"), "-o", str(args.executable)], check=True)
    evaluate(args.executable, args.package, args.cases, args.output, args.prefix, not args.no_plan, args.arithmetic,args.linear,args.filter_head)


if __name__ == "__main__":
    main()
