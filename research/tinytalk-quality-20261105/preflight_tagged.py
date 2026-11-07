#!/usr/bin/env python3
"""Check hidden-token handling, gradients and the actual packed memory budget."""
import argparse
from pathlib import Path
from common import core, load_model, quantize, qat_modules, actual_q4, logps
from rebalance import compact_tokenizer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--seed", type=int, default=62414)
    args = parser.parse_args()
    import torch
    model, tokenizer, device = load_model(args)
    tags = model.config.tinytalk_intent_token_ids
    assert len(tags) == 20
    for kind, token in tags.items():
        assert tokenizer.convert_tokens_to_ids(f"<|tt_intent:{kind}|>") == token
        assert tokenizer.decode([token] + tokenizer.encode(" Hello!", add_special_tokens=False) + [tokenizer.eos_token_id], skip_special_tokens=True).strip() == "Hello!"
    output = Path(args.output);output.mkdir(parents=True, exist_ok=True)
    packed = quantize.export(model, output / "model.ttq4", {"source_sha256": core.digest(Path(args.model) / "model.safetensors"), "change": "learned hidden intent prefixes"})
    table = compact_tokenizer(tokenizer, output / "tokenizer.ttbpe")
    assert table["vocab_size"] == model.config.vocab_size and len(table["special_token_ids"]) == 21
    with actual_q4(model, None):
        expected = {name: p.detach().clone() for name, p in model.named_parameters()}
        quantize.restore(model, output / "model.ttq4")
        reload_error = max(float((expected[name] - p.detach()).abs().max()) for name, p in model.named_parameters())
        assert reload_error == 0
    qstate = qat_modules(model)
    rows, skipped = core.encode_rows(tokenizer, core.read_rows(Path(args.data) / "train.jsonl")[:8], 128)
    assert len(rows) >= 4
    ids = set(tags.values())
    assert all(sum(token in ids for token, label in zip(tokens, labels) if label != -100) == 1 for tokens, labels, _ in rows)
    _, loss, _, _ = logps(model, rows, tokenizer, device, 4.0);loss.backward()
    embedding = model.transformer.wte.parametrizations.weight.original
    norm = float(embedding.grad[list(tags.values())].abs().sum())
    assert norm > 0 and torch.isfinite(embedding.grad).all()
    parameter_ids = {id(p) for p in model.parameters()}
    with actual_q4(model, qstate):
        with torch.no_grad():_, actual, _, _ = logps(model, rows, tokenizer, device, 4.0)
    assert abs(float(loss.detach()) - float(actual)) < 1e-5
    assert parameter_ids == {id(p) for p in model.parameters()}
    total = packed["file_bytes"] + table["file_bytes"] + 1048576 + 262144
    assert total < 8388608
    result = {"device": device, "parameters": sum(p.numel() for p in model.parameters()), "vocab": len(tokenizer),
              "intent_tags": len(tags), "all_tags_hidden_by_decoder": True, "train_rows": len(rows), "skipped": skipped,
              "weighted_qat_loss": float(loss.detach()), "actual_q4_loss": float(actual), "intent_embedding_gradient_norm": norm,
              "packed_reload_max_abs_error": reload_error, "packed_bytes": packed["file_bytes"], "tokenizer_table_bytes": table["file_bytes"],
              "total_psram_design_bytes_context128": total, "remaining_from_8mib": 8388608 - total, "native_runtime_measured": False}
    core.save(output / "preflight.json", result);print(result, flush=True)


if __name__ == "__main__":
    main()
