"""Isolated remote controller; never modifies another experiment or service."""
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[2]
BASE = REPO / ".build/mk61-agent-20261106"
SCRIPT = "research/mk61-agent-20261106/"
IMAGE = "sha256:a3bc7f09c1e2e72e068021feb75118c92e98c538706caa0c5d1acc0bb9252623"
GPU = os.environ.get("MK61_AGENT_GPU", "0")


def status(phase, **kwargs):
    value = {"phase": phase, "unix": time.time(), **kwargs}
    (BASE / "remote-status.json").write_text(json.dumps(value, indent=2) + "\n")
    print(json.dumps(value), flush=True)


def run(log, *args, timeout=10800):
    command = ["sudo", "-n", "docker", "run", "--rm", "--gpus", "device=" + GPU,
               "--cpus=4", "--memory=10g", "--shm-size=512m", "--user", f"{os.getuid()}:{os.getgid()}",
               "--env", "HF_HUB_OFFLINE=1", "--env", "TRANSFORMERS_OFFLINE=1", "--env", "HF_HOME=/tmp/hf",
               "--env", "PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True",
               "--env", "TOKENIZERS_PARALLELISM=false", "--volume", f"{REPO}:/work", "--workdir", "/work",
               "--entrypoint", "python3", IMAGE, "-u", *args]
    log_path = BASE / log
    if log_path.exists():
        log_path.rename(log_path.with_name(log_path.stem + f".previous-{int(time.time())}.log"))
    with log_path.open("w") as stream:
        result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"Command failed: {log}")


def assess(model, label, split, *, q4=False, no_plan=False):
    flags = (["--q4"] if q4 else []) + (["--no-plan"] if no_plan else [])
    relative = ".build/mk61-agent-20261106/"
    task_file = split if split == "basic" else split + "-extended-v2"
    result_path = BASE / f"results/{label}-{split}.json"
    if result_path.exists() and label.startswith("original-"):
        result = json.loads(result_path.read_text())
        expected_hash = hashlib.sha256((BASE / f"tasks/{task_file}.jsonl").read_bytes()).hexdigest()
        if result["tasks_sha256"] == expected_hash and result["max_new_tokens_per_turn"] == 160 and result["q4"] == q4:
            return
    run(f"{label}-{split}.log", SCRIPT + "evaluate.py", "--model", model,
        "--tasks", relative + f"tasks/{task_file}.jsonl", "--output", relative + f"results/{label}-{split}.json",
        "--max-new", "160", *flags)


def main():
    relative = ".build/mk61-agent-20261106/"
    original = relative + "flourish-original"
    # These are immutable, unmodified-model baselines, before any gradient steps.
    status("baseline")
    for split in ["basic", "validation", "test"]:
        assess(original, "original-fp32", split)
        assess(original, "original-q4", split, q4=True)
    status("domain_continuation", steps=600, training_test_opened=False)
    if not (BASE / "domain/training.json").exists():
        run("domain.log", SCRIPT + "train.py", "--phase", "domain", "--initial", original,
            "--data", relative + "training/domain-documents.jsonl", "--tasks", relative + "tasks/validation-extended-v2.jsonl",
            "--output", relative + "domain", "--steps", "600", "--batch", "24", "--context", "512", "--lr", "3e-5")
    for arm in ["plan", "no-plan"]:
        status("tool_sft", arm=arm, steps=3000, qat_start=2001)
        if (BASE / arm / "training.json").exists():
            continue
        run(f"{arm}.log", SCRIPT + "train.py", "--phase", "sft", "--initial", relative + "domain/last",
            "--data", relative + "training/sft-combined-v2.jsonl", "--tasks", relative + "tasks/validation-extended-v2.jsonl",
            "--output", relative + arm, "--steps", "3000", "--batch", "32", "--micro-batch", "16", "--context", "512", "--lr", "0.00015",
            "--qat-start", "2001", *(["--no-plan"] if arm == "no-plan" else []))
    status("final_evaluation", checkpoint_selection="fixed development subset only")
    for arm in ["plan", "no-plan"]:
        model = relative + arm + "/best"
        for split in ["basic", "validation", "test"]:
            assess(model, arm + "-fp32", split, no_plan=arm == "no-plan")
            assess(model, arm + "-q4", split, q4=True, no_plan=arm == "no-plan")
    summary = {}
    for path in sorted((BASE / "results").glob("*.json")):
        row = json.loads(path.read_text())
        summary[path.stem] = {key: row[key] for key in ["total", "passed", "pass_rate", "valid_tool_tasks", "by_kind", "q4"]}
    (BASE / "comparison.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    status("first_comparison_complete", comparison="comparison.json", native_device_inference_measured=False)


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        status("failed", error=f"{type(error).__name__}: {error}")
        raise
