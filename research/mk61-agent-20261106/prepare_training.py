"""Build corpus continuation and verified Russian plan/action/observation examples."""
from __future__ import annotations

import collections
import hashlib
import json
from pathlib import Path
import random
import re
import time

from emulator import Emulator
from harness import check_program, feedback, initial_prompt, trace_feedback
from tasks import BUILD, make_generated, program_text, save_jsonl

SOURCE = Path("/Users/bolk/Projects/MK-61")


def normalize(text):
    text = re.sub(r"(?m)^# /Users/.*$|--- COLUMN \d+ ---", "", text)
    text = re.sub(r"([а-яА-ЯёЁ])-\n([а-яё])", r"\1\2", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def prepare_books():
    root = SOURCE / "output/research/nzdr-2026-10-28/extracted"
    heldout = [json.loads(line) for line in (BUILD / "corpus/games-test.jsonl").read_text().splitlines()]
    heldout += [json.loads(line) for line in (BUILD / "corpus/games-validation.jsonl").read_text().splitlines()]
    titles = [r["title"].lower().strip() for r in heldout if len(r["title"].strip()) >= 7]
    books, excluded = [], collections.Counter()
    for directory in sorted(root.iterdir()):
        if not directory.is_dir(): continue
        native = directory / "native-text.txt"
        if native.exists() and len(native.read_text().strip()) > 10000:
            chunks = re.split(r"\f|\n\s*\n", native.read_text())
            sources = [(str(native), index + 1, chunk) for index, chunk in enumerate(chunks)]
        else:
            sources = [(str(path), int(re.search(r"page-(\d+)", path.name)[1]), path.read_text())
                       for path in sorted((directory / "pages").glob("*.vision.txt"))]
        for source, page, text in sources:
            text = normalize(text)
            # Keep instructional material. Complete game chapters can duplicate
            # the held-out games. Mixed-model opcode tables are not MK-61 labels.
            if re.search(r"\bигр\w*|\bБейсик\b|МК[- ]?85|TI[- ]?59|HP[- ]?41|БК[- ]?0010", text, re.I):
                excluded["game_or_foreign_machine"] += 1; continue
            if any(title in text.lower() for title in titles):
                excluded["heldout_title"] += 1; continue
            if not re.search(r"программ|регистр|стек|цикл|алгоритм|обратн\w* польск", text, re.I):
                excluded["off_topic"] += 1; continue
            if len(text) < 180 or len(re.findall(r"[а-яА-ЯёЁ]", text)) / len(text) < .45:
                excluded["short_or_table"] += 1; continue
            # Numeric tables and broken OCR lines are retained as source data
            # outside training; they are never used as trusted program answers.
            lines = [line.strip() for line in text.splitlines() if len(line.strip()) >= 20 and
                     len(re.findall(r"[а-яА-ЯёЁ]", line)) / max(1, len(line)) >= .45]
            cleaned = " ".join(lines)
            if len(cleaned) < 180: continue
            books.append({"book": directory.name, "source": source, "page_or_paragraph": page,
                          "source_sha256": hashlib.sha256(text.encode()).hexdigest(),
                          "text": cleaned, "split": "train", "use": "instructional_prose_only"})
    save_jsonl(BUILD / "training/books-train.jsonl", books)
    return books, dict(excluded)


def answer_for(task, *, diagnosis=None):
    plan = task["reference_plan"]
    if diagnosis:
        plan = diagnosis + "; " + plan
    return "<plan>" + plan + "</plan><write>" + program_text(task["reference_code"]) + "</write><run/>"


def main():
    out = BUILD / "training"
    out.mkdir(parents=True, exist_ok=True)
    if (out / "manifest.json").exists():
        raise SystemExit("Training snapshot exists; use a new version for a new dataset")
    rng = random.Random(61065)
    emulator = Emulator()
    books, excluded = prepare_books()
    documents = []
    for row in books:
        documents.append({"id": "book:" + row["book"] + ":" + str(row["page_or_paragraph"]),
                          "source": row["source"], "kind": "book_prose",
                          "text": "Учебный материал о микрокалькуляторах.\n" + row["text"]})
    for line in (BUILD / "corpus/games-train.jsonl").read_text().splitlines():
        row = json.loads(line)
        if not row["usable_for_code"]: continue
        documents.append({"id": "game:" + row["program"], "source": row["program"], "family": row["family"],
                          "kind": "historical_game", "text": "Исторический листинг МК-61.\n" + row["description_text"][:6500] +
                          "\nБайты программы HEX:\n" + program_text(row["bytes"])})
    for line in (BUILD / "corpus/references-train.jsonl").read_text().splitlines():
        row = json.loads(line)
        documents.append({"id": "reference:" + row["source"], "source": row["source"], "kind": "reference", "text": row["text"]})
    save_jsonl(out / "domain-documents.jsonl", documents)
    tasks = make_generated("train", 14000, seed=61064)
    rows = []
    started = time.monotonic()
    for index, task in enumerate(tasks):
        reference = check_program(emulator, task["reference_code"], task["public_tests"] + task["hidden_tests"][:1])
        if not reference["pass"]:
            raise ValueError(f"Independent reference check failed: {task['id']}")
        examples = bool(index % 2)
        common = {"family": task["family"], "source": "verified_expression_generator", "split": "train"}
        rows.append({**common, "kind": task["kind"], "prompt": initial_prompt(task, examples=examples), "answer": answer_for(task)})
        if task.get("initial_code"):
            checked = check_program(emulator, task["initial_code"], task["public_tests"])
            observation = feedback(checked)
            if not checked["pass"]:
                first_diff = next(i for i, (a, b) in enumerate(zip(task["initial_code"], task["reference_code"])) if a != b)
                diagnosis = f"исправить команду {first_diff:02d}: нужен код {task['reference_code'][first_diff]:02X}"
                rows.append({**common, "kind": "repair_after_failure",
                             "prompt": initial_prompt(task, examples=examples, observation=observation),
                             "answer": answer_for(task, diagnosis=diagnosis)})
                trace = trace_feedback(emulator, task["initial_code"], task["public_tests"][0])
                rows.append({**common, "kind": "trace_call", "prompt": initial_prompt(task, examples=examples),
                             "answer": "<plan>проверить текущий код пошагово</plan><trace/>"})
                rows.append({**common, "kind": "repair_after_trace",
                             "prompt": initial_prompt(task, examples=examples, observation=trace),
                             "answer": answer_for(task, diagnosis=diagnosis)})
        if index % 4 == 0:
            successful = {**task, "initial_code": task["reference_code"]}
            rows.append({**common, "kind": "finish_after_pass",
                         "prompt": initial_prompt(successful, examples=examples, observation="PASS"), "answer": "<done/>"})
        if (index + 1) % 2000 == 0:
            print(json.dumps({"tasks_checked": index + 1, "sft_examples": len(rows)}), flush=True)
    rng.shuffle(rows)
    save_jsonl(out / "sft-train.jsonl", rows)
    manifest = {"tasks": len(tasks), "sft_rows": len(rows), "sft_kinds": dict(collections.Counter(row["kind"] for row in rows)),
                "domain_documents": len(documents), "domain_kinds": dict(collections.Counter(row["kind"] for row in documents)),
                "book_ids": sorted({row["book"] for row in books}), "book_units": len(books),
                "book_exclusions": excluded, "seconds": time.monotonic() - started,
                "independent_reference_checks": "Every generated task, both public inputs and one hidden input, real production microcode core",
                "teacher_observations_are_loss_targets": False,
                "full_ocr_program_tables_used_as_verified_answers": False,
                "files": {name: hashlib.sha256((out / name).read_bytes()).hexdigest()
                          for name in ["domain-documents.jsonl", "books-train.jsonl", "sft-train.jsonl"]}}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
