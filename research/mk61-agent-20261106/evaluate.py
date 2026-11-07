"""Functional coding evaluation; model-written success claims are not grades."""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path
import time

import torch
import harness
from transformers import AutoModelForCausalLM, AutoTokenizer

from emulator import Emulator
from harness import agent_run
from quantization import export_q4, load_q4
from prompt_variants import without_public_examples


def generator(model, tokenizer, *, context=512, max_new=160, plan=True, hide_public_inputs=False):
    device = next(model.parameters()).device

    def generate(prompt):
        if hide_public_inputs:prompt=without_public_examples(prompt)
        if not plan:
            prompt = prompt.replace("<plan>краткий план</plan>", "").replace(
                "<plan>взять R0 и R1; сложить</plan>", "")
        ids = tokenizer.encode(prompt, add_special_tokens=False)
        # Preserve a bounded active context. The harness stores the full trace
        # separately and renders only the current task, candidate and failure.
        ids = ids[-(context - max_new):]
        inputs = torch.tensor([ids], dtype=torch.long, device=device)
        with torch.inference_mode():
            output = model.generate(input_ids=inputs, attention_mask=torch.ones_like(inputs),
                                    max_new_tokens=max_new, do_sample=False, use_cache=True,
                                    pad_token_id=tokenizer.pad_token_id or 0,
                                    eos_token_id=tokenizer.eos_token_id)
        return tokenizer.decode(output[0, len(ids):], skip_special_tokens=True)

    return generate


def evaluate(model, tokenizer, tasks, *, turns=3, plan=True, max_new=160):
    emulator = Emulator()
    generate = generator(model, tokenizer, plan=plan, max_new=max_new)
    start = time.monotonic()
    rows = []
    for index, task in enumerate(tasks):
        rows.append(agent_run(task, generate, emulator, turns=turns))
        if (index + 1) % 10 == 0:
            print(json.dumps({"evaluated": index + 1, "passed": sum(x["pass"] for x in rows)}), flush=True)
    by_kind = {}
    for kind in sorted({row["kind"] for row in rows}):
        subset = [row for row in rows if row["kind"] == kind]
        by_kind[kind] = {"total": len(subset), "passed": sum(row["pass"] for row in subset)}
    return {"total": len(rows), "passed": sum(row["pass"] for row in rows),
            "pass_rate": sum(row["pass"] for row in rows) / max(1, len(rows)),
            "valid_tool_tasks": sum(row["valid_tool_calls"] > 0 for row in rows),
            "by_kind": by_kind, "seconds": time.monotonic() - start,
            "turn_budget": turns, "max_new_tokens_per_turn": max_new,
            "protocol_sha256": hashlib.sha256(Path(harness.__file__).read_bytes()).hexdigest(),
            "method": "Greedy, unchanged tool budget, real microcode core, public inputs plus independent hidden tests",
            "details": rows}


def read_tasks(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--q4", action="store_true")
    parser.add_argument("--no-plan", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--turns", type=int, default=3)
    parser.add_argument("--max-new", type=int, default=160)
    args = parser.parse_args()
    torch.set_num_threads(2)
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True, trust_remote_code=False)
    model = AutoModelForCausalLM.from_pretrained(args.model, local_files_only=True, trust_remote_code=False).to(args.device).eval()
    tasks = read_tasks(args.tasks)
    if args.limit:
        tasks = tasks[:args.limit]
    packed = None
    if args.q4:
        packed = export_q4(model, args.output.with_suffix(".mkq4"))
        load_q4(model, args.output.with_suffix(".mkq4"))
    result = evaluate(model, tokenizer, tasks, turns=args.turns, plan=not args.no_plan, max_new=args.max_new)
    result.update(model=str(args.model), q4=args.q4, packed=packed,
                  tasks_sha256=hashlib.sha256(args.tasks.read_bytes()).hexdigest())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "details"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
