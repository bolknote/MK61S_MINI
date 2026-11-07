#!/usr/bin/env python3
"""Run the fixed conversation experiment in two isolated B200 containers."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
IMAGE = "sha256:a3bc7f09c1e2e72e068021feb75118c92e98c538706caa0c5d1acc0bb9252623"


def status(phase, **kwargs):
    payload = {"phase": phase, "unix": time.time(), **kwargs}
    (ROOT / "status.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload), flush=True)


def container(gpu, *args):
    return ["sudo", "-n", "docker", "run", "--rm", "--gpus", f"device={gpu}",
            "--network=host", "--shm-size=512m", "--cpus=4", "--memory=10g",
            "--user", f"{os.getuid()}:{os.getgid()}", "--env", "HF_HUB_OFFLINE=1",
            "--env", "TRANSFORMERS_OFFLINE=1", "--env", "HF_HOME=/tmp/hf",
            "--env", "TOKENIZERS_PARALLELISM=false", "--volume", f"{ROOT}:/work",
            "--volume", "/home/sad/tinytalk-train-20261105-k0i328cq/model:/work/model:ro",
            "--workdir", "/work", "--entrypoint", "python3", IMAGE, "-u", *args]


def command(args, log):
    with (ROOT / log).open("w") as stream:
        result = subprocess.run(args, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=3600)
    if result.returncode:
        raise RuntimeError(f"Command failed: {log}")


def main():
    gpu = subprocess.check_output(["nvidia-smi", "--query-gpu=index,name,memory.free,memory.used", "--format=csv,noheader"], text=True)
    (ROOT / "gpu-before.txt").write_text(gpu)
    for line in gpu.splitlines():
        parts = [value.strip() for value in line.split(",")]
        assert "B200" in parts[1] and int(parts[2].split()[0]) > 6144
    status("prepare")
    command([sys.executable, "prepare_data.py", "merge", "--output", "data", "--teacher", "teacher-dialogues.jsonl"], "prepare.log")
    status("training", arms=["qat", "staged"], steps_each=2000)
    processes = []
    for index, arm in enumerate(["qat", "staged"]):
        stream = (ROOT / f"{arm}.log").open("w")
        process = subprocess.Popen(container(index, "train_chat.py", "--arm", arm, "--output", arm),
                                   cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        processes.append((arm, process, stream))
    deadline = time.monotonic() + 3600
    while any(process.poll() is None for _, process, _ in processes):
        if time.monotonic() > deadline:
            for _, process, _ in processes:
                process.terminate()
            raise TimeoutError("Training exceeded the one-hour pilot limit")
        time.sleep(3)
    chosen = []
    for arm, process, stream in processes:
        stream.close()
        if process.returncode:
            raise RuntimeError(f"{arm} failed; see {arm}.log")
        training = json.loads((ROOT / arm / "training.json").read_text())
        selected = next((row for row in training["history"] if row["step"] == training["best_step"]), None)
        chosen.append({"arm": arm, "step": training["best_step"], "dev_score": selected["score"] if selected else [0, -sum(training["baseline_validation_q4_nll"].values())]})
    # Choose the strategy on development performance before opening the test prompts.
    chosen.sort(key=lambda row: tuple(row["dev_score"]), reverse=True)
    (ROOT / "preselected.json").write_text(json.dumps({"selected": chosen[0], "candidates": chosen,
                                                       "test_used_for_selection": False}, indent=2) + "\n")
    status("packing", selected=chosen[0])
    for gpu, arm in enumerate(["qat", "staged"]):
        command(container(gpu, "quantize.py", "--model", f"{arm}/best", "--output", f"{arm}/model.ttq4",
                          "--report", f"{arm}/packed.json"), f"{arm}-packed.log")
    status("reserved_test", selected=chosen[0])
    command(container(0, "evaluate_chat.py"), "evaluation.log")
    after = subprocess.check_output(["nvidia-smi", "--query-gpu=index,name,memory.free,memory.used", "--format=csv,noheader"], text=True)
    (ROOT / "gpu-after.txt").write_text(after)
    status("complete", selected=chosen[0])


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        status("failed", error=f"{type(error).__name__}: {error}")
        raise
