"""Snapshot provenance and split whole game families before any augmentation."""
from __future__ import annotations

import argparse
import collections
import csv
import difflib
import hashlib
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent


def digest(text: str | bytes) -> str:
    return hashlib.sha256(text.encode() if isinstance(text, str) else text).hexdigest()


def write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def write_jsonl(path: Path, rows):
    with path.open("w") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("/Users/bolk/Projects/MK-61"))
    parser.add_argument("--output", type=Path, default=HERE.parents[1] / ".build/mk61-agent-20261106/corpus")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader((args.source / "games/manifest.tsv").open(), delimiter="\t"))
    result = subprocess.run(["node", str(HERE / "export_catalog.cjs"), str(args.source)],
                            input=json.dumps(rows), text=True, capture_output=True, check=True)
    rows = json.loads(result.stdout)
    parent = list(range(len(rows)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        a, b = find(a), find(b)
        parent[max(a, b)] = min(a, b)

    by_key = {}
    for i, row in enumerate(rows):
        row["listing_sha256"] = digest(row["listing"])
        row["description_sha256"] = digest(row["description_text"])
        title = re.sub(r"\([^)]*\)|\d+|\b[ivx]+\b", "", row["title"].lower())
        title = re.sub(r"[^\w]+", " ", title).strip()
        keys = [("title", title)]
        if row["series"]:
            keys.append(("series", row["series"]))
        if row["parse_status"] == "ok":
            keys.append(("code", digest(bytes(row["bytes"]))))
        for key in keys:
            if key in by_key:
                union(i, by_key[key])
            else:
                by_key[key] = i
    similar_pairs = 0
    for i, row in enumerate(rows):
        if row["parse_status"] != "ok" or len(row["bytes"]) < 20:
            continue
        for j in range(i):
            other = rows[j]
            if find(i) == find(j) or other["parse_status"] != "ok" or len(other["bytes"]) < 20:
                continue
            a, b = row["bytes"], other["bytes"]
            if min(len(a), len(b)) / max(len(a), len(b)) < .82:
                continue
            matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
            if matcher.quick_ratio() >= .85 and matcher.ratio() >= .85:
                union(i, j)
                similar_pairs += 1
    families = collections.defaultdict(list)
    for i, row in enumerate(rows):
        families[find(i)].append(row["program"])
    for i, row in enumerate(rows):
        family = digest("\n".join(sorted(families[find(i)])))[:16]
        bucket = int(digest("mk61-agent-family-v1:" + family)[:8], 16) % 10
        row["family"] = family
        row["split"] = "test" if bucket == 0 else "validation" if bucket == 1 else "train"
        row["usable_for_code"] = row["parse_status"] == "ok" and len(row["bytes"]) <= 105
    for split in ["train", "validation", "test"]:
        write_jsonl(args.output / f"games-{split}.jsonl", (r for r in rows if r["split"] == split))

    # General instruction material only. Audits and game walkthroughs are excluded
    # because they can contain solutions to held-out games. Full book OCR needs
    # a separate provenance-aware audit before becoming training data.
    names = ["01-programming.md", "03-command-reference.md", "04-programming-cookbook.md",
             "07-flowcharts.md", "08-numerical-errors.md", "09-debugging-and-service.md"]
    documents = []
    for name in names:
        path = args.source / "docs" / name
        text = path.read_text()
        documents.append({"source": str(path.relative_to(args.source)), "sha256": digest(text),
                          "text": text, "split": "train", "kind": "general_reference"})
    write_jsonl(args.output / "references-train.jsonl", documents)
    books = [{"path": str(p.relative_to(args.source)), "bytes": p.stat().st_size,
              "sha256": digest(p.read_bytes()), "training_use": "not_ingested"}
             for p in sorted((args.source / "docs/reference").rglob("*.pdf"))]
    write_json(args.output / "books-inventory.json", books)
    report = {"source_root": str(args.source), "manifest_sha256": digest((args.source / "games/manifest.tsv").read_bytes()),
              "entries": len(rows), "games": sum(r["kind"] == "game" for r in rows),
              "families": len(families), "near_duplicate_unions": similar_pairs,
              "parse_status": dict(collections.Counter(r["parse_status"] for r in rows)),
              "splits": {s: {"entries": sum(r["split"] == s for r in rows),
                             "families": len({r["family"] for r in rows if r["split"] == s}),
                             "usable_programs": sum(r["split"] == s and r["usable_for_code"] for r in rows)}
                         for s in ["train", "validation", "test"]},
              "reference_documents": len(documents), "reference_bytes": sum(len(r["text"].encode()) for r in documents),
              "books_inventoried": len(books), "full_book_text_used": False,
              "rejected": [{"program": r["program"], "error": r.get("parse_error")} for r in rows if r["parse_status"] != "ok"],
              "split_rule": "Union series, normalized titles, exact code, and >=85% byte-sequence similarity; hash entire components before augmentation",
              "held_out_game_descriptions_used_in_training": False}
    write_json(args.output / "manifest.json", report)
    print(json.dumps({**report, "rejected": report["rejected"][:8]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
