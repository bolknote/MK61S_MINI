#!/usr/bin/env python3
"""Prepare an optional wider TinyTalk FFN with initially zero output contribution.

The original model's function is preserved before learning. This is an isolated
capacity experiment, not a replacement for the current selected model.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from common import core, quantize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--intermediate", type=int, default=1536)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--seed", type=int, default=12061)
    args = parser.parse_args()
    import torch
    from transformers import AutoModelForCausalLM
    output = Path(args.output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Use a fresh output directory")
    model, tokenizer, device = core.load(args)
    model.eval().requires_grad_(False)
    old = model.transformer.h[0].mlp.c_fc.out_features
    assert args.intermediate > old
    config = copy.deepcopy(model.config);config.intermediate_size = args.intermediate
    config.tinytalk_widened_from = {"intermediate_size": old, "checkpoint_sha256": core.digest(Path(args.model) / "model.safetensors")}
    wider = AutoModelForCausalLM.from_config(config, attn_implementation="eager").to(device).eval().requires_grad_(False)
    source = model.state_dict()
    with torch.no_grad():
        for name, target in wider.state_dict().items():
            original = source[name]
            if target.shape == original.shape:
                target.copy_(original)
            elif name.endswith("mlp.c_fc.weight"):
                repeats = (target.shape[0] + old - 1) // old
                target.copy_(original.repeat(repeats, 1)[:target.shape[0]])
                target[old:] += torch.randn_like(target[old:]) * 0.01
            elif name.endswith("mlp.c_fc.bias"):
                target.copy_(original.repeat((target.shape[0] + old - 1) // old)[:target.shape[0]])
            elif name.endswith("mlp.c_proj.weight"):
                target.zero_();target[:, :old].copy_(original)
            else:
                raise ValueError(f"Unexpected changed tensor: {name}")
    prompts = ["Hello!", "Could you ask me a question?", "My name is Alice.", "I feel a little tired.", "What could I draw?"]
    inputs = [tokenizer(core.render([{"role": "user", "content": text}]), return_tensors="pt", add_special_tokens=False).to(device) for text in prompts]
    with torch.inference_mode():
        full_error = max(float((model(**batch, use_cache=False).logits - wider(**batch, use_cache=False).logits).abs().max()) for batch in inputs)
    assert full_error < 5e-5
    output.mkdir(parents=True, exist_ok=True)
    wider.save_pretrained(output, safe_serialization=True);tokenizer.save_pretrained(output)
    quantize.copy_notices(args.model, output)
    packed = quantize.export(wider, output / "model.ttq4", {"derived_from": core.MODEL,
                            "source_sha256": config.tinytalk_widened_from["checkpoint_sha256"],
                            "change": f"MLP width {old} to {args.intermediate}; extra output columns initialized to zero"})
    quantize.roundtrip(model);quantize.roundtrip(wider)
    with torch.inference_mode():
        q4_error = max(float((model(**batch, use_cache=False).logits - wider(**batch, use_cache=False).logits).abs().max()) for batch in inputs)
    assert q4_error < 5e-5
    budget = packed["file_bytes"] + 921923 + 1048576 + 262144
    assert budget <= 8388608
    report = {"parameters": sum(p.numel() for p in wider.parameters()), "old_intermediate": old,
              "new_intermediate": args.intermediate, "fp32_function_max_abs_error": full_error,
              "q4_function_max_abs_error": q4_error, "packed": packed,
              "psram_design_bytes_context256": budget, "psram_remaining_design_bytes": 8388608 - budget,
              "native_runtime_measured": False, "trained": False}
    core.save(output / "widening.json", report)
    print(json.dumps({k: report[k] for k in ["parameters", "new_intermediate", "fp32_function_max_abs_error", "q4_function_max_abs_error", "psram_design_bytes_context256", "psram_remaining_design_bytes"]}), flush=True)


if __name__ == "__main__":
    main()
