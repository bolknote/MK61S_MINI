#!/usr/bin/env python3
"""Check teacher final answers and earlier context replies before supervising both."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from grade import grade
from generate_large import BEHAVIORS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", default="large-raw")
    parser.add_argument("--output", default="teacher-audit")
    parser.add_argument("--count", type=int, default=100)
    args = parser.parse_args()
    groups = {"final": [], "context": []}
    for path in sorted(Path(args.raw).glob('*.json')):
        raw = json.loads(path.read_text())
        description = raw["request"]["messages"][-1]["content"]
        kind = next(k for k, value in BEHAVIORS.items() if description.startswith("Behavior: " + value))
        examples = json.loads(raw["response"]["choices"][0]["message"]["content"])["examples"]
        for index, row in enumerate(examples):
            if len(row["context"]) not in (0, 2, 4):continue
            turns = [re.sub(r"^(?:user|bot|assistant|tinytalk)\s*:\s*", "", re.sub(r"\s+", " ", t).strip().replace("\u2019", "'"), flags=re.I)
                     for t in row["context"] + [row["user"], row["answer"]]]
            messages = [{"role": "user" if i % 2 == 0 else "assistant", "content": text} for i, text in enumerate(turns[:-1])]
            identity = f"{path.stem}:{index}"
            groups["final"].append({"id": identity, "messages": messages, "intent": BEHAVIORS[kind], "reply": turns[-1]})
            for at in range(1, len(messages), 2):
                groups["context"].append({"id": f"{identity}:prior{at}", "messages": messages[:at],
                                          "intent": "Respond relevantly and actually fulfill the user's request.", "reply": messages[at]["content"]})
    output = Path(args.output);output.mkdir(parents=True, exist_ok=True)
    report = {"source_batches": len(list(Path(args.raw).glob('*.json'))), "method": "Stable sample of teacher supervision, not held-out student evaluation"}
    for group, rows in groups.items():
        rows.sort(key=lambda row: hashlib.sha256(("teacher-audit:" + row["id"]).encode()).hexdigest())
        rows = rows[:args.count]
        report[group] = {"grades": grade(rows, [row["reply"] for row in rows], output / "grade-cache"), "examples": rows}
        print(group, report[group]["grades"]["pass_rate"], flush=True)
    (output / "audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
