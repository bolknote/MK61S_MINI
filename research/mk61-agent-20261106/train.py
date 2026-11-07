"""Small full-parameter continuation, verified tool SFT, and Q4-aware training."""
from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import math
from pathlib import Path
import random
import re
import time

import torch
import torch.nn.functional as F
from torch.nn.utils import parametrize
from transformers import AutoModelForCausalLM, AutoTokenizer

from evaluate import evaluate, read_tasks
from quantization import export_q4, fake_q4, load_q4
from prompt_variants import without_public_examples


class Q4Weight(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.enabled = False

    def forward(self, value):
        return fake_q4(value) if self.enabled else value


def attach_qat(model):
    for module in list(model.modules()):
        if isinstance(module, (torch.nn.Linear, torch.nn.Embedding)) and module.weight.shape[-1] % 32 == 0:
            parametrize.register_parametrization(module, "weight", Q4Weight())


def set_qat(model, enabled):
    for module in model.modules():
        if isinstance(module, Q4Weight): module.enabled = enabled


@torch.no_grad()
def plain_copy(model):
    # A fresh model avoids shared dynamic parametrization classes after deepcopy.
    # Copy the underlying FP32 Parameters, preserving a genuine FP32/Q4 comparison.
    with torch.random.fork_rng(devices=[]):
        replica = AutoModelForCausalLM.from_config(copy.deepcopy(model.config), trust_remote_code=False).cpu()
    seen = set()
    for name, value in model.named_parameters():
        plain_name = name.replace(".parametrizations.weight.original", ".weight")
        replica.get_parameter(plain_name).copy_(value.detach().cpu())
        seen.add(plain_name)
    assert seen == {name for name, _ in replica.named_parameters()}
    replica.tie_weights()
    return replica.eval()


def strip_plan(text):
    return re.sub(r"<plan>.*?</plan>", "", text, flags=re.S)


def checkpoint(model, tokenizer, directory):
    directory.mkdir(parents=True, exist_ok=True)
    replica = plain_copy(model)
    replica.save_pretrained(directory, safe_serialization=True)
    tokenizer.save_pretrained(directory)
    return replica


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--initial", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", choices=["domain", "sft"], required=True)
    parser.add_argument("--steps", type=int, default=3000)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--micro-batch", type=int)
    parser.add_argument("--context", type=int, default=512)
    parser.add_argument("--lr", type=float, default=0.00015)
    parser.add_argument("--qat-start", type=int, default=2001)
    parser.add_argument("--no-plan", action="store_true")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--eval-every", type=int, default=500)
    parser.add_argument("--development-all", action="store_true")
    parser.add_argument("--natural-selection", action="store_true")
    parser.add_argument("--eval-batch-size", type=int, default=1)
    parser.add_argument("--prompt-limit", type=int)
    parser.add_argument("--hide-public-inputs", action="store_true")
    parser.add_argument("--seed", type=int, default=61066)
    args = parser.parse_args()
    micro_batch = args.micro_batch or args.batch
    if args.batch % micro_batch:
        raise ValueError("Effective batch must be a multiple of micro-batch")
    accumulation = args.batch // micro_batch
    args.output.mkdir(parents=True, exist_ok=True)
    # A separately launched control arm and the main controller can converge
    # here. One writer trains; the other reuses its completed matching result.
    lock_stream = (args.output / "training.lock").open("a+")
    fcntl.flock(lock_stream, fcntl.LOCK_EX)
    existing = args.output / "training.json"
    if existing.exists():
        completed = json.loads(existing.read_text())
        if (completed["phase"] == args.phase and completed["steps"] == args.steps
                and completed.get("no_plan", False) == args.no_plan
                and completed["source_sha256"] == hashlib.sha256(args.data.read_bytes()).hexdigest()):
            print(json.dumps({"reused_completed_training": str(existing)}), flush=True)
            return
    torch.set_num_threads(2)
    torch.manual_seed(args.seed)
    rng = random.Random(args.seed)
    if args.device == "cuda":
        torch.cuda.set_per_process_memory_fraction(.025)
        torch.backends.cuda.matmul.allow_tf32 = True
    tokenizer = AutoTokenizer.from_pretrained(args.initial, local_files_only=True, trust_remote_code=False)
    model = AutoModelForCausalLM.from_pretrained(args.initial, local_files_only=True, trust_remote_code=False).to(args.device)
    if model.config.max_position_embeddings != 512:
        raise ValueError("This experiment preserves the native 512-token context")
    records = [json.loads(line) for line in args.data.read_text().splitlines()]
    data = []
    if args.phase == "domain":
        for row in records:
            tokens = tokenizer.encode(row["text"], add_special_tokens=False) + [tokenizer.eos_token_id]
            if len(tokens) >= 32:
                data.append(tokens)
    else:
        for row in records:
            prompt, answer = row["prompt"], row["answer"]
            if args.hide_public_inputs:prompt=without_public_examples(prompt)
            if args.no_plan:
                prompt, answer = strip_plan(prompt), strip_plan(answer)
            p = tokenizer.encode(prompt, add_special_tokens=False)
            a = tokenizer.encode(answer, add_special_tokens=False) + [tokenizer.eos_token_id]
            if len(a) >= args.context - 16:
                raise ValueError("Tool target is too long for the context")
            prompt_limit = min(args.context - len(a), args.prompt_limit or args.context)
            p = p[-prompt_limit:]
            data.append((p + a, [-100] * len(p) + a))
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=.01)
    if args.phase == "sft": attach_qat(model)
    tasks = read_tasks(args.tasks)
    # Fixed development subset; the final test is never opened by this trainer.
    task_subset = tasks if args.development_all else tasks[:16] + [task for task in tasks if task["kind"] in {"branch", "loop", "state"}][:8]
    history, losses = [], []
    best_score = -1
    best_key = None
    best_step = 0
    start = time.monotonic()
    parameter_count = sum(p.numel() for p in model.parameters())

    def batch():
        rows = []
        for _ in range(micro_batch):
            row = rng.choice(data)
            if args.phase == "domain":
                offset = rng.randrange(max(1, len(row) - args.context + 1))
                ids = row[offset:offset + args.context]
                rows.append((ids, ids))
            else:
                rows.append(row)
        length = max(len(row[0]) for row in rows)
        ids = torch.full((len(rows), length), tokenizer.pad_token_id or 0, dtype=torch.long)
        labels = torch.full_like(ids, -100)
        mask = torch.zeros_like(ids)
        for i, (x, y) in enumerate(rows):
            ids[i, :len(x)] = torch.tensor(x)
            labels[i, :len(y)] = torch.tensor(y)
            mask[i, :len(x)] = 1
        return ids.to(args.device), mask.to(args.device), labels.to(args.device)

    for step in range(1, args.steps + 1):
        if args.phase == "sft": set_qat(model, step >= args.qat_start)
        model.train()
        ratio = min(1., step / max(1, min(100, args.steps // 10)))
        cosine = .2 + .8 * (1 + math.cos(math.pi * step / args.steps)) / 2
        for group in optimizer.param_groups: group["lr"] = args.lr * ratio * cosine
        optimizer.zero_grad(set_to_none=True)
        step_loss = 0.
        for _ in range(accumulation):
            ids, mask, labels = batch()
            with torch.autocast(device_type="cuda", dtype=torch.bfloat16, enabled=args.device == "cuda"):
                output = model(input_ids=ids, attention_mask=mask, labels=labels, use_cache=False)
                loss = output.loss / accumulation
            if not bool(torch.isfinite(loss)):
                raise ValueError("Non-finite training loss")
            step_loss += float(loss.detach())
            loss.backward()
            del output, loss, ids, mask, labels
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.)
        optimizer.step()
        losses.append(step_loss)
        if step % 50 == 0 or step == 1:
            status = {"phase": args.phase, "step": step, "steps": args.steps,
                      "loss": sum(losses[-50:]) / len(losses[-50:]),
                      "qat": args.phase == "sft" and step >= args.qat_start,
                      "seconds": time.monotonic() - start}
            (args.output / "status.json").write_text(json.dumps(status, indent=2) + "\n")
            print(json.dumps(status), flush=True)
        if args.phase == "sft" and (step % args.eval_every == 0 or step == args.steps):
            replica = plain_copy(model)
            packed = export_q4(replica, args.output / "development.mkq4")
            load_q4(replica, args.output / "development.mkq4")
            if args.eval_batch_size > 1:
                from evaluate_batched import evaluate as batched_evaluate
                result = batched_evaluate(replica, tokenizer, task_subset, plan=not args.no_plan, max_new=160,
                                          batch_size=args.eval_batch_size,hide_public_inputs=args.hide_public_inputs)
            else:
                result = evaluate(replica, tokenizer, task_subset, plan=not args.no_plan, max_new=160)
            score = result["pass_rate"]
            if args.natural_selection:
                natural = result["by_kind"]["natural_language"]
                formal_total = result["total"] - natural["total"]
                formal_passed = result["passed"] - natural["passed"]
                selection_key = (formal_passed / max(1, formal_total) >= .95,
                                 natural["passed"] / natural["total"], formal_passed / max(1, formal_total), score)
            else:
                selection_key = (score,)
            history.append({"step": step, "q4_pass_rate": score, "passed": result["passed"],
                            "total": result["total"], "valid_tool_tasks": result["valid_tool_tasks"],
                            "loss": sum(losses[-50:]) / len(losses[-50:]), "packed": packed})
            (args.output / f"development-{step}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
            if best_key is None or selection_key > best_key:
                best_key = selection_key
                best_score, best_step = score, step
                checkpoint(model, tokenizer, args.output / "best")
            print(json.dumps({"development_step": step, "q4_passed": result["passed"], "total": result["total"],
                              "best_step": best_step}), flush=True)
            del replica
    checkpoint(model, tokenizer, args.output / "last")
    report = {"phase": args.phase, "steps": args.steps, "batch": args.batch, "micro_batch": micro_batch,
              "gradient_accumulation": accumulation, "context": args.context,
              "initial": str(args.initial), "parameters": parameter_count, "no_plan": args.no_plan,
              "qat_start": args.qat_start if args.phase == "sft" else None,
              "source_sha256": hashlib.sha256(args.data.read_bytes()).hexdigest(),
              "training_rows": len(data), "best_step": best_step, "best_q4_pass_rate": best_score,
              "final_loss": sum(losses[-50:]) / len(losses[-50:]), "history": history,
              "seconds": time.monotonic() - start, "fresh_test_opened": False}
    report["selection_key"] = best_key
    report["development_all"] = args.development_all
    report["natural_selection_with_formal_guard"] = args.natural_selection
    report["public_examples_hidden_from_model_prompt"] = args.hide_public_inputs
    (args.output / "training.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
