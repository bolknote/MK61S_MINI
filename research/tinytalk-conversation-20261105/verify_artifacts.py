#!/usr/bin/env python3
"""Verify packed files and reproduce B200 greedy answers on the local CPU."""
import argparse
import json
from pathlib import Path

from train_chat import core, decode, quantize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=".build/tinytalk-chat-20261105/model")
    parser.add_argument("--results", default=".build/tinytalk-conversation-20261105/server-results")
    parser.add_argument("--report", default="research/tinytalk-conversation-20261105/verification.json")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--seed", type=int, default=27631)
    args = parser.parse_args()
    import torch
    root = Path(args.results)
    cases = core.read_rows(root / "suite/test.jsonl")
    evaluation = json.loads((root / "evaluation.json").read_text())
    selected = json.loads((root / "preselected.json").read_text())
    assert selected["test_used_for_selection"] is False
    report = {"original_sha256": core.digest(Path(args.model) / "model.safetensors"),
              "preselected": selected, "models": {}}
    assert report["original_sha256"] == core.ORIGINAL_SHA
    for arm in ["qat", "staged"]:
        packed = root / arm / "model.ttq4"
        metadata = json.loads((root / arm / "packed.json").read_text())
        assert core.digest(packed) == metadata["file_sha256"]
        training = json.loads((root / arm / "training.json").read_text())
        assert core.digest(root / arm / "best/model.safetensors") == training["best_sha256"]
        assert training["original_unchanged"]
        model, tokenizer, device = core.load(args, root / arm / "best")
        model.eval().requires_grad_(False)
        quantize.roundtrip(model)
        expected = {name: parameter.clone() for name, parameter in model.named_parameters()}
        quantize.restore(model, packed)
        error = max(float((expected[name] - parameter).abs().max()) for name, parameter in model.named_parameters())
        assert error == 0
        replies = decode(model, tokenizer, cases[:16], device)
        reference = evaluation["models"][arm]["replies"]["greedy"][:16]
        checks = [{"id": new["id"], "matches": new["reply"] == old["reply"],
                   "cpu": new["reply"], "b200": old["reply"]} for new, old in zip(replies, reference)]
        report["models"][arm] = {"packed_sha256": core.digest(packed), "packed_bytes": packed.stat().st_size,
                                  "parameters": sum(p.numel() for p in model.parameters()),
                                  "packed_reload_max_abs_error": error, "cpu_matches_b200": sum(c["matches"] for c in checks),
                                  "comparisons": checks}
        assert report["models"][arm]["parameters"] == core.PARAMETERS
        print(json.dumps({"arm": arm, "packed_bytes": packed.stat().st_size,
                          "cpu_matches_b200": report["models"][arm]["cpu_matches_b200"], "compared": len(checks)}), flush=True)
        del model
    arm = selected["selected"]["arm"]
    assert core.digest(root / "selected/model.ttq4") == core.digest(root / arm / "model.ttq4")
    core.save(args.report, report)


if __name__ == "__main__":
    main()
