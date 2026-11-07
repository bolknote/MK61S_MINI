#!/usr/bin/env python3
"""Try small chat models locally, before quantization.

Run with --download-only once, then without arguments for an interactive chat.
--smoke runs a small, explicitly ungraded conversation sample.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / ".build" / "squeal-chat-20261105"
MODEL_DIR = WORK / "model"
MODEL_ID = "Squeal-Studio/squeal_ai_8m-instruct"
REVISION = "24dd4690ffa674a608387cf864c695239ed7964f"
PROFILES = {
    "squeal": {"model": MODEL_ID, "revision": REVISION, "directory": MODEL_DIR,
               "questions": ("Привет! Как тебя зовут?", "Что ты любишь делать?",
                             "Я сегодня устал. Посоветуй что-нибудь простое.",
                             "Почему зимой идёт снег?", "Сколько будет два плюс два?"),
               "introduction": "Меня зовут Борис. Как дела?", "recall": "Как меня зовут?",
               "prompt_format": "Author template with bot roles and an explicit assistant generation marker"},
    "tinytalk": {"model": "TheREZOR/TinyTalk",
                 "revision": "61c79ad139344cdd344a687b35fa8f1c52326154",
                 "directory": ROOT / ".build" / "tinytalk-chat-20261105" / "model",
                 "questions": ("Hi! What is your name?", "What do you like to do?",
                               "I'm tired today. Can you suggest something simple?",
                               "Why does it snow in winter?", "What is two plus two?"),
                 "introduction": "My name is Boris. How are you?", "recall": "What is my name?",
                 "prompt_format": "User: message, newline, Bot: reply; EOS between exchanges; final Bot: generation marker"},
    "stentor": {"model": "StentorLabs/Stentor-12M-Instruct",
                "revision": "6d44a6ffc689a021365eb97ea66d795929a1b646",
                "directory": ROOT / ".build" / "stentor-chat-20261105" / "model",
                "questions": ("Hi! What is your name?", "What do you like to do?",
                              "I'm tired today. Can you suggest something simple?",
                              "Why does it snow in winter?", "What is two plus two?"),
                "introduction": "My name is Boris. How are you?", "recall": "What is my name?",
                "system_prompt": "You are a helpful assistant.",
                "prompt_format": "Published tokenizer chat template with the author's quick-start system prompt"},
}
os.environ.setdefault("HF_HOME", str(WORK / "huggingface"))
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=PROFILES, default="squeal")
    parser.add_argument("--download-only", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--prompt")
    parser.add_argument("--model-dir", type=Path,
                        help="Use a local edited copy instead of the original weights")
    parser.add_argument("--packed-q4", type=Path,
                        help="Restore a TTQ4v1 TinyTalk file for FP32 host inference")
    parser.add_argument("--json", type=Path, help="Save prompts, raw answers and settings")
    parser.add_argument("--temperature", type=float, default=0.7,
                        help="0 for greedy decoding; default: 0.7")
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--top-k", type=int, default=40)
    parser.add_argument("--repetition-penalty", type=float, default=1.0)
    parser.add_argument("--system-prompt", help="Override Stentor's quick-start system prompt")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--context", type=int, default=256,
                        help="Total prompt plus answer token budget")
    parser.add_argument("--max-new-tokens", type=int, default=80)
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    if args.model_dir is None:
        args.model_dir = PROFILES[args.profile]["directory"]
    if not 0 <= args.temperature <= 2:
        parser.error("temperature must be between 0 and 2")
    if not 0 < args.top_p <= 1 or args.top_k < 0 or args.repetition_penalty <= 0:
        parser.error("invalid sampling parameters")
    if args.system_prompt is not None and args.profile != "stentor":
        parser.error("--system-prompt is supported for Stentor only")
    if args.packed_q4 is not None and args.profile != "tinytalk":
        parser.error("--packed-q4 is supported for TinyTalk only")
    if args.context < 32 or not 1 <= args.max_new_tokens < args.context:
        parser.error("context must exceed max-new-tokens and be at least 32")
    if args.threads < 1 or (args.smoke and args.prompt is not None):
        parser.error("use positive threads, and either --smoke or --prompt")
    return args


def manifest(model_dir=MODEL_DIR, model_id=MODEL_ID, revision=REVISION):
    files = {}
    for name in ("config.json", "generation_config.json", "model.safetensors",
                 "tokenizer.json", "tokenizer_config.json", "chat_template.jinja",
                 "vocab.json", "merges.txt"):
        path = model_dir / name
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            files[name] = {"bytes": path.stat().st_size, "sha256": digest.hexdigest()}
    result = {"model": model_id, "revision": revision, "files": files}
    if (model_dir / "weight-edit.json").is_file():
        result["weight_edit"] = json.loads((model_dir / "weight-edit.json").read_text())
    return result


def render_prompt(tokenizer, messages, profile="squeal", system_prompt=None):
    if profile == "stentor":
        if system_prompt is None:
            system_prompt = PROFILES[profile]["system_prompt"]
        turns = ([{"role": "system", "content": system_prompt}] if system_prompt else [])
        return tokenizer.apply_chat_template(
            turns + messages, tokenize=False, add_generation_prompt=True)
    if profile == "tinytalk":
        turns = []
        for message in messages:
            if message["role"] == "user":
                turns.append(f"User: {message['content']}\n")
            elif message["role"] == "assistant":
                turns.append(f"Bot: {message['content']}{tokenizer.eos_token}\n")
            else:
                raise ValueError("TinyTalk supports user/assistant turns only")
        # The author's runnable example ends at Bot: without a trailing space.
        return "".join(turns) + "Bot:"
    # The published template recognizes "bot", not "assistant", and ignores
    # add_generation_prompt. Match its actual training format.
    turns = [{"role": "bot" if m["role"] == "assistant" else m["role"],
              "content": m["content"]} for m in messages]
    return tokenizer.apply_chat_template(
        turns, tokenize=False, add_generation_prompt=False) + "<|assistant|>\n"


def main(cache_factory=None, logits_processor_factory=None):
    args = arguments()
    profile = PROFILES[args.profile]
    if args.download_only:
        if args.model_dir != profile["directory"]:
            raise SystemExit("--download-only downloads only the original model.")
        from huggingface_hub import snapshot_download
        snapshot_download(profile["model"], revision=profile["revision"], local_dir=args.model_dir,
                          token=False, allow_patterns=["*.json", "*.safetensors",
                                                       "*.jinja", "*.txt", "README.md",
                                                       "LICENSE*", "NOTICE.md"])
        info = manifest(args.model_dir, profile["model"], profile["revision"])
        (args.model_dir.parent / "model-manifest.json").write_text(
            json.dumps(info, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return
    if not (args.model_dir / "model.safetensors").is_file():
        raise SystemExit("First run this script with --download-only.")

    # Loading and all inference below use only the downloaded local files.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, TextStreamer

    torch.set_num_threads(args.threads)
    torch.manual_seed(args.seed)
    tokenizer = AutoTokenizer.from_pretrained(args.model_dir, local_files_only=True,
                                             trust_remote_code=False)
    model = AutoModelForCausalLM.from_pretrained(
        args.model_dir, local_files_only=True, trust_remote_code=False,
        dtype=torch.float32, attn_implementation="eager").to("cpu").eval()
    packed_manifest = None
    if args.packed_q4:
        sys.path.insert(0, str(ROOT / "research" / "tinytalk-train-20261105"))
        from quantize import restore
        packed_manifest = restore(model, args.packed_q4)
        packed_manifest["file_bytes"] = args.packed_q4.stat().st_size
        packed_manifest["file_sha256"] = hashlib.sha256(args.packed_q4.read_bytes()).hexdigest()
    pad_id = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.eos_token_id
    if args.context > model.config.max_position_embeddings:
        raise SystemExit("Requested context exceeds the model's trained context.")
    info = manifest(args.model_dir, profile["model"], profile["revision"])
    if packed_manifest:
        info["packed_q4"] = packed_manifest
    label = profile["model"] + (" [edited weights]" if "weight_edit" in info else "")
    if packed_manifest and packed_manifest["origin"]["source_sha256"] != info["files"]["model.safetensors"]["sha256"]:
        label += " [fine-tuned Q4 weights]"
    precision = "Q4 weights, FP32 host arithmetic" if packed_manifest else "FP32"
    print(f"{label}: {sum(p.numel() for p in model.parameters()):,} parameters, "
          f"{precision}, CPU, context {args.context}", flush=True)
    info.update({"python": sys.version, "platform": platform.platform(),
                 "packages": {p: importlib.metadata.version(p) for p in
                              ("torch", "transformers", "tokenizers", "safetensors",
                               "huggingface-hub")},
                 "settings": {k: str(v) if isinstance(v, Path) else v
                              for k, v in vars(args).items()},
                 "parameter_count": sum(p.numel() for p in model.parameters()),
                 "custom_kv_cache": cache_factory is not None,
                 "custom_logits_processor": logits_processor_factory is not None,
                 "chat_template": tokenizer.chat_template,
                 "prompt_format": profile["prompt_format"],
                 "samples": []})

    def answer(messages):
        # Drop complete old exchanges, never silently truncate the current question.
        while True:
            prompt = render_prompt(tokenizer, messages, args.profile, args.system_prompt)
            encoded = tokenizer(prompt, add_special_tokens=False, return_tensors="pt")
            count = encoded.input_ids.shape[1]
            if count + args.max_new_tokens <= args.context:
                break
            if len(messages) <= 1:
                raise ValueError("Question is too long for this context and answer budget.")
            del messages[:2]
            print("[Старые реплики исключены из контекста.]", flush=True)
        options = {"max_new_tokens": args.max_new_tokens,
                   "do_sample": args.temperature > 0,
                   "use_cache": True,
                   "repetition_penalty": args.repetition_penalty,
                   "pad_token_id": pad_id,
                   "eos_token_id": tokenizer.eos_token_id}
        if args.temperature > 0:
            options.update(temperature=args.temperature, top_p=args.top_p, top_k=args.top_k)
        cache = cache_factory(model) if cache_factory is not None else None
        if cache is not None:
            options['past_key_values'] = cache
        if logits_processor_factory is not None:
            options['logits_processor'] = logits_processor_factory(model, tokenizer, count)
        started = time.perf_counter()
        with torch.inference_mode():
            output = model.generate(
                **encoded, **options,
                streamer=TextStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True))
        elapsed = time.perf_counter() - started
        generated = output[0, count:]
        reply = tokenizer.decode(generated, skip_special_tokens=True).strip()
        record = {"messages": [dict(m) for m in messages], "rendered_prompt": prompt,
                  "prompt_tokens": count, "generated_tokens": len(generated),
                  "reply": reply, "raw_reply": tokenizer.decode(generated),
                  "seconds": elapsed, "tokens_per_second": len(generated) / elapsed,
                  "hit_token_limit": len(generated) == args.max_new_tokens,
                  "ended_with_eos": bool(len(generated) and
                                          int(generated[-1]) == tokenizer.eos_token_id)}
        info["samples"].append(record)
        if cache is not None:
            record['kv_storage_dtypes'] = sorted({str(layer.keys.dtype) for layer in cache.layers
                                                  if getattr(layer, 'keys', None) is not None})
        print(f"[{len(generated)} токенов, {elapsed:.2f} с]", flush=True)
        return reply

    try:
        if args.smoke:
            for question in profile["questions"]:
                print(f"\nВы: {question}\nМодель: ", end="", flush=True)
                answer([{"role": "user", "content": question}])
            messages = [{"role": "user", "content": profile["introduction"]}]
            print(f"\nВы: {messages[0]['content']}\nМодель: ", end="", flush=True)
            messages.append({"role": "assistant", "content": answer(messages)})
            messages.append({"role": "user", "content": profile["recall"]})
            print(f"\nВы: {profile['recall']}\nМодель: ", end="", flush=True)
            answer(messages)
        elif args.prompt is not None:
            print("Модель: ", end="", flush=True)
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
                print("Модель: ", end="", flush=True)
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
            args.json.write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n")
            print(f"Запись: {args.json}")


if __name__ == "__main__":
    main()
