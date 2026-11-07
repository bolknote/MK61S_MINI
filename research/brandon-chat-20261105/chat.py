#!/usr/bin/env python3
"""Run pinned Brandon 10.7M with the author's reviewed model/tokenizer code.

Weights are read with safetensors; the author's pickle checkpoint loader is unused.
--q4 simulates row-padded 32-weight Q4 blocks with FP16 scales, on the host.
This is a numerical test, not an embedded inference implementation.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / ".build" / "brandon-chat-20261105"
MODEL_ID = "xaskasdf/brandon-tiny-10m-instruct"
REVISION = "ca6329de991a1cfc17b2a7a1aaae2cc38c08577a"
QUESTIONS = ["Hi! What is your name?", "What do you like to do?",
             "I'm tired today. Can you suggest something simple?",
             "Why does it snow in winter?", "What is two plus two?"]


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(name):
    manifest = json.loads((WORK / "source" / "manifest.json").read_text())
    relative = f"src/{name}.py"
    path = WORK / "source" / relative
    if fingerprint(path) != manifest["files"][relative]["sha256"]:
        raise ValueError(f"Source changed: {path}")
    spec = importlib.util.spec_from_file_location(f"brandon_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def q4_roundtrip(model):
    """Nearest Q4 using signed max/-8 scale; pad each row to 32 weights.

    Store 16 packed bytes plus one FP16 scale per block. Small non-matrix
    parameters remain FP32. Host inference uses dequantized FP32 tensors.
    """
    import torch
    total = 0
    matrices = []
    with torch.no_grad():
        for name, parameter in model.named_parameters():
            if parameter.ndim != 2 or name == "dwa_weights":
                total += parameter.numel() * 4
                continue
            rows, columns = parameter.shape
            padded = (columns + 31) // 32 * 32
            values = torch.nn.functional.pad(parameter, (0, padded - columns)).reshape(-1, 32)
            extreme = values.gather(1, values.abs().argmax(1, keepdim=True))
            scale = (extreme / -8).half().float()
            inv = torch.where(scale != 0, scale.reciprocal(), 0)
            code = torch.floor(values * inv + 8.5).clamp(0, 15)
            restored = ((code - 8) * scale).reshape(rows, padded)[:, :columns]
            error = (parameter - restored).square().mean().sqrt().item()
            parameter.copy_(restored)
            size = rows * (padded // 32) * 18
            matrices.append({"name": name, "shape": [rows, columns],
                             "padded_columns": padded, "bytes": size, "rmse": error})
            total += size
    return {"format": "row-padded Q4, 32 weights + FP16 scale, other parameters FP32",
            "packed_weight_bytes": total, "matrices": matrices,
            "execution": "quantize/dequantize simulation; FP32 host arithmetic; no packed file or device runtime"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--prompt")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--top-k", type=int, default=40)
    parser.add_argument("--repetition-penalty", type=float, default=1.2)
    parser.add_argument("--no-repeat-ngram-size", type=int, default=3)
    parser.add_argument("--context", type=int, default=256)
    parser.add_argument("--max-new-tokens", type=int, default=80)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--q4", action="store_true")
    args = parser.parse_args()
    if args.smoke and args.prompt is not None:
        parser.error("use --smoke or --prompt")
    if not 32 <= args.context <= 512 or not 1 <= args.max_new_tokens < args.context:
        parser.error("invalid context or answer budget")
    if not 0 <= args.temperature <= 2 or not 0 < args.top_p <= 1 or args.top_k < 0:
        parser.error("invalid sampling parameters")
    if args.repetition_penalty <= 0 or args.no_repeat_ngram_size < 0:
        parser.error("invalid repetition parameters")
    import torch
    from safetensors.torch import load_file
    torch.set_num_threads(2)
    torch.manual_seed(args.seed)
    source = load_module("model")
    config = json.loads((WORK / "model" / "config.json").read_text())
    fields = {field.name for field in dataclasses.fields(source.ModelConfig)}
    model = source.TinyLlama(source.ModelConfig(**{k: v for k, v in config.items() if k in fields})).eval()
    model.load_state_dict(load_file(WORK / "model" / "model.safetensors"), strict=True)
    model.requires_grad_(False)
    tokenizer = load_module("tokenizer").Tokenizer(str(WORK / "model" / "tokenizer.model"))
    report = {"model": MODEL_ID, "revision": REVISION, "parameter_count": model.count_parameters(False),
              "source": json.loads((WORK / "source" / "manifest.json").read_text()),
              "model_sha256": fingerprint(WORK / "model" / "model.safetensors"),
              "tokenizer_sha256": fingerprint(WORK / "model" / "tokenizer.model"),
              "packages": {n: importlib.metadata.version(n) for n in
                           ["torch", "safetensors", "sentencepiece"]},
              "settings": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
              "prompt_format": "Whole ChatML string encoded as in author's inference example; no system/BOS",
              "stop_tokens": tokenizer.get_stop_tokens(), "samples": []}
    if args.q4:
        report["quantization"] = q4_roundtrip(model)
    print(f"{MODEL_ID}: {report['parameter_count']:,} parameters, "
          f"{'Q4 simulation' if args.q4 else 'FP32'}, CPU", flush=True)

    def answer(messages):
        while True:
            prompt = "".join(f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n" for m in messages)
            prompt += "<|im_start|>assistant\n"
            ids = tokenizer.encode(prompt)
            if len(ids) + args.max_new_tokens <= args.context:
                break
            if len(messages) <= 1:
                raise ValueError("Question is too long for the context and answer budget")
            del messages[:2]
            print("[Старые реплики исключены из контекста.]", flush=True)
        start = time.perf_counter()
        output = model.generate(torch.tensor(ids), max_new_tokens=args.max_new_tokens,
                                temperature=args.temperature, top_p=args.top_p, top_k=args.top_k,
                                repetition_penalty=args.repetition_penalty,
                                no_repeat_ngram_size=args.no_repeat_ngram_size,
                                stop_tokens=tokenizer.get_stop_tokens())
        elapsed = time.perf_counter() - start
        generated = output[0, len(ids):].tolist()
        reply = tokenizer.decode(generated, skip_special=True).strip()
        print(reply, flush=True)
        report["samples"].append({"messages": [dict(m) for m in messages], "rendered_prompt": prompt,
                                  "prompt_tokens": len(ids), "generated_tokens": len(generated),
                                  "reply": reply, "raw_reply": tokenizer.decode(generated),
                                  "ended_with_eos": bool(generated and generated[-1] in tokenizer.get_stop_tokens()),
                                  "hit_token_limit": len(generated) == args.max_new_tokens,
                                  "seconds": elapsed, "tokens_per_second": len(generated) / elapsed})
        return reply

    try:
        if args.smoke:
            for question in QUESTIONS:
                print(f"\nВы: {question}\nМодель: ", end="", flush=True)
                answer([{"role": "user", "content": question}])
            messages = [{"role": "user", "content": "My name is Boris. How are you?"}]
            for turn in range(2):
                if turn:
                    messages.append({"role": "user", "content": "What is my name?"})
                print(f"\nВы: {messages[-1]['content']}\nМодель: ", end="", flush=True)
                messages.append({"role": "assistant", "content": answer(messages)})
        elif args.prompt is not None:
            answer([{"role": "user", "content": args.prompt}])
        else:
            print("Команды: /new — новый разговор, /quit — выход.")
            messages = []
            while True:
                try:
                    question = input("\nВы: ").strip()
                except EOFError:
                    break
                if question == "/quit":
                    break
                if question == "/new":
                    messages.clear()
                    continue
                if not question:
                    continue
                messages.append({"role": "user", "content": question})
                try:
                    reply = answer(messages)
                except ValueError as error:
                    messages.pop()
                    print(error)
                    continue
                messages.append({"role": "assistant", "content": reply})
    except KeyboardInterrupt:
        print("\nОстановлено.")
    finally:
        if args.json:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            print(f"Запись: {args.json}")


if __name__ == "__main__":
    main()
