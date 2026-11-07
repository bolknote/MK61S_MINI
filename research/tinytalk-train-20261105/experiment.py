#!/usr/bin/env python3
"""Small, reproducible full-parameter TinyTalk fine-tuning pilot.

prepare: disjoint synthetic tasks + optional JSONL teacher examples.
train: assistant-only SFT, select checkpoint on validation loss, never test.
evaluate: original vs selected vs simulated Q4 on a reserved test set.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import nullcontext
import hashlib
import importlib.metadata
import inspect
import json
import math
import os
from pathlib import Path
import random
import re
import sys
import time

os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
MODEL = "TheREZOR/TinyTalk"
REVISION = "61c79ad139344cdd344a687b35fa8f1c52326154"
ORIGINAL_SHA = "d7510ceac1d4f2a7d00b6f2da92cdce38706faa60a96c60884819d00ef58af77"
PARAMETERS = 8278400
EOS = "<|endoftext|>"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def render(messages):
    result = ""
    for index, message in enumerate(messages):
        expected = "user" if index % 2 == 0 else "assistant"
        assert message["role"] == expected
        if expected == "user":
            result += f"User: {message['content']}\n"
        else:
            result += f"Bot: {message['content']}{EOS}\n"
    assert messages[-1]["role"] == "user"
    return result + "Bot:"


def prepare(args):
    root = Path(args.data)
    root.mkdir(parents=True, exist_ok=True)
    values = {
        "name": ("My name is {}.", "Your name is {}.", [
            "Alice Ben Carol David Emma Frank Grace Henry Isabel James Kate Leo Mia Noah Olivia Paul Rachel Sam Tina Victor Wendy Zoe Andrew Brenda Colin Diana Edward Fiona George Helen Ian Julia Kevin Linda Martin Nancy Owen Peter Rita Simon Teresa Walter Yvonne Aaron Bella Cedric Denise Elliot Freya Gordon Hazel Iris Julian Kira Lewis Megan Nolan Opal Philip Quinn Rose Steve Vera Xander Yara Zane".split(),
            "Adrian Celia Derek Elise Fabian Greta Hugo Ingrid Jonas Keira Louis Mabel Nathan Orla Perry Selma".split(),
            "Agnes Arthur Beatrice Calvin Dorian Edith Felix Hannah Jasper Lucia Marcus Nadia Otto Petra Silas Violet".split()]),
        "dog": ("My dog is named {}.", "Your dog's name is {}.", [
            "Rex Spot Milo Ruby Max Daisy Buddy Oscar Teddy Toby Molly Lucy Bailey Archie Buster Chloe Duke Ellie Finn Gus Holly Ivy Joey Koda Lola Marley Nina Ollie Poppy Rocco Scout Tilly Willow Ziggy".split(),
            "Benny Dolly Harvey Millie Monty Olive Remy Rosie Rufus Suki".split(),
            "Amber Basil Bramble Clover Dexter Hazel Jasper Misty Pebble Rusty".split()]),
        "city": ("I live in {}.", "You live in {}.", [
            "London Paris Berlin Rome Boston Denver Tokyo Madrid Milan Dublin Oslo Miami Austin Dallas Bristol Cardiff York Oxford Lincoln Durham Leeds Exeter Newport Plymouth Dover Preston Derby Reading Norwich Cambridge".split(),
            "Athens Vienna Prague Lisbon Warsaw Munich Naples Lyon Nice Turin".split(),
            "Helsinki Stockholm Bergen Venice Verona Seville Toledo Bremen Hamburg Bath".split()]),
        "food": ("My favorite food is {}.", "Your favorite food is {}.", [
            "pizza soup bread pasta rice salad cake fish meat cheese beans noodles apples bananas carrots grapes potatoes tomatoes eggs chicken cookies yogurt pancakes peaches pears plums oranges oats peas".split(),
            "cherries spinach cabbage lentils salmon waffles pudding mango tofu pumpkin".split(),
            "apricots broccoli cucumber dumplings lasagna porridge raisins raspberries squash strawberries".split()]),
    }
    queries = {
        "name": [["What is my name?", "Can you tell me my name?", "Do you remember my name?"],
                 ["Please remind me of my name."], ["Which name did I tell you?"]],
        "dog": [["What is my dog's name?", "What did I name my dog?", "Do you remember my dog's name?"],
                ["Please remind me what my dog is called."], ["Which name belongs to my dog?"]],
        "city": [["Where do I live?", "What city do I live in?", "Do you remember where I live?"],
                 ["Please remind me where my home is."], ["Which city did I say I live in?"]],
        "food": [["What is my favorite food?", "Which food do I like best?", "Do you remember my favorite food?"],
                 ["Please remind me which food I like most."], ["Which food did I say was my favorite?"]],
    }
    splits = [[], [], []]
    for kind, (intro, target, pools) in values.items():
        for split, pool in enumerate(pools):
            for value in pool:
                for distractor in [False, True]:
                    for variant in range(4 if split == 0 else 2):
                        fact = intro.format(value)
                        if distractor:
                            friend = pools[0][(pools[0].index(value) + 1) % len(pools[0])] if split == 0 else pools[0][variant]
                            other = intro.format(friend).replace("My ", "My friend's ", 1).replace("I live", "My friend lives")
                            fact += " " + other
                        messages = [{"role": "user", "content": fact},
                                    {"role": "assistant", "content": ["Thanks for telling me.", "I will try to remember."][variant % 2]},
                                    {"role": "user", "content": queries[kind][split][variant % len(queries[kind][split])]}]
                        splits[split].append({"kind": "context", "category": kind, "messages": messages,
                                              "target": target.format(value), "value": value,
                                              "distractors": [friend] if distractor else []})
    # Canonical operand pairs: neither order of a test pair occurs in training.
    for left in range(21):
        for right in range(left, 21):
            bucket = int(hashlib.sha256(f"plus:{left}:{right}:frozen-v1".encode()).hexdigest(), 16) % 10
            split = 2 if bucket == 0 else 1 if bucket == 1 else 0
            formats = [["What is {a} plus {b}?", "How much is {a} + {b}?", "Add {a} and {b}."],
                       ["Please calculate {a} + {b}."], ["What total do {a} and {b} make?"]][split]
            for form in formats:
                for a, b in [(left, right), (right, left)] if left != right else [(left, right)]:
                    splits[split].append({"kind": "arithmetic", "category": "addition",
                                          "messages": [{"role": "user", "content": form.format(a=a, b=b)}],
                                          "target": str(a + b) + ".", "value": a + b, "operands": [a, b]})
    teacher_counts = [0, 0, 0]
    if args.teacher:
        seen = set()
        for item in read_rows(args.teacher):
            question, answer = item["question"].strip(), item["answer"].strip()
            key = re.sub(r"\W+", " ", question.lower()).strip()
            if key in seen or not question or not answer or len(answer.split()) > 30:
                continue
            seen.add(key)
            split = int(item["split"])  # Topic groups assigned before teacher generation.
            assert split in [0, 1, 2]
            splits[split].append({"kind": "teacher", "category": item["topic"],
                                  "messages": [{"role": "user", "content": question}],
                                  "target": answer})
            teacher_counts[split] += 1
    # Same rendered question cannot occur in two splits.
    keys = [{render(row["messages"]) for row in rows} for rows in splits]
    assert not keys[0] & keys[1] and not keys[0] & keys[2] and not keys[1] & keys[2]
    manifest = {"model": MODEL, "revision": REVISION, "teacher_counts": teacher_counts,
                "purpose": "Targeted English skill pilot; not a general intelligence benchmark",
                "split_policy": "Disjoint context values within each category and question forms; addition pairs grouped before splitting; teacher topic groups preassigned"}
    for name, rows in zip(["train", "validation", "test"], splits):
        random.Random(872 + len(name)).shuffle(rows)
        path = root / f"{name}.jsonl"
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
        manifest[name] = {"rows": len(rows), "kinds": dict(Counter(row["kind"] for row in rows)), "sha256": digest(path)}
    save(root / "manifest.json", manifest)
    print(json.dumps(manifest, indent=2), flush=True)


def load(args, model_dir=None):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    torch.set_num_threads(4)
    torch.manual_seed(args.seed)
    path = Path(model_dir or args.model)
    tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True, trust_remote_code=False)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"
    model = AutoModelForCausalLM.from_pretrained(path, local_files_only=True, trust_remote_code=False,
                                                dtype=torch.float32, attn_implementation="eager")
    assert sum(p.numel() for p in model.parameters()) == PARAMETERS
    device = "cuda" if args.device == "auto" and torch.cuda.is_available() else "cpu" if args.device == "auto" else args.device
    model.to(device)
    return model, tokenizer, device


def encode_rows(tokenizer, rows, context):
    result, skipped = [], 0
    for row in rows:
        prompt = render(row["messages"])
        prefix = tokenizer.encode(prompt, add_special_tokens=False)
        tokens = tokenizer.encode(prompt + " " + row["target"], add_special_tokens=False) + [tokenizer.eos_token_id]
        assert tokens[:len(prefix)] == prefix
        if len(tokens) > context:
            skipped += 1
            continue
        result.append((tokens, [-100] * len(prefix) + tokens[len(prefix):], row["kind"]))
    if not result:
        raise ValueError("No complete training examples fit in context")
    return result, skipped


def batch(rows, pad, device):
    import torch
    width = max(len(tokens) for tokens, _, _ in rows)
    ids = torch.full((len(rows), width), pad, dtype=torch.long, device=device)
    labels = torch.full_like(ids, -100)
    mask = torch.zeros_like(ids)
    for index, (tokens, targets, _) in enumerate(rows):
        ids[index, :len(tokens)] = torch.tensor(tokens, device=device)
        labels[index, :len(tokens)] = torch.tensor(targets, device=device)
        mask[index, :len(tokens)] = 1
    return ids, labels, mask


def completion_loss(model, rows, pad, device):
    import torch
    ids, labels, mask = batch(rows, pad, device)
    hidden = model.transformer(input_ids=ids, attention_mask=mask, use_cache=False).last_hidden_state
    use = labels[:, 1:] != -100
    logits = model.lm_head(hidden[:, :-1][use])
    return torch.nn.functional.cross_entropy(logits.float(), labels[:, 1:][use], reduction="sum"), int(use.sum())


def train(args):
    import torch
    output = Path(args.output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Use a new empty output directory for each experiment")
    output.mkdir(parents=True, exist_ok=True)
    assert digest(Path(args.model) / "model.safetensors") == ORIGINAL_SHA
    model, tokenizer, device = load(args)
    qat_state = None
    if args.qat:
        from quantize import qat_modules
        qat_state = qat_modules(model)
    if device == "cuda" and not torch.cuda.is_bf16_supported():
        raise ValueError("CUDA BF16 support is required for this pilot")
    training, skipped = encode_rows(tokenizer, read_rows(Path(args.data) / "train.jsonl"), args.context)
    validation, val_skipped = encode_rows(tokenizer, read_rows(Path(args.data) / "validation.jsonl"), args.context)
    if val_skipped:
        raise ValueError("Validation examples must fit without truncation")
    groups = {kind: [row for row in training if row[2] == kind] for kind in {r[2] for r in training}}
    rng = random.Random(args.seed)
    kinds = sorted(groups)
    # Natural answers receive half the samples when available, to protect dialogue.
    kind_weights = [0.5 if k == "teacher" else 0.3 if k == "context" else 0.2 for k in kinds]
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    amp = lambda: torch.autocast("cuda", dtype=torch.bfloat16) if device == "cuda" else nullcontext()
    report = {"model": MODEL, "revision": REVISION, "original_sha256": ORIGINAL_SHA,
              "parameters": PARAMETERS, "settings": vars(args), "device": device,
              "packages": {n: importlib.metadata.version(n) for n in ["torch", "transformers", "safetensors"]},
              "data": json.loads((Path(args.data) / "manifest.json").read_text()),
              "training_rows": len(training), "skipped_training_rows": skipped,
              "optimizer_storage_floor_bytes": PARAMETERS * 16,
              "test_used_for_training_or_selection": False, "history": []}
    if device == "cuda":
        free, total = torch.cuda.mem_get_info()
        report["gpu"] = {"name": torch.cuda.get_device_name(), "free_bytes_before_training": free, "total_bytes": total}
        torch.cuda.reset_peak_memory_stats()

    @torch.inference_mode()
    def validate():
        model.eval()
        sums, counts = Counter(), Counter()
        for start in range(0, len(validation), args.batch_size):
            rows = validation[start:start + args.batch_size]
            # Group by kind so regression in natural language is visible.
            for kind in sorted({row[2] for row in rows}):
                selected = [row for row in rows if row[2] == kind]
                with amp():
                    loss, count = completion_loss(model, selected, tokenizer.eos_token_id, device)
                sums[kind] += float(loss); counts[kind] += count
        by_kind = {k: sums[k] / counts[k] for k in sums}
        score = sum(by_kind.values()) / len(by_kind)
        return {"mean_kind_nll": score, "by_kind_nll": by_kind}

    started = time.perf_counter()
    baseline = validate()
    report["baseline_validation"] = baseline
    best = baseline["mean_kind_nll"]
    report["best_step"] = 0
    # The original is a valid selection if every checkpoint regresses.
    def checkpoint(path):
        if qat_state:
            from quantize import save_qat_checkpoint
            save_qat_checkpoint(model, path, qat_state)
        else:
            model.save_pretrained(path, safe_serialization=True)
        from quantize import copy_notices
        copy_notices(args.model, path)

    checkpoint(output / "best")
    tokenizer.save_pretrained(output / "best")
    for step in range(1, args.steps + 1):
        model.train()
        optimizer.zero_grad(set_to_none=True)
        losses = []
        for _ in range(args.grad_accum):
            rows = [rng.choice(groups[rng.choices(kinds, weights=kind_weights)[0]]) for _ in range(args.batch_size)]
            with amp():
                total, count = completion_loss(model, rows, tokenizer.eos_token_id, device)
                loss = total / count / args.grad_accum
            if not torch.isfinite(loss):
                raise ValueError("Non-finite training loss")
            loss.backward()
            losses.append(float(loss.detach()) * args.grad_accum)
        norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        if not torch.isfinite(norm):
            raise ValueError("Non-finite gradient norm")
        warmup = min(1.0, step / max(1, min(30, args.steps // 10)))
        cosine = 0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * step / args.steps))
        for group in optimizer.param_groups:
            group["lr"] = args.lr * warmup * cosine
        optimizer.step()
        if step == 1 or step % 25 == 0:
            print(json.dumps({"step": step, "train_loss": sum(losses) / len(losses),
                              "seconds": round(time.perf_counter() - started, 2)}), flush=True)
        if step % args.eval_every == 0 or step == args.steps:
            metrics = validate()
            metrics.update(step=step, seconds=time.perf_counter() - started)
            natural = metrics["by_kind_nll"].get("teacher", 0)
            natural_baseline = baseline["by_kind_nll"].get("teacher", 0)
            eligible = natural <= natural_baseline + 0.15
            metrics["natural_language_guard_passed"] = eligible
            report["history"].append(metrics)
            if eligible and metrics["mean_kind_nll"] < best:
                best = metrics["mean_kind_nll"]
                report["best_step"] = step
                model.eval()
                checkpoint(output / "best")
            save(output / "training.json", report)
            print(json.dumps({"validation": metrics, "best_step": report["best_step"]}), flush=True)
    model.eval()
    checkpoint(output / "last")
    tokenizer.save_pretrained(output / "last")
    report["seconds"] = time.perf_counter() - started
    report["original_unchanged"] = digest(Path(args.model) / "model.safetensors") == ORIGINAL_SHA
    report["best_sha256"] = digest(output / "best" / "model.safetensors")
    report["best_parameters"] = sum(p.numel() for p in model.parameters())
    if device == "cuda":
        report["gpu"].update(peak_allocated_bytes=torch.cuda.max_memory_allocated(), peak_reserved_bytes=torch.cuda.max_memory_reserved())
    save(output / "training.json", report)
    print(json.dumps({k: report[k] for k in ["best_step", "seconds", "original_unchanged", "best_sha256"]}), flush=True)


def score(row, reply, ended):
    text = reply.lower().strip()
    if row["kind"] == "context":
        found = bool(re.search(r"(?<!\w)" + re.escape(row["value"].lower()) + r"(?!\w)", text))
        wrong = any(re.search(r"(?<!\w)" + re.escape(v.lower()) + r"(?!\w)", text) for v in row["distractors"])
        own = {"name": r"(?:my name is|i am|i'm)", "dog": r"my dog's name is",
               "food": r"my favorite food is", "city": r"i live in"}[row["category"]]
        confused = bool(re.search(r"\b" + own + r"\s+" + re.escape(row["value"].lower()) + r"\b", text))
        words = re.findall(r"\w+", text)
        triples = [tuple(words[i:i+3]) for i in range(len(words) - 2)]
        return bool(ended and found and not wrong and not confused and len(triples) == len(set(triples)))
    if row["kind"] == "arithmetic":
        # Strict one-number answer, so echoing the question cannot pass.
        numbers = [int(n) for n in re.findall(r"(?<!\w)-?\d+(?!\w)", text)]
        words = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
                 "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"]
        spellings = {word: n for n, word in enumerate(words)}
        spellings.update({"twenty " + words[n]: 20 + n for n in range(1, 10)})
        spellings.update({"thirty": 30, "forty": 40})
        spellings.update({"thirty " + words[n]: 30 + n for n in range(1, 10)})
        verbal = text.rstrip(".! ").replace("-", " ")
        if not numbers and verbal in spellings:
            numbers = [spellings[verbal]]
        return bool(ended and numbers == [row["value"]])
    return None


def evaluate(args):
    import torch
    rows = read_rows(Path(args.data) / "test.jsonl")
    if args.limit:
        rows = rows[:args.limit]
    for question in ["Hi! What is your name?", "What do you like to do?",
                     "I'm tired today. Can you suggest something simple?",
                     "Why does it snow in winter?", "What is two plus two?"]:
        rows.append({"kind": "chat_probe", "messages": [{"role": "user", "content": question}], "target": ""})
    rows.append({"kind": "chat_probe", "messages": [
        {"role": "user", "content": "My name is Boris. How are you?"},
        {"role": "assistant", "content": "Nice to meet you."},
        {"role": "user", "content": "What is my name?"}], "target": ""})
    report = {"data_sha256": digest(Path(args.data) / "test.jsonl"), "settings": vars(args),
              "selection_policy": "Checkpoint chosen by validation before this test is read", "models": {}}
    variants = [("original", args.model, False), ("original_q4", args.model, True),
                ("trained", args.candidate, False), ("trained_q4", args.candidate, True)]
    for label, path, quantized in variants:
        model, tokenizer, device = load(args, path)
        model.eval().requires_grad_(False)
        quantization = None
        if quantized:
            from quantize import roundtrip
            quantization = roundtrip(model)
        details = []
        tokenizer.padding_side = "left"
        with torch.inference_mode():
            for start in range(0, len(rows), args.eval_batch_size):
                group = rows[start:start + args.eval_batch_size]
                batch_inputs = tokenizer([render(r["messages"]) for r in group], padding=True,
                                         add_special_tokens=False, return_tensors="pt").to(device)
                assert batch_inputs.input_ids.shape[1] + 32 <= 256
                options = {"max_new_tokens": 32, "do_sample": False, "use_cache": True,
                           "pad_token_id": tokenizer.eos_token_id, "eos_token_id": tokenizer.eos_token_id}
                if "logits_to_keep" in inspect.signature(model.forward).parameters:
                    options["logits_to_keep"] = 1
                outputs = model.generate(**batch_inputs, **options)[:, batch_inputs.input_ids.shape[1]:]
                for row, generated in zip(group, outputs.tolist()):
                    ended = tokenizer.eos_token_id in generated
                    if ended:
                        generated = generated[:generated.index(tokenizer.eos_token_id) + 1]
                    reply = tokenizer.decode(generated, skip_special_tokens=True).strip()
                    details.append(row | {"reply": reply, "ended_with_eos": ended, "correct": score(row, reply, ended)})
        tokenizer.padding_side = "right"
        teacher_rows = [row for row in rows if row["kind"] == "teacher"]
        encoded, _ = encode_rows(tokenizer, teacher_rows, 256) if teacher_rows else ([], 0)
        total_loss, total_count = 0, 0
        with torch.inference_mode():
            for start in range(0, len(encoded), args.eval_batch_size):
                loss, count = completion_loss(model, encoded[start:start + args.eval_batch_size], tokenizer.eos_token_id, device)
                total_loss += float(loss); total_count += count
        metrics = {}
        for kind in ["context", "arithmetic", "teacher"]:
            subset = [d for d in details if d["kind"] == kind]
            metrics[kind] = {"total": len(subset), "correct": sum(d["correct"] is True for d in subset) if kind != "teacher" else None,
                             "ended_with_eos": sum(d["ended_with_eos"] for d in subset)}
        metrics["teacher_reference_nll"] = total_loss / total_count if total_count else None
        report["models"][label] = {"sha256": digest(Path(path) / "model.safetensors"),
                                    "quantization": quantization, "metrics": metrics, "details": details}
        save(args.report, report)
        print(json.dumps({"model": label, "metrics": metrics}), flush=True)
        del model
        if device == "cuda":
            torch.cuda.empty_cache()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "train", "evaluate"])
    parser.add_argument("--model", default=".build/tinytalk-chat-20261105/model")
    parser.add_argument("--data", default=".build/tinytalk-train-20261105/data")
    parser.add_argument("--teacher")
    parser.add_argument("--output", default=".build/tinytalk-train-20261105/run")
    parser.add_argument("--candidate")
    parser.add_argument("--report", default="research/tinytalk-train-20261105/evaluation.json")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--seed", type=int, default=5927)
    parser.add_argument("--steps", type=int, default=500)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--grad-accum", type=int, default=1)
    parser.add_argument("--lr", type=float, default=5e-5)
    parser.add_argument("--context", type=int, default=256)
    parser.add_argument("--eval-every", type=int, default=100)
    parser.add_argument("--eval-batch-size", type=int, default=8)
    parser.add_argument("--limit", type=int, default=0, help="Smoke evaluation only; full report should use 0")
    parser.add_argument("--qat", action="store_true", help="Full-parameter learning with a straight-through Q4 simulation")
    args = parser.parse_args()
    for value in [args.steps, args.batch_size, args.grad_accum, args.eval_every, args.eval_batch_size]:
        if value < 1:
            parser.error("step and batch counts must be positive")
    if not 32 <= args.context <= 256 or args.lr <= 0 or args.limit < 0:
        parser.error("invalid context, learning rate or limit")
    if args.mode == "evaluate" and not args.candidate:
        parser.error("--candidate is required for evaluation")
    {"prepare": prepare, "train": train, "evaluate": evaluate}[args.mode](args)


if __name__ == "__main__":
    main()
