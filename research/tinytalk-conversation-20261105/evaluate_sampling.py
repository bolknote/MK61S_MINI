#!/usr/bin/env python3
"""Check two additional sampling seeds for the strategy chosen on development data.

No weights or selection decisions change after the reserved test. This checks
whether an observed conversational preference depends on one random sample.
"""
import argparse
import json
from pathlib import Path

from train_chat import core, decode, quantize
from judge import compare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="model")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--seed", type=int, default=27631)
    args = parser.parse_args()
    import torch
    selection = json.loads(Path("preselected.json").read_text())
    arm = selection["selected"]["arm"]
    cases = core.read_rows("suite/test.jsonl")
    report = {"preselected_arm": selection, "temperature": 0.7, "top_p": 0.9, "top_k": 40,
              "test_used_to_change_weights_or_selection": False, "models": {}}
    baseline = None
    for label, directory, packed in [("original", args.model, None), (arm, f"{arm}/best", f"{arm}/model.ttq4")]:
        model, tokenizer, device = core.load(args, directory)
        model.eval().requires_grad_(False)
        if packed:
            quantize.restore(model, packed)
        else:
            quantize.roundtrip(model)
        replies = {str(seed): decode(model, tokenizer, cases, device, 0.7, seed) for seed in [17331, 27731]}
        item = {"replies": replies, "checkpoint_sha256": core.digest(Path(directory) / "model.safetensors")}
        if baseline is None:
            baseline = replies
        else:
            item["judgments"] = {seed: compare(cases, baseline[seed], replies[seed], "sampling-judge-cache", f"sampling-{seed}") for seed in replies}
        report["models"][label] = item
        core.save("sampling-check.json", report)
        print(json.dumps({"model": label, "judgments": {seed: value["counts"] for seed, value in item.get("judgments", {}).items()}}), flush=True)
        del model
        torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
