#!/usr/bin/env python3
"""Train frequency-preserving vocabulary plus a learned conversational-act prefix."""
import json
import shutil
from run_remote import container, command, status, ROOT


def main():
    status("preflight", model="tagged", runtime_context=128)
    command(container(0, "preflight_tagged.py", "--model", "tagged-init", "--data", "data", "--output", "gpu-preflight", "--device", "cuda"), "preflight.log")
    status("training", model="tagged", steps=20000, batch_size=64, qat_start=1, intent_weight=4, uniform_intents=True)
    command(container(0, "train.py", "--mode", "sft", "--model", "tagged-init", "--output", "tagged",
                      "--steps", "20000", "--batch-size", "64", "--lr", "4e-5", "--eval-every", "2000",
                      "--qat-start", "1", "--embedding-lr-scale", "0.5", "--replay-fraction", "0.05", "--kl", "0.002",
                      "--intent-weight", "4", "--uniform-groups"), "tagged.log", 14400)
    report = json.loads((ROOT / "tagged/training.json").read_text())
    chosen = next((row for row in report["history"] if row["step"] == report["best_step"]), report["baseline"])
    selected = {"mode": "tagged", "step": report["best_step"], "goal_met": chosen["goal_met"],
                "score": chosen["selection_score"], "acceptable": chosen["direct"]["pass_rate"],
                "context": chosen["context_pass_rate"], "multi_turn": chosen["multi_turn"]["pass_rate"]}
    (ROOT / "selection.json").write_text(json.dumps({"selected": selected, "test_opened": False}, indent=2))
    command(container(0, "quantize.py", "--model", "tagged/best", "--output", "tagged/model.ttq4", "--report", "tagged/packed.json"), "packed.log")
    shutil.copyfile(ROOT / "tagged-init/tokenizer.ttbpe", ROOT / "tagged/tokenizer.ttbpe")
    packed = json.loads((ROOT / "tagged/packed.json").read_text())
    total = packed["file_bytes"] + (ROOT / "tagged/tokenizer.ttbpe").stat().st_size + 1048576 + 262144
    assert total < 8388608
    (ROOT / "tagged/memory-budget.json").write_text(json.dumps({"packed_bytes": packed["file_bytes"],
        "compact_tokenizer_bytes": (ROOT / "tagged/tokenizer.ttbpe").stat().st_size, "fp16_kv_bytes_context128": 1048576,
        "working_reserve_bytes": 262144, "total_design_bytes": total, "remaining_from_8mib": 8388608 - total,
        "native_runtime_measured": False}, indent=2))
    status("development_target_met" if selected["goal_met"] else "needs_next_iteration", selected=selected)


if __name__ == "__main__":
    try:main()
    except BaseException as error:
        status("failed", error=f"{type(error).__name__}: {error}")
        raise
