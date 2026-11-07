#!/usr/bin/env python3
"""Verify packed checkpoints and reproduce selected B200 development replies on CPU."""
import argparse
import json
from pathlib import Path
from common import core, decode, load_model, quantize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True)
    parser.add_argument("--arms", nargs="+", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--seed", type=int, default=7731)
    parser.add_argument("--model", default="unused")
    args = parser.parse_args()
    root = Path(args.results)
    cases = core.read_rows(root / "suite/dev.jsonl")
    report = {"device": args.device, "models": {}, "uses_reserved_test": False}
    for arm in args.arms:
        folder = root / arm
        metadata = json.loads((folder / "packed.json").read_text())
        training = json.loads((folder / "training.json").read_text())
        assert core.digest(folder / "model.ttq4") == metadata["file_sha256"]
        assert core.digest(folder / "best/model.safetensors") == training["best_sha256"]
        assert training["source_unchanged"]
        chosen = next((row for row in training["history"] if row["step"] == training["best_step"]), training["baseline"])
        model, tokenizer, device = load_model(args, folder / "best")
        model.eval().requires_grad_(False)
        quantize.roundtrip(model)
        expected = {name: p.detach().clone() for name, p in model.named_parameters()}
        quantize.restore(model, folder / "model.ttq4")
        error = max(float((expected[name] - p).abs().max()) for name, p in model.named_parameters())
        assert error == 0
        replies = decode(model, tokenizer, cases[:16], device)
        checks = [{"id": new["id"], "matches": new["reply"] == old["reply"], "cpu": new["reply"], "b200": old["reply"]}
                  for new, old in zip(replies, chosen["replies"][:16])]
        report["models"][arm] = {"parameters": sum(p.numel() for p in model.parameters()), "best_step": training["best_step"],
                                  "packed_bytes": (folder / "model.ttq4").stat().st_size, "packed_reload_max_abs_error": error,
                                  "matching_replies": sum(row["matches"] for row in checks), "comparisons": checks}
        print(arm, report["models"][arm]["matching_replies"], "/", len(checks), flush=True)
        del model, expected
    core.save(args.output, report)


if __name__ == "__main__":
    main()
