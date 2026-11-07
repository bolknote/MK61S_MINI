#!/usr/bin/env python3
"""Audit a frozen packed candidate on held-out prompts and actual conversations."""
import argparse
import json
from pathlib import Path
from common import core, load_model, quantize
from evaluate import assess, TEST_SCENARIOS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--packed", required=True)
    parser.add_argument("--selection", required=True)
    parser.add_argument("--suite", default="suite/test.jsonl")
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--seed", type=int, default=84119)
    parser.add_argument("--scenarios", help="Use an independently reserved JSON conversation suite")
    parser.add_argument("--fp16-kv", action="store_true", help="Use the planned actual FP16 KV storage")
    parser.add_argument("--precision-development", help="Prior complete precision-development validation report")
    args = parser.parse_args()
    selection = json.loads(Path(args.selection).read_text())
    assert selection["selected"]["goal_met"], "Finish development improvements before opening the final audit"
    assert selection['selected'].get('two_consecutive_goal_checks', True), 'Confirm development gates at consecutive checks'
    if args.fp16_kv:
        assert args.precision_development, 'Validate every observed gate at FP16 KV before opening the fresh audit'
    if args.precision_development:
        precision = json.loads(Path(args.precision_development).read_text())
        assert args.fp16_kv and precision['goal_met'] and precision['fp16_kv']
        assert precision['raw_checkpoint_sha256'] == core.digest(Path(args.model) / 'model.safetensors')
        assert precision['packed_sha256'] == core.digest(args.packed)
    output = Path(args.output)
    assert not output.exists(), "Keep earlier held-out results immutable"
    output.mkdir(parents=True)
    model, tokenizer, device = load_model(args)
    model.eval().requires_grad_(False)
    quantize.roundtrip(model)
    import torch
    expected = {name: p.detach().clone() for name, p in model.named_parameters()}
    packed = quantize.restore(model, args.packed)
    error = max(float((expected[name] - p).abs().max()) for name, p in model.named_parameters())
    assert error == 0
    del expected
    scenarios = json.loads(Path(args.scenarios).read_text()) if args.scenarios else TEST_SCENARIOS
    result = assess(model, tokenizer, device, core.read_rows(args.suite), None, output / "grade-cache", "final", scenarios,
                    fp16_kv=args.fp16_kv)
    report = {"selection": selection, "raw_checkpoint_sha256": core.digest(Path(args.model) / "model.safetensors"),
              "packed_sha256": core.digest(args.packed), "packed_reload_max_abs_error": error,
              "parameters": sum(p.numel() for p in model.parameters()), "test_sha256": core.digest(args.suite),
              "scenarios_sha256": core.digest(args.scenarios) if args.scenarios else None,
              "packed_bytes": Path(args.packed).stat().st_size, "native_runtime_measured": False, "result": result}
    if args.precision_development: report['precision_development_sha256'] = core.digest(args.precision_development)
    core.save(output / "audit.json", report)
    print(json.dumps({"acceptable": result["direct"]["pass_rate"], "context": result["context_pass_rate"],
                      "multi_turn": result["multi_turn"]["pass_rate"], "malformed": result["malformed"], "goal_met": result["goal_met"]}), flush=True)


if __name__ == "__main__":
    main()
