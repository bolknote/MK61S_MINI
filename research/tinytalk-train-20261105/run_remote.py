#!/usr/bin/env python3
"""Bounded pilot on the user's two B200 cards, using a cached training image.

Run from the dedicated uploaded experiment directory. The two fixed training
arms share frozen data and settings; each selects on validation before testing.
"""
from pathlib import Path
import json
import os
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
IMAGE = "sha256:a3bc7f09c1e2e72e068021feb75118c92e98c538706caa0c5d1acc0bb9252623"


def state(phase, **kwargs):
    payload = {"phase": phase, "unix": time.time(), **kwargs}
    (ROOT / "status.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload), flush=True)


def command(args, log):
    with (ROOT / log).open("w") as stream:
        result = subprocess.run(args, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=1800)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}); see {log}")


def container(gpu, *args):
    return ["sudo", "-n", "docker", "run", "--rm", "--gpus", f"device={gpu}",
            "--network=none", "--shm-size=512m", "--cpus=4", "--memory=8g",
            "--user", f"{os.getuid()}:{os.getgid()}",
            "--env", "HF_HUB_OFFLINE=1", "--env", "TRANSFORMERS_OFFLINE=1",
            "--env", "HF_HOME=/tmp/hf", "--env", "TOKENIZERS_PARALLELISM=false",
            "--volume", f"{ROOT}:/work", "--workdir", "/work", "--entrypoint", "python3", IMAGE,
            "-u", *args]


def main():
    origin = subprocess.check_output(["nvidia-smi", "--query-gpu=index,name,memory.free,memory.used,utilization.gpu", "--format=csv,noheader"], text=True)
    (ROOT / "gpu-before.txt").write_text(origin)
    for line in origin.splitlines():
        fields = [part.strip() for part in line.split(",")]
        assert "B200" in fields[1] and int(fields[2].split()[0]) > 4096
    state("teacher_examples")
    command([sys.executable, "-u", "teacher.py", "--output", "teacher.jsonl"], "teacher.log")
    state("prepare_frozen_data")
    command([sys.executable, "experiment.py", "prepare", "--data", "data", "--teacher", "teacher.jsonl"], "prepare.log")
    state("training", arms=["sft", "qat"], steps_each=500, seed=5927)
    runs = []
    for gpu, arm in [(0, "sft"), (1, "qat")]:
        args = container(gpu, "experiment.py", "train", "--model", "model", "--data", "data",
                         "--output", arm, "--device", "cuda", "--steps", "500", "--batch-size", "16",
                         "--eval-every", "100")
        if arm == "qat":
            args.append("--qat")
        log = (ROOT / f"{arm}.log").open("w")
        process = subprocess.Popen(args, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        runs.append((arm, process, log))
    deadline = time.monotonic() + 1800
    while any(process.poll() is None for _, process, _ in runs):
        if time.monotonic() > deadline:
            for _, process, _ in runs:
                process.terminate()
            raise TimeoutError("Training pilot exceeded 30 minutes")
        time.sleep(2)
    for arm, process, log in runs:
        log.close()
        if process.returncode:
            raise RuntimeError(f"{arm} training failed ({process.returncode}); see {arm}.log")
    state("reserved_test", note="Both selected checkpoints are frozen before opening test data")
    for gpu, arm in [(0, "sft"), (1, "qat")]:
        command(container(gpu, "experiment.py", "evaluate", "--model", "model", "--data", "data",
                          "--candidate", f"{arm}/best", "--device", "cuda", "--report", f"{arm}/evaluation.json"),
                f"{arm}-evaluation.log")
        command(container(gpu, "quantize.py", "--model", f"{arm}/best", "--output", f"{arm}/model.ttq4",
                          "--report", f"{arm}/packed.json"), f"{arm}-packed.log")
    after = subprocess.check_output(["nvidia-smi", "--query-gpu=index,name,memory.free,memory.used,utilization.gpu", "--format=csv,noheader"], text=True)
    (ROOT / "gpu-after.txt").write_text(after)
    state("complete", results=["sft/training.json", "sft/evaluation.json", "qat/training.json", "qat/evaluation.json"])


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        state("failed", error=f"{type(error).__name__}: {error}")
        raise
