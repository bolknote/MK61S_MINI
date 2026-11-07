#!/usr/bin/env python3
"""Separate raw-model errors from errors added by Q4 on development prompts."""
import argparse
from pathlib import Path
from common import core, decode, load_model, quantize
from grade import grade


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--suite", default="suite/dev.jsonl")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--seed", type=int, default=41011)
    args = parser.parse_args()
    assert Path(args.suite).name == "dev.jsonl", "Precision diagnosis is for development, not the reserved test"
    model, tokenizer, device = load_model(args)
    model.eval().requires_grad_(False)
    cases = core.read_rows(args.suite)
    output = Path(args.output);output.mkdir(parents=True, exist_ok=True)
    report = {"source_sha256": core.digest(Path(args.model) / "model.safetensors"), "test_opened": False}
    for mode in ["fp32", "q4"]:
        if mode == "q4":quantize.roundtrip(model)
        replies = decode(model, tokenizer, cases, device)
        grades = grade(cases, replies, output / "grade-cache")
        report[mode] = {"grades": grades, "replies": replies}
        print(mode, grades["pass_rate"], flush=True)
    core.save(output / "diagnosis.json", report)


if __name__ == "__main__":
    main()
