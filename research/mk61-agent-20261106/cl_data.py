"""Prepare composition holdouts and the retired Kon-Tiki recovery examples."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch

import bj_teacher
import ck_data
from ay_common import read, rows, save_rows, sha, write
from ce_data import reword


PREVIOUS = ck_data.ROOT
ROOT = PREVIOUS.parent / "kon-tiki-composition-recovery-v1"
PARENT = PREVIOUS / "checkpoints/012727"
LITERALS = {
    "train": ("0.74261", "1.74261", "4.74261", "12.74261", "-0.74261", "-2.296875"),
    "development": ("0.50821", "1.50821", "4.50821", "39.50821", "-0.50821"),
    "closed": ("0.57361", "1.57361", "3.57361", "37.57361", "-0.57361"),
}


def asts():
    counts = {**ck_data.COUNTS, "train": (32, 4, 8)}
    with patch.multiple(ck_data, ROOT=ROOT, LITERALS=LITERALS, COUNTS=counts):
        ck_data.build_asts()


def audited_file(split, name):
    path = PREVIOUS / "eval" / f"{split}-012727"
    assert sha(path / (name + ".json")) == read(path / "complete.json")[name + "_sha256"]
    return read(path / (name + ".json"))


def recovery_targets():
    previous = read(PREVIOUS / "comparison.json")
    lost = previous["fixed_hour_endpoint"]["retention"]["full_changes"]["repairs"]["lost"]
    assert len(lost) == 3
    retention = {r["id"]: r for r in rows(PREVIOUS / "retention.jsonl")}
    failed_repairs = [r for r in audited_file("retention", "full")["records"] if r["id"] in lost]
    targets = [retention[r["task_id"]] for r in failed_repairs]
    assert len(targets) == 3
    closed = {g["id"]: g for g in rows(PREVIOUS / "closed.jsonl")}
    first = audited_file("closed", "full")["primary"]
    failed = [closed[r["id"]] for r in first if not r["program_correct"] and closed[r["id"]]["family"] == "composition"]
    positives = [closed[r["id"]] for r in first if r["program_correct"]]
    return targets, lost, failed, positives


def augment():
    targets, _, failed, _ = recovery_targets()
    data = [{**g, "split": "train"} for g in [*targets, *failed]]
    ROOT.mkdir(parents=True, exist_ok=True)
    bj_teacher.ROOT = ROOT
    bj_teacher.URL = "http://127.0.0.1:18133/v1/chat/completions"
    client = bj_teacher.Client()
    groups = [data[i:i + 4] for i in range(0, len(data), 4)]
    output, audit, failures = [], [], []
    with ThreadPoolExecutor(8) as executor:
        jobs = {executor.submit(bj_teacher.chunk, client, group): group for group in groups}
        for index, job in enumerate(as_completed(jobs), 1):
            try:
                matches, records = job.result()
            except Exception as error:
                failures.append({"ids": [g["id"] for g in jobs[job]], "error": repr(error)[:400]})
            else:
                audit.extend(records)
                for goal in jobs[job]:
                    for variant, entry in enumerate(matches[goal["id"]]):
                        try:
                            row = reword(goal, entry["text"], "deepseek_blind_reviewed")
                        except (ValueError, ArithmeticError):
                            continue
                        row.update(id=f"cl:teacher:{goal['id']}:{variant}", source_id=goal["id"])
                        output.append(row)
            if index % 4 == 0 or index == len(jobs):
                print({"batches": index, "total": len(jobs), "variants": len(output)}, flush=True)
    output.sort(key=lambda g: g["id"])
    save_rows(ROOT / "reworded.jsonl", output)
    save_rows(ROOT / "teacher-audit.jsonl", sorted(audit, key=lambda r: (r["id"], r.get("attempt", 0), r["text"])))
    write(ROOT / "teacher-frozen.json", {"model": bj_teacher.MODEL, "variants": len(output), "failures": failures,
                                        "sha256": sha(ROOT / "reworded.jsonl"), "closed_queries": 0})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("asts", "augment"))
    {"asts": asts, "augment": augment}[parser.parse_args().stage]()
