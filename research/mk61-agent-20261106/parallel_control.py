"""Run the independent no-plan control on the second B200, with one-writer locking."""
import json
import os
import time

os.environ["MK61_AGENT_GPU"] = "1"
from run_experiment import BASE, SCRIPT, run


def main():
    relative = ".build/mk61-agent-20261106/"
    run("no-plan-parallel.log", SCRIPT + "train.py", "--phase", "sft", "--initial", relative + "domain/last",
        "--data", relative + "training/sft-combined-v2.jsonl", "--tasks", relative + "tasks/validation-extended-v2.jsonl",
        "--output", relative + "no-plan", "--steps", "3000", "--batch", "32", "--micro-batch", "16",
        "--context", "512", "--lr", "0.00015", "--qat-start", "2001", "--no-plan")
    (BASE / "parallel-control.json").write_text(json.dumps({"phase": "completed", "unix": time.time(), "gpu": 1}, indent=2) + "\n")


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        (BASE / "parallel-control.json").write_text(json.dumps({"phase": "failed", "error": str(error)}, indent=2) + "\n")
        raise
