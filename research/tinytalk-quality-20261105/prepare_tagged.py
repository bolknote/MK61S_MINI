#!/usr/bin/env python3
"""Prepare learned intent tags and vetted targets; no external intent rule runs at inference."""
import argparse
from collections import Counter
import json
from pathlib import Path

from annotate_intents import INTENTS
from common import core, load_model, quantize
from rebalance import compact_tokenizer

WORDS = {"greet": "hello", "identify": "bot", "thanks": "thanks", "goodbye": "bye", "ask_question": "question",
         "suggest": "idea", "positive": "happy", "negative": "sorry", "tired": "tired", "sharing": "interesting",
         "preference": "like", "clarify": "mean", "play": "game", "story": "story", "remember_user": "name",
         "remember_other": "pet", "correction": "correct", "followup": "more", "alternative": "else", "chat": "chat"}
WORDS['play_move'] = 'turn'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--source-data", required=True)
    parser.add_argument("--annotations", required=True)
    parser.add_argument("--output-model", required=True)
    parser.add_argument("--output-data", required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--seed", type=int, default=87120)
    args = parser.parse_args()
    import torch
    output_model = Path(args.output_model);output_data = Path(args.output_data)
    assert not output_model.exists() and not output_data.exists()
    annotations_root = Path(args.annotations)
    annotation_manifest = json.loads((annotations_root / "manifest.json").read_text())
    source_path = Path(args.source_data) / "train.jsonl"
    assert core.digest(source_path) == annotation_manifest["source_sha256"]
    labels = {row["id"]: row for row in core.read_rows(annotations_root / "labels.jsonl")}
    model, tokenizer, device = load_model(args)
    old_vocab = len(tokenizer)
    anchors = {kind: tokenizer.encode(" " + WORDS[kind], add_special_tokens=False) for kind in INTENTS}
    tags = [f"<|tt_intent:{kind}|>" for kind in INTENTS]
    added = tokenizer.add_special_tokens({"additional_special_tokens": tags})
    assert added == len(INTENTS)
    model.resize_token_embeddings(len(tokenizer), mean_resizing=False)
    ids = {kind: tokenizer.convert_tokens_to_ids(tag) for kind, tag in zip(INTENTS, tags)}
    with torch.no_grad():
        for kind, index in ids.items():
            assert all(token < old_vocab for token in anchors[kind])
            model.transformer.wte.weight[index].copy_(model.transformer.wte.weight[anchors[kind]].mean(0))
    assert model.lm_head.weight is model.transformer.wte.weight
    model.config.tinytalk_intent_token_ids = ids
    model.config.tinytalk_intent_behavior = "Predict one learned act tag, then answer; hide special tokens in displayed text; render plain history between turns"
    output_model.mkdir(parents=True)
    model.save_pretrained(output_model, safe_serialization=True);tokenizer.save_pretrained(output_model);quantize.copy_notices(args.model, output_model)
    table = compact_tokenizer(tokenizer, output_model / "tokenizer.ttbpe")
    output_data.mkdir(parents=True)
    rows = [];rejected = [];counts = Counter()
    for row in core.read_rows(source_path):
        row = dict(row)
        if row["kind"] == "replay":kind = "chat"
        else:
            label = labels[row["id"]]
            if not label["ok"]:
                rejected.append(row["id"]);continue
            kind = label["intent"]
            row["base_kind"] = row["kind"];row["kind"] = kind
        row["plain_target"] = row["target"]
        row["target"] = f"<|tt_intent:{kind}|> " + row["target"]
        row["intent_label"] = kind
        counts[row["kind"]] += 1;rows.append(row)
    path = output_data / "train.jsonl"
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    manifest = {"policy": "Teacher-vetted training targets; learned 20-way act prefix; plain stored dialogue history; 5% replay sampling",
                "source_train_sha256": core.digest(source_path), "annotation": annotation_manifest,
                "rows": len(rows), "rejected": len(rejected), "kinds": dict(counts), "sha256": core.digest(path),
                "intent_token_ids": ids, "compact_tokenizer_bytes": table["file_bytes"], "reserved_test_opened": False}
    core.save(output_data / "manifest.json", manifest);core.save(output_data / "rejected.json", rejected)
    core.save(output_model / "tokenizer-table.json", table)
    print(json.dumps(manifest), flush=True)


if __name__ == "__main__":
    main()
