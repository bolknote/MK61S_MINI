#!/usr/bin/env python3
"""Run the second capacity/data experiment and keep the final test unopened."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import time
from run_remote import container, command, status, ROOT, ORIGIN


def worker(mode):
    model = "/previous" if mode == "small" else "wide-init"
    gpu = 0 if mode == "small" else 1
    command(container(gpu, "train.py", "--mode", "sft", "--model", model, "--output", mode,
                      "--steps", "12000", "--lr", "6e-5", "--batch-size", "32", "--eval-every", "2000",
                      "--replay-fraction", "0.05", "--kl", "0.005", "--qat-start", "6001"), mode + ".log", 10800)


def main():
    status("generating_larger_corpus", planned_requests=2912, planned_examples=34944)
    command(["python3", "-u", "generate_large.py"], "generation.log", 7200)
    command(["python3", "prepare.py", "--gold", "large-gold.jsonl", "--replay", ORIGIN["previous_data"],
             "--supervise-context"], "prepare.log", 120)
    status("training", modes=["small", "wide"], steps=12000, qat_start=6001)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(worker, ["small", "wide"]))
    selection = []
    for mode in ["small", "wide"]:
        report = json.loads((ROOT / mode / "training.json").read_text())
        chosen = next((row for row in report["history"] if row["step"] == report["best_step"]), report["baseline"])
        selection.append({"mode": mode, "step": report["best_step"], "goal_met": chosen["goal_met"],
                          "score": chosen["selection_score"], "acceptable": chosen["direct"]["pass_rate"],
                          "context": chosen["context_pass_rate"], "multi_turn": chosen["multi_turn"]["pass_rate"]})
        command(container(0, "quantize.py", "--model", f"{mode}/best", "--output", f"{mode}/model.ttq4", "--report", f"{mode}/packed.json"), mode + "-packed.log")
    selection.sort(key=lambda row: (row["goal_met"], row["score"]), reverse=True)
    (ROOT / "selection.json").write_text(json.dumps({"selected": selection[0], "candidates": selection, "test_opened": False}, indent=2))
    status("development_target_met" if selection[0]["goal_met"] else "needs_next_iteration", selected=selection[0])


if __name__ == "__main__":
    try:main()
    except BaseException as error:
        status("failed", error=f"{type(error).__name__}: {error}")
        raise
