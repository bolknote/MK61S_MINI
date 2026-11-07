#!/usr/bin/env python3
"""One final, reserved conversation comparison using actual packed Q4 files."""
import argparse
import json
from pathlib import Path

from train_chat import core, decode, nll, quantize
from judge import compare


def run(args):
    import torch
    root = Path(args.output)
    cases = core.read_rows(Path(args.suite) / "test.jsonl")
    references = core.read_rows(Path(args.data) / "test.jsonl")
    report = {"preselected_arm": json.loads(Path("preselected.json").read_text()),
              "suite_sha256": core.digest(Path(args.suite) / "test.jsonl"),
              "method": "Reserved authored prompts, actual TTQ4 file restore, blind Qwen pairwise assessment",
              "settings": vars(args), "models": {}}
    variants = [("original", args.model, None), ("qat", "qat/best", "qat/model.ttq4"),
                ("staged", "staged/best", "staged/model.ttq4")]
    rollout_users = [
        ["I could use some quiet company tonight.", "I've started sketching a cat, but it looks funny.", "Maybe I'll give it a silly hat. What do you think?"],
        ["I like calm music when I read.", "I don't like loud songs much.", "What else could make a quiet evening nice?"],
        ["Hi, I'm Lena. It's nice to meet you.", "I have a new cat called Pebble.", "Do you remember my cat's name?"],
    ]
    baseline = None
    for label, directory, packed in variants:
        model, tokenizer, device = core.load(args, directory)
        model.eval().requires_grad_(False)
        if packed:
            metadata = quantize.restore(model, packed)
        else:
            metadata = quantize.roundtrip(model)
        replies = {mode: decode(model, tokenizer, cases, device, temp) for mode, temp in [("greedy", 0), ("sampled", 0.7)]}
        encoded, skipped = core.encode_rows(tokenizer, references, 256)
        language = {kind: nll(model, [r for r in encoded if r[2] == kind][:128], tokenizer, device) for kind in ["soda", "teacher"]}
        diagnostics = {mode: {"bad": sum(row["bad"] for row in values),
                              "unique_replies": len({row["reply"].lower() for row in values}),
                              "ended_with_eos": sum(row["ended_with_eos"] for row in values)} for mode, values in replies.items()}
        rollouts = []
        for index, users in enumerate(rollout_users):
            messages = []
            for turn, text in enumerate(users):
                messages.append({"role": "user", "content": text})
                case = {"id": f"rollout:{index}:{turn}", "messages": messages}
                reply = decode(model, tokenizer, [case], device)[0]["reply"]
                messages.append({"role": "assistant", "content": reply})
            rollouts.append(messages)
        item = {"checkpoint_sha256": core.digest(Path(directory) / "model.safetensors"),
                "packed_sha256": core.digest(packed) if packed else None, "quantization": metadata,
                "replies": replies, "q4_test_nll": language, "diagnostics": diagnostics,
                "rollouts": rollouts, "test_reference_rows_skipped": skipped}
        if baseline is None:
            baseline = replies
        else:
            item["judgments"] = {mode: compare(cases, baseline[mode], replies[mode], root.parent / "test-judge-cache", f"test-{mode}") for mode in replies}
        report["models"][label] = item
        core.save(root, report)
        print(json.dumps({"model": label, "diagnostics": diagnostics, "q4_test_nll": language,
                          "judgments": {mode: value["counts"] for mode, value in item.get("judgments", {}).items()}}), flush=True)
        del model
        if device == "cuda":
            torch.cuda.empty_cache()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="model")
    parser.add_argument("--suite", default="suite")
    parser.add_argument("--data", default="data")
    parser.add_argument("--output", default="evaluation.json")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--seed", type=int, default=27631)
    run(parser.parse_args())
