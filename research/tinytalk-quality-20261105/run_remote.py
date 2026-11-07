#!/usr/bin/env python3
"""Continue training and report whether another iteration is needed; do not declare a pilot good."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
ORIGIN = json.loads((ROOT / "origin.json").read_text())
IMAGE = ORIGIN["image"]


def status(phase, **kwargs):
    value = {"phase": phase, "unix": time.time(), **kwargs}
    (ROOT / "status.json").write_text(json.dumps(value, indent=2))
    print(json.dumps(value), flush=True)


def container(gpu, *args):
    return ["sudo", "-n", "docker", "run", "--rm", "--gpus", f"device={gpu}",
            "--network=host", "--shm-size=512m", "--cpus=4", "--memory=10g", "--user", f"{os.getuid()}:{os.getgid()}",
            "--env", "HF_HUB_OFFLINE=1", "--env", "TRANSFORMERS_OFFLINE=1", "--env", "HF_HOME=/tmp/hf",
            "--env", "TOKENIZERS_PARALLELISM=false", "--volume", f"{ROOT}:/work",
            "--volume", f"{ORIGIN['previous_model']}:/previous:ro", "--volume", f"{ORIGIN['original_model']}:/original:ro",
            "--volume", f"{ORIGIN['previous_data']}:/replay:ro", "--workdir", "/work", "--entrypoint", "python3", IMAGE, "-u", *args]


def command(args, log, timeout=5400):
    with (ROOT / log).open("w") as stream:
        result = subprocess.run(args, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"Command failed: {log}")


def worker(mode):
    if mode == "dpo":
        command(container(1, "make_pairs.py"), "pairs.log")
        command(container(1, "train.py", "--mode", "dpo", "--output", "dpo", "--steps", "6000", "--lr", "1e-5"), "dpo.log")
    else:
        command(container(0, "train.py", "--mode", "sft", "--output", "sft", "--steps", "8000", "--lr", "3e-5"), "sft.log")


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        worker(sys.argv[2]);return
    # The generator is independent so failures can be inspected and corrected without discarding work.
    status("preparing")
    command([sys.executable, "prepare.py", "--replay", ORIGIN["previous_data"]], "prepare.log", 120)
    from grade import calibrate
    (ROOT / "grade-calibration.json").write_text(json.dumps(calibrate(ROOT / "grade-calibration-cache"), indent=2))
    status("training", modes=["sft", "dpo"], sft_steps=8000, dpo_steps=6000)
    processes = []
    for mode in ["sft", "dpo"]:
        stream = (ROOT / f"{mode}-worker.log").open("w")
        process = subprocess.Popen([sys.executable, "-u", __file__, "--worker", mode], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        processes.append((mode, process, stream))
    deadline = time.monotonic() + 7200
    while any(process.poll() is None for _, process, _ in processes):
        if time.monotonic() > deadline:
            raise TimeoutError("Quality iteration exceeded two hours")
        time.sleep(5)
    candidates = []
    for mode, process, stream in processes:
        stream.close()
        if process.returncode:
            raise RuntimeError(f"{mode} worker failed; see logs")
        report = json.loads((ROOT / mode / "training.json").read_text())
        selected = next((row for row in report["history"] if row["step"] == report["best_step"]), report["baseline"])
        candidates.append({"mode": mode, "step": report["best_step"], "goal_met": selected["goal_met"],
                           "score": selected["selection_score"], "acceptable": selected["direct"]["pass_rate"],
                           "context": selected["context_pass_rate"], "multi_turn": selected["multi_turn"]["pass_rate"]})
    candidates.sort(key=lambda row: (row["goal_met"], row["score"]), reverse=True)
    (ROOT / "selection.json").write_text(json.dumps({"selected": candidates[0], "candidates": candidates,
                                                    "test_opened": False}, indent=2))
    for gpu, mode in enumerate(["sft", "dpo"]):
        command(container(gpu, "quantize.py", "--model", f"{mode}/best", "--output", f"{mode}/model.ttq4",
                          "--report", f"{mode}/packed.json"), f"{mode}-packed.log")
    status("development_target_met" if candidates[0]["goal_met"] else "needs_next_iteration", selected=candidates[0])


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        # Worker failures must not race with the controller's status.
        if "--worker" not in sys.argv:
            status("failed", error=f"{type(error).__name__}: {error}")
        raise
