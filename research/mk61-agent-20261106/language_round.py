"""Continue both arms on Russian conditions, then run regression and fresh audits."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[2]
BASE = REPO / ".build/mk61-agent-20261106"
REL = ".build/mk61-agent-20261106/"
SCRIPT = "research/mk61-agent-20261106/"


def status(phase, **extra):
    row = {"phase": phase, "unix": time.time(), **extra}
    (BASE / "language-status.json").write_text(json.dumps(row, indent=2) + "\n")
    print(json.dumps(row), flush=True)


def worker(arm):
    os.environ["MK61_AGENT_GPU"] = "0" if arm == "plan" else "1"
    from run_experiment import run
    run(f"language-{arm}.log", SCRIPT + "train.py", "--phase", "sft", "--initial", REL + arm + "/last",
        "--data", REL + "language-data/train.jsonl", "--tasks", REL + "language-data/validation.jsonl",
        "--output", REL + "language-" + arm, "--steps", "2000", "--batch", "32", "--micro-batch", "16",
        "--context", "512", "--lr", "0.00008", "--qat-start", "1", *(["--no-plan"] if arm == "no-plan" else []))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", choices=["plan", "no-plan"])
    args = parser.parse_args()
    if args.worker:
        worker(args.worker)
        return
    status("russian_conditions_training", arms=["plan", "no-plan"], steps=2000, qat_start=1)
    processes = []
    for arm in ["plan", "no-plan"]:
        stream = (BASE / f"language-{arm}-controller.log").open("w")
        process = subprocess.Popen([sys.executable, "-u", __file__, "--worker", arm], cwd=REPO,
                                   stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT)
        processes.append((arm, process, stream))
    for arm, process, stream in processes:
        result = process.wait()
        stream.close()
        if result:
            raise RuntimeError(f"Language training failed: {arm}")
    status("russian_conditions_evaluation")
    from run_experiment import run
    sets = {"basic": "tasks/basic.jsonl", "regression": "tasks/test-extended-v2.jsonl",
            "language-validation": "language-data/validation.jsonl", "diagnostic": "tasks/natural.jsonl",
            "fresh-natural": "language-data/audit.jsonl"}
    for arm in ["plan", "no-plan"]:
        for split, path in sets.items():
            for q4 in [False, True]:
                label = "language-" + arm + ("-q4" if q4 else "-fp32") + "-" + split
                run(label + ".log", SCRIPT + "evaluate.py", "--model", REL + "language-" + arm + "/best",
                    "--tasks", REL + path, "--output", REL + "language-results/" + label + ".json",
                    "--max-new", "160", *(["--q4"] if q4 else []), *(["--no-plan"] if arm == "no-plan" else []))
    comparison = {}
    for path in (BASE / "language-results").glob("*.json"):
        value = json.loads(path.read_text())
        comparison[path.stem] = {k: value[k] for k in ["total", "passed", "pass_rate", "valid_tool_tasks", "by_kind", "q4"]}
    (BASE / "language-comparison.json").write_text(json.dumps(comparison, ensure_ascii=False, indent=2) + "\n")
    status("language_comparison_complete")


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        if "--worker" not in sys.argv:
            status("failed", error=f"{type(error).__name__}: {error}")
        raise
