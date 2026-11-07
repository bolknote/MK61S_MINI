#!/usr/bin/env python3
"""Train the isolated wider-hidden, smaller-vocabulary TinyTalk derivative."""
import json
import shutil
from run_remote import container, command, status, ROOT


def main():
    status("training", model="balanced", steps=20000, batch_size=64, qat_start=1, runtime_context=128)
    command(container(1, "train.py", "--mode", "sft", "--model", "balanced-init", "--output", "balanced",
                      "--steps", "20000", "--batch-size", "64", "--lr", "4e-5", "--eval-every", "2000",
                      "--qat-start", "1", "--embedding-lr-scale", "0.5", "--replay-fraction", "0.05", "--kl", "0.002"),
            "balanced.log", 14400)
    report = json.loads((ROOT / "balanced/training.json").read_text())
    chosen = next((row for row in report["history"] if row["step"] == report["best_step"]), report["baseline"])
    selected = {"mode": "balanced", "step": report["best_step"], "goal_met": chosen["goal_met"],
                "score": chosen["selection_score"], "acceptable": chosen["direct"]["pass_rate"],
                "context": chosen["context_pass_rate"], "multi_turn": chosen["multi_turn"]["pass_rate"]}
    (ROOT / "selection.json").write_text(json.dumps({"selected": selected, "test_opened": False}, indent=2))
    command(container(1, "quantize.py", "--model", "balanced/best", "--output", "balanced/model.ttq4", "--report", "balanced/packed.json"),
            "balanced-packed.log")
    shutil.copyfile(ROOT / "balanced-init/tokenizer.ttbpe", ROOT / "balanced/tokenizer.ttbpe")
    packed = json.loads((ROOT / "balanced/packed.json").read_text())
    table_bytes = (ROOT / "balanced/tokenizer.ttbpe").stat().st_size
    total = packed["file_bytes"] + table_bytes + 1048576 + 262144
    assert total <= 8388608
    (ROOT / "balanced/memory-budget.json").write_text(json.dumps({"packed_weights_bytes": packed["file_bytes"],
        "compact_tokenizer_bytes": table_bytes, "fp16_kv_context128_bytes": 1048576, "working_reserve_bytes": 262144,
        "total_design_bytes": total, "remaining_from_8mib": 8388608 - total, "native_runtime_measured": False}, indent=2))
    status("development_target_met" if selected["goal_met"] else "needs_next_iteration", selected=selected)


if __name__ == "__main__":
    try:main()
    except BaseException as error:
        status("failed", error=f"{type(error).__name__}: {error}")
        raise
