#!/usr/bin/env python3
"""Prepare natural dialogue replay and merge dialogue-level teacher splits."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


def key(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def write(path, rows):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    return {"rows": len(rows), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def rows_for(turns, source, identity):
    rows = []
    for end in range(1, len(turns), 2):
        start = max(0, end - 5)
        messages = [{"role": "user" if i % 2 == 0 else "assistant", "content": turns[i]}
                    for i in range(start, end)]
        rows.append({"id": f"{identity}:{end}", "kind": source, "messages": messages, "target": turns[end]})
    return rows


def soda(args):
    import pyarrow.parquet as pq
    root = Path(args.output); root.mkdir(parents=True, exist_ok=True)
    partitions = [[], [], []]
    rejected = Counter(); accepted = 0
    names = "Alex Ben Clara David Emma Finn Grace Henry Iris Jack Kate Leo Mia Noah Olive Paul Rose Sam Tessa Will".split()
    generic = {"friend", "man", "woman", "mother", "father", "son", "daughter", "person", "customer", "teacher", "wife", "husband", "boss", "brother", "sister"}
    human_claim = re.compile(r"\b(?:my (?:wife|husband|son|daughter|children|boss|job|school)|i (?:went|bought|live|work|was born)|i'm (?:a lawyer|a doctor|a teacher|\d)|i am (?:a lawyer|a doctor|a teacher|\d))\b", re.I)
    off_topic = re.compile(r"\b(?:mortgage|lawsuit|cocaine|heroin|murder|suicide|chemotherapy|cancer|measles|contract|stock market)\b", re.I)
    reader = pq.ParquetFile(args.parquet)
    for batch in reader.iter_batches(batch_size=2048, columns=["dialogue", "speakers", "original_index"]):
        for row in batch.to_pylist():
            turns, speakers = row["dialogue"], row["speakers"]
            if len(turns) < 4 or len(turns) != len(speakers) or len(set(speakers)) != 2:
                rejected["speakers"] += 1; continue
            if any(speaker != speakers[i % 2] for i, speaker in enumerate(speakers)):
                rejected["alternation"] += 1; continue
            identity = key(["soda-v2", int(row["original_index"])])
            bucket = int(identity[:8], 16) % 100
            split = 1 if bucket < 3 else 2 if bucket < 6 else 0
            if len(partitions[split]) >= ([24000, 800, 800][split]):
                continue
            cleaned = []
            for text in turns:
                text = re.sub(r"\s+", " ", text.strip().strip('"')).replace("\u2019", "'")
                for index, speaker in enumerate(speakers[:2]):
                    if speaker.lower() not in generic and len(speaker) >= 3:
                        replacement = names[int(identity[8:12], 16) % len(names)] if index == 0 else "TinyTalk"
                        text = re.sub(r"(?<!\w)" + re.escape(speaker) + r"(?!\w)", replacement, text)
                cleaned.append(text)
            # Keep a complete, short window; never truncate part of an utterance.
            window = None
            for start in range(0, len(cleaned) - 3, 2):
                candidate = cleaned[start:start + 6]
                if len(candidate) % 2:
                    candidate = candidate[:-1]
                if any(not t or len(t.split()) > 24 or len(t) > 160 for t in candidate):
                    continue
                if len(" ".join(candidate)) > 650 or off_topic.search(" ".join(candidate)):
                    continue
                if any(human_claim.search(t) for t in candidate[1::2]):
                    continue
                if any(marker in " ".join(candidate).lower() for marker in ["<|", "user:", "bot:"]):
                    continue
                words = re.findall(r"[A-Za-z]+", " ".join(candidate))
                if not words or sum(map(len, words)) / len(words) > 5.2:
                    continue
                window = candidate; break
            if window is None:
                rejected["length_or_complexity"] += 1; continue
            partitions[split].extend(rows_for(window, "soda", identity))
            accepted += 1
        if all(len(rows) >= limit for rows, limit in zip(partitions, [24000, 800, 800])):
            break
    manifest = {"source": "allenai/soda", "source_sha256": hashlib.sha256(Path(args.parquet).read_bytes()).hexdigest(),
                "accepted_dialogues": accepted, "rejected": dict(rejected),
                "policy": "Strict two-speaker alternation, short complete turns, dialogue-level split, simple language, obvious human job/family claims filtered"}
    for name, rows in zip(["train", "validation", "test"], partitions):
        manifest[name] = write(root / f"soda-{name}.jsonl", rows)
    (root / "soda-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2), flush=True)


def merge(args):
    root = Path(args.output)
    partitions = [[] for _ in range(3)]
    for i, name in enumerate(["train", "validation", "test"]):
        partitions[i] = [json.loads(line) for line in (root / f"soda-{name}.jsonl").read_text().splitlines()]
    for line in Path(args.teacher).read_text().splitlines():
        row = json.loads(line)
        bucket = int(row["id"][:8], 16) % 100
        split = 1 if bucket < 5 else 2 if bucket < 10 else 0
        partitions[split].extend(rows_for(row["turns"], "teacher", row["id"]))
    # A small amount of stable role/identity training; no arithmetic or fact-recall drills.
    questions = ["What should I call you?", "Who am I chatting with?", "Tell me your name.",
                 "Do you have a name?", "Are you a person?", "What are you?", "Who are you?",
                 "Could you introduce yourself?", "Hello, who is this?", "What is your name?"]
    for index, question in enumerate(questions):
        partitions[0].append({"id": f"identity:{index}", "kind": "identity",
                              "messages": [{"role": "user", "content": question}],
                              "target": "I'm TinyTalk, a little chat bot. What would you like to talk about?" if index % 2 else "I'm TinyTalk, a friendly chat bot."})
    seen, manifest = set(), {"policy": "All windows of each source dialogue stay in one split; exact context duplicates removed across splits",
                             "sampling_probabilities": {"teacher": 0.65, "soda": 0.33, "identity": 0.02},
                             "arithmetic_or_recall_drills": False}
    for name, rows in zip(["train", "validation", "test"], partitions):
        unique = []
        for row in rows:
            fingerprint = key(row["messages"])
            if fingerprint in seen:
                continue
            seen.add(fingerprint); unique.append(row)
        manifest[name] = write(root / f"{name}.jsonl", unique)
        manifest[name]["kinds"] = dict(Counter(row["kind"] for row in unique))
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["soda", "merge"])
    parser.add_argument("--parquet")
    parser.add_argument("--teacher")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    {"soda": soda, "merge": merge}[args.mode](args)
