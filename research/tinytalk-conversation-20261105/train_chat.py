#!/usr/bin/env python3
"""Conversation-focused TinyTalk training; checkpoint selection uses actual Q4 replies."""
import argparse
from contextlib import contextmanager
from collections import Counter
import hashlib
import inspect
import json
import math
from pathlib import Path
import random
import sys
import time

try:
    import experiment as core
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tinytalk-train-20261105"))
    import experiment as core
import quantize
from judge import compare, calibrate


@contextmanager
def actual_q4(model, qat_state):
    import torch
    from torch.nn.utils import parametrize
    identities = {id(p) for p in model.parameters()}
    if qat_state:
        for module in qat_state[0]:
            parametrize.remove_parametrizations(module, "weight", leave_parametrized=False)
    originals = {name: p.detach().clone() for name, p in model.named_parameters()}
    quantize.roundtrip(model)
    model.eval()
    try:
        yield
    finally:
        with torch.no_grad():
            for name, p in model.named_parameters():
                p.copy_(originals[name])
        if qat_state:
            for module in qat_state[0]:
                parametrize.register_parametrization(module, "weight", qat_state[1]())
        assert {id(p) for p in model.parameters()} == identities


def logits_targets(model, rows, tokenizer, device):
    ids, labels, mask = core.batch(rows, tokenizer.eos_token_id, device)
    hidden = model.transformer(input_ids=ids, attention_mask=mask, use_cache=False).last_hidden_state
    use = labels[:, 1:] != -100
    return model.lm_head(hidden[:, :-1][use]), labels[:, 1:][use]


def decode(model, tokenizer, cases, device, temperature=0, seed=7731):
    import torch
    result = []
    torch.manual_seed(seed)
    tokenizer.padding_side = "left"
    with torch.inference_mode():
        for start in range(0, len(cases), 8):
            group = cases[start:start + 8]
            encoded = tokenizer([core.render(row["messages"]) for row in group], padding=True,
                                add_special_tokens=False, return_tensors="pt").to(device)
            assert encoded.input_ids.shape[1] + 40 <= 256
            options = {"max_new_tokens": 40, "do_sample": temperature > 0, "use_cache": True,
                       "pad_token_id": tokenizer.eos_token_id, "eos_token_id": tokenizer.eos_token_id}
            if temperature > 0:
                options.update(temperature=temperature, top_p=0.9, top_k=40)
            if "logits_to_keep" in inspect.signature(model.forward).parameters:
                options["logits_to_keep"] = 1
            output = model.generate(**encoded, **options)[:, encoded.input_ids.shape[1]:]
            for case, tokens in zip(group, output.tolist()):
                ended = tokenizer.eos_token_id in tokens
                if ended:
                    tokens = tokens[:tokens.index(tokenizer.eos_token_id) + 1]
                reply = tokenizer.decode(tokens, skip_special_tokens=True).strip()
                words = reply.lower().split()
                triples = [tuple(words[i:i+3]) for i in range(len(words) - 2)]
                bad = not ended or not reply or len(triples) != len(set(triples))
                result.append({"id": case["id"], "reply": reply, "ended_with_eos": ended, "bad": bad,
                               "tokens": len(tokens)})
    tokenizer.padding_side = "right"
    return result


def nll(model, rows, tokenizer, device):
    import torch
    total, count = 0, 0
    with torch.inference_mode():
        for start in range(0, len(rows), 8):
            loss, tokens = core.completion_loss(model, rows[start:start + 8], tokenizer.eos_token_id, device)
            total += float(loss); count += tokens
    return total / count


def run(args):
    import torch
    from torch.nn import functional as F
    output = Path(args.output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Use a fresh output directory")
    output.mkdir(parents=True, exist_ok=True)
    assert core.digest(Path(args.model) / "model.safetensors") == core.ORIGINAL_SHA
    model, tokenizer, device = core.load(args)
    reference, _, _ = core.load(args)
    reference.eval().requires_grad_(False)
    training, skipped = core.encode_rows(tokenizer, core.read_rows(Path(args.data) / "train.jsonl"), 256)
    validation, val_skipped = core.encode_rows(tokenizer, core.read_rows(Path(args.data) / "validation.jsonl"), 256)
    # Fixed small natural-language validation subsets, separate from free conversation prompts.
    validation = sorted(validation, key=lambda row: hashlib.sha256(str(row[0]).encode()).hexdigest())
    val_groups = {kind: [row for row in validation if row[2] == kind][:128] for kind in ["soda", "teacher"]}
    assert all(val_groups.values())
    groups = {kind: [row for row in training if row[2] == kind] for kind in ["soda", "teacher", "identity"]}
    assert all(groups.values())
    cases = core.read_rows(Path(args.suite) / "dev.jsonl")
    # Keep the reserved test file closed during training and selection.
    calibration = calibrate(output / "judge-cache")
    with actual_q4(reference, None):
        baseline = {mode: decode(reference, tokenizer, cases, device, temp) for mode, temp in [("greedy", 0), ("sampled", 0.7)]}
        baseline_nll = {kind: nll(reference, rows, tokenizer, device) for kind, rows in val_groups.items()}
    qat_state = quantize.qat_modules(model) if args.arm == "qat" else None
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    rng = random.Random(args.seed)
    report = {"model": core.MODEL, "revision": core.REVISION, "parameters": core.PARAMETERS,
              "settings": vars(args), "calibration": calibration, "baseline_dev_q4": baseline,
              "baseline_validation_q4_nll": baseline_nll, "training_rows": len(training), "skipped": skipped,
              "validation_skipped": val_skipped, "data": json.loads((Path(args.data) / "manifest.json").read_text()),
              "suite": json.loads((Path(args.suite) / "suite-manifest.json").read_text()),
              "test_used_for_selection": False, "history": [], "best_step": 0,
              "selection": "Blind Qwen preference on authored development conversations, after actual Q4; language/degeneration guards; NLL tie-break"}
    torch.cuda.reset_peak_memory_stats() if device == "cuda" else None
    best = (0.0, -sum(baseline_nll.values()))

    def checkpoint(path):
        if qat_state:
            quantize.save_qat_checkpoint(model, path, qat_state)
        else:
            model.save_pretrained(path, safe_serialization=True)
        tokenizer.save_pretrained(path)
        quantize.copy_notices(args.model, path)

    checkpoint(output / "best")
    started = time.monotonic()
    for step in range(1, args.steps + 1):
        if args.arm == "staged" and step == args.qat_start:
            ids = {id(p) for p in model.parameters()}
            qat_state = quantize.qat_modules(model)
            assert {id(p) for p in model.parameters()} == ids
        model.train(); optimizer.zero_grad(set_to_none=True)
        rows = [rng.choice(groups[rng.choices(["teacher", "soda", "identity"], weights=[0.65, 0.33, 0.02])[0]]) for _ in range(args.batch_size)]
        amp = torch.autocast("cuda", dtype=torch.bfloat16) if device == "cuda" else core.nullcontext()
        with amp:
            logits, targets = logits_targets(model, rows, tokenizer, device)
            ce = F.cross_entropy(logits.float(), targets)
            with torch.no_grad():
                ref_logits, _ = logits_targets(reference, rows, tokenizer, device)
            kl = F.kl_div(F.log_softmax(logits.float(), dim=-1), F.softmax(ref_logits.float(), dim=-1), reduction="batchmean")
            loss = ce + args.kl * kl
        if not torch.isfinite(loss):
            raise ValueError("Non-finite loss")
        loss.backward()
        norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        if not torch.isfinite(norm):
            raise ValueError("Non-finite gradient norm")
        if args.arm == "staged" and step >= args.qat_start:
            phase_step, length, maximum = step - args.qat_start + 1, args.steps - args.qat_start + 1, args.lr / 4
        else:
            phase_step, length, maximum = step, args.qat_start - 1 if args.arm == "staged" else args.steps, args.lr
        rate = maximum * min(1, phase_step / 40) * (0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * phase_step / length)))
        for group in optimizer.param_groups:
            group["lr"] = rate
        optimizer.step()
        if step == 1 or step % 100 == 0:
            print(json.dumps({"step": step, "ce": float(ce.detach()), "kl": float(kl.detach()), "seconds": round(time.monotonic() - started, 1)}), flush=True)
        if step % args.eval_every == 0 or step == args.steps:
            with actual_q4(model, qat_state):
                losses = {kind: nll(model, rows, tokenizer, device) for kind, rows in val_groups.items()}
                replies = {mode: decode(model, tokenizer, cases, device, temp) for mode, temp in [("greedy", 0), ("sampled", 0.7)]}
            judgments = {mode: compare(cases, baseline[mode], replies[mode], output / "judge-cache", f"dev-{mode}") for mode in replies}
            preferences = [judgments[mode]["net_preference"] for mode in judgments]
            bad = sum(row["bad"] for mode in replies.values() for row in mode)
            old_bad = sum(row["bad"] for mode in baseline.values() for row in mode)
            distinct = len({row["reply"].lower() for mode in replies.values() for row in mode})
            old_distinct = len({row["reply"].lower() for mode in baseline.values() for row in mode})
            eligible = (losses["soda"] <= baseline_nll["soda"] + 0.25 and bad <= old_bad + 4 and
                        distinct >= old_distinct * 0.7 and all(j["counts"]["error"] <= 2 for j in judgments.values()))
            score = (sum(preferences) / len(preferences), -sum(losses.values()))
            item = {"step": step, "q4_nll": losses, "replies": replies, "judgments": judgments,
                    "bad": bad, "distinct_replies": distinct, "eligible": eligible, "score": score,
                    "seconds": time.monotonic() - started}
            report["history"].append(item)
            if eligible and score > best:
                best = score; report["best_step"] = step
                checkpoint(output / "best")
            core.save(output / "training.json", report)
            print(json.dumps({"dev_step": step, "preference": preferences, "eligible": eligible, "best_step": report["best_step"],
                              "q4_nll": losses, "bad": bad, "seconds": round(time.monotonic() - started, 1)}), flush=True)
    checkpoint(output / "last")
    report["seconds"] = time.monotonic() - started
    report["best_sha256"] = core.digest(output / "best/model.safetensors")
    report["original_unchanged"] = core.digest(Path(args.model) / "model.safetensors") == core.ORIGINAL_SHA
    if device == "cuda":
        report["gpu"] = {"name": torch.cuda.get_device_name(), "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                         "peak_reserved_bytes": torch.cuda.max_memory_reserved()}
    core.save(output / "training.json", report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=["qat", "staged"], required=True)
    parser.add_argument("--model", default="model")
    parser.add_argument("--data", default="data")
    parser.add_argument("--suite", default="suite")
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--seed", type=int, default=27631)
    parser.add_argument("--steps", type=int, default=2000)
    parser.add_argument("--qat-start", type=int, default=1401)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--kl", type=float, default=0.03)
    parser.add_argument("--eval-every", type=int, default=500)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
