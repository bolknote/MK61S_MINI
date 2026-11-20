"""Audit avoidable refusals and prepare matched next-action lessons."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import itertools
import random
from unittest.mock import patch

import bj_teacher
from ar_spec import equivalent, verify
from ay_codec import encode
from ay_common import read, rows, save_rows, sha, write
from be_language import paths3, question
from bh_common import signature
from bj_runtime import Session
from bl_spec import install
from bl_vm import CachedVM
from bs_data import worker
from ce_data import reword
from ce_wording import editorial_question
from cm_eval import after_review
from cn_data import (PREVIOUS, ROOT as PARENT, REVIEW_GROUPS, accept_teacher, ask,
                     intent, lesson, review_states, training_goals)
from cn_review_check import review_status
from full_isa_protocol import REGISTERS
from ha_protocol import canonical


ROOT = PARENT.with_name("kon-tiki-executor-refusals-v1")
SEED = 261114939
TEACHER = "http://127.0.0.1:18120/v1/chat/completions"
OPS = ("abs", "atan", "cos", "exp", "frac", "int", "ln", "log10", "neg",
       "reciprocal", "sin", "sqrt", "square")
RELATED = (("ln", "square", "reciprocal"), ("sqrt", "exp", "exp"),
           ("sign", "pow10", "neg"), ("sin", "square", "abs"),
           ("atan", "reciprocal", "square"), ("neg", "square", "neg"))


def old_tasks(split):
    parent = PARENT if split == "fresh" else PREVIOUS
    return rows(parent / f"{split}.jsonl")


def previous_refusals():
    result = []
    for split in ("development", "recovery", "closed", "fresh"):
        goals = {g["id"]: g for g in old_tasks(split)}
        path = PARENT / "review-check" / f"{split}-retry"
        assert sha(path / "full.json") == read(path / "complete.json")["full_sha256"]
        baseline = read(PARENT / "eval" / f"{split}-full-0000/full.json")
        already_refused = {r["id"] for r in baseline["records"] if r["abstained"]}
        for row in read(path / "full.json")["records"]:
            if not row["abstained"]:
                continue
            event = after_review(row)
            after = event is not None and event["kind"] == "unsure"
            goal = goals[row["task_id"]]
            generation = event["generation"] if after else {}
            if after and row["final_spec_intent"]["tested_equal"]:
                correct_spec = equivalent(row["declared_spec"], goal["spec"],
                                          goal["public_inputs"] + goal["checker_inputs"] + goal["audit_inputs"])
                assert correct_spec["tested_equal"], row["id"]
            result.append({"split": split, "id": row["id"], "task_id": row["task_id"],
                           "was_refusal": row["id"] in already_refused, "after_review": after,
                           "guard": bool(generation.get("guard_blocked")),
                           "spec_correct": row["final_spec_intent"]["tested_equal"],
                           "program_correct": row["program_correct"],
                           "independent_match": review_status({"task": goal["task"], "angle": goal["spec"]["angle"]},
                                                              row["declared_spec"]) if after else None})
    return result


def retired_states(audit, vm):
    lessons = []
    for split in ("development", "fresh"):
        identities = {r["id"] for r in audit if r["split"] == split and r["spec_correct"] and r["after_review"]}
        goals = {g["id"]: g for g in old_tasks(split)}
        run = read(PARENT / "review-check" / f"{split}-retry/full.json")
        for row in run["records"]:
            if row["id"] not in identities:
                continue
            goal = goals[row["task_id"]]
            body = goal["reference_body"] if row["initially_correct"] else goal["bad_body"]
            session = Session(goal, body, vm, "spec", row["initial_spec"], True)
            for event in row["history"]:
                if event["kind"] == "replan":
                    session.pending_replan = False
                    session.replan_attempted = True
                    session.apply_replan(event["body"])
                    break
                session.apply_action(event["kind"], event["generation"]["body"])
            good = verify(vm, session.body, goal["pool"], goal["spec"],
                          goal["public_inputs"] + goal["checker_inputs"])["status"] == "TESTED"
            action, group = ("done", "keep") if good else ("write", "repair")
            item = lesson(goal, session, group, action, [] if good else goal["spec_body"])
            assert item and item["short"] == after_review(row)["prompt"], row["id"]
            lessons.append({**item, "refusal_id": row["id"]})
    return lessons


def forms(split, group, index, rng):
    series = {"train": 48301, "validation": 67103, "closed": 80761}[split]
    value = {"constant": canonical(f"2.{series + index}")}
    register = rng.choice(REGISTERS)
    if group == "power":
        a, b = {"constant": "10"}, value
        return ["pow10", b], ["pow", b, a]
    outer, middle, inner = group
    leaf = register
    if index % 5 == 0 and inner in ("neg", "abs", "square", "pow10"):
        leaf = value
    return (["+", [outer, [middle, [inner, leaf]]], value]
            if index % 4 == 0 and inner != "pow10" else [outer, [middle, [inner, leaf]]],)


def wording(goal, index):
    spec = goal["spec"]
    expr = spec["X"]
    if goal["family"] == "power":
        base, exponent = ({"constant": "10"}, expr[1]) if expr[0] == "pow10" else expr[1:]
        left, right = base["constant"], exponent["constant"]
        text = (f"Возведи {left} в степень {right}." if index % 2 else
                f"Вычисли степень с основанием {left} и показателем {right}.")
        if spec["writes"]:
            text += f" Запиши ответ в {next(iter(spec['writes']))}."
    elif index % 7 == 0 and all("pow10" not in path for path in paths3(expr)):
        text = question(spec, ("chain", "bracket", "named")[index % 3], goal["id"])
    else:
        text = editorial_question(spec, index)
    return reword(goal, text, "co_authored")


def make_split(split, plan, old, seen, occupied):
    rng = random.Random(SEED + {"train": 1, "validation": 2, "closed": 3}[split])
    result = []
    index = 0
    for group, count in plan:
        family = "power" if group == "power" else "related" if group in RELATED else "composition"
        accepted = 0
        for _ in range(count * (24 if family in ("related", "power") else 5)):
            if accepted >= count:
                break
            index += 1
            expressions = forms(split, group, index, rng)
            expression_keys = {signature({"X": x, "writes": {}, "angle": "DEG"}) for x in expressions}
            if expression_keys & old:
                continue
            store, angle = rng.choice(REGISTERS), rng.choice(("DEG", "RAD", "GRAD"))
            group_rows = []
            for offset, expr in enumerate(expressions):
                spec = {"X": expr, "angle": angle, "writes": {store: expr} if index % 5 else {}}
                key = signature(spec)
                if key in seen:
                    break
                if family == "composition":
                    if (paths3(expr) - {group}) & occupied:
                        break
                identity = f"co:{split}:{len(result) + offset:03}"
                row = worker((spec, identity, "train" if split == "train" else "closed", family,
                              rng.randrange(2**30), "bracket",
                              ("operation", "argument", "order")[index % 3], []))
                if row is None:
                    break
                row = wording(row, index)
                group_rows.append(row)
            if len(group_rows) != len(expressions):
                continue
            for row in group_rows:
                if family == "power":
                    row["pair_id"] = f"co:{split}:power:{index}"
                seen.add(signature(row["spec"]))
                result.append(row)
            old.update(expression_keys)
            accepted += len(group_rows)
        if accepted != count:
            print({"split": split, "group": group, "wanted": count, "accepted": accepted}, flush=True)
            if family == "power":
                raise RuntimeError((split, group, count, accepted))
    return result


def prepare():
    install()
    rng = random.Random(SEED)
    audit = previous_refusals()
    save_rows(ROOT / "refusal-audit.jsonl", audit)
    print({s: Counter((r["after_review"], r["guard"], r["spec_correct"]) for r in audit if r["split"] == s)
           for s in ("development", "recovery", "closed", "fresh")}, flush=True)
    old = [*training_goals(), *(g for s in ("development", "recovery", "closed", "fresh") for g in old_tasks(s))]
    seen = {signature(g["spec"]) for g in old}
    seen_expressions = {signature({"X": g["spec"]["X"], "writes": {}, "angle": "DEG"}) for g in old}
    occupied = set().union(*(paths3(g["spec"]["X"]) for g in old))
    available = [t for t in itertools.permutations(OPS, 3) if t not in occupied and t not in RELATED]
    rng.shuffle(available)
    groups = {"train": available[:32], "validation": available[32:46], "closed": available[46:74]}
    reserved = {*occupied, *(group for split in groups.values() for group in split)}
    counts = {"train": (40, 8, 4), "validation": (24, 4, 4), "closed": (40, 8, 4)}
    splits = {}
    for split, (power, related, size) in counts.items():
        plan = [("power", power), *((t, related) for t in RELATED), *((t, size) for t in groups[split])]
        result = make_split(split, plan, seen_expressions, seen, reserved)
        assert len({intent(row) for row in result}) == len(result)
        assert len(result) >= {"train": 140, "validation": 60, "closed": 120}[split], len(result)
        splits[split] = result
        save_rows(ROOT / f"{split}.jsonl", result)
        print(split, Counter(r["family"] for r in result), flush=True)
    known = {intent(r) for r in [*old, *splits["train"]]}
    assert not known & {intent(r) for r in [*splits["validation"], *splits["closed"]]}
    assert not ({intent(r) for r in splits["validation"]} & {intent(r) for r in splits["closed"]})
    write(ROOT / "data-frozen.json", {"seed": SEED, "files": {f"{s}.jsonl": sha(ROOT / f"{s}.jsonl") for s in splits},
                                    "splits": {s: Counter(r["family"] for r in v) for s, v in splits.items()},
                                    "novel_triples": groups, "shared_remediation_motifs": RELATED})


def label():
    install()
    assert all(sha(ROOT / name) == digest for name, digest in read(ROOT / "data-frozen.json")["files"].items())
    vm = CachedVM(512)
    goals = rows(ROOT / "train.jsonl")
    old = old_tasks("development") + old_tasks("fresh")
    by_id = {g["id"]: g for g in [*goals, *old]}
    audit = rows(ROOT / "refusal-audit.jsonl")
    hard = retired_states(audit, vm)
    replay = [*hard]
    for goal in [*goals, *(by_id[x["task_id"]] for x in hard)]:
        replay.extend(r for r in review_states(goal, vm) if r is not None)
    unique = {}
    for item in replay:
        previous = unique.setdefault(item["id"], item)
        assert (previous["action"], previous["body"]) == (item["action"], item["body"]), item["id"]
    replay = list(unique.values())
    rng = random.Random(SEED)
    source = []
    for group, count in zip(REVIEW_GROUPS, (108, 65, 56, 56, 48), strict=True):
        choices = [r for r in replay if r["group"] == group and "refusal_id" not in r]
        source.extend(rng.sample(choices, min(count, len(choices))))
    rng.shuffle(source)
    source = [*hard, *source]
    assert len({r["id"] for r in source}) == len(source)
    save_rows(ROOT / "matched-lessons.jsonl", replay)
    save_rows(ROOT / "retired-refusals.jsonl", hard)
    data = []
    accepted = []
    batches = [source[i:i + 3] for i in range(0, len(source), 3)]
    with patch.multiple(bj_teacher, ROOT=ROOT, URL=TEACHER):
        client = bj_teacher.Client()
        with ThreadPoolExecutor(max_workers=8) as pool:
            for i, (batch, items) in enumerate(zip(batches, pool.map(lambda b: ask(client, b, by_id), batches), strict=True), 1):
                for state in batch:
                    answer = items.get(state["id"])
                    error = None
                    try:
                        if answer is None:
                            raise ValueError("missing teacher answer")
                        value = accept_teacher(answer, state, by_id[state["task_id"]], vm)
                        # Use the same stable SPEC serialization in both sides of a lesson.
                        accepted.append({**value, "body": state["body"]})
                    except (ValueError, KeyError, ArithmeticError, RuntimeError, SyntaxError, TypeError) as exc:
                        error = str(exc)
                    data.append({"id": state["id"], "task_id": state["task_id"], "target": state["action"],
                                 "group": state["group"], "response": answer, "rejected": error})
                if i % 5 == 0 or i == len(batches):
                    progress = {"batches": i, "total": len(batches), "verified_teacher": len(accepted)}
                    write(ROOT / "teacher-status.json", progress)
                    print(progress, flush=True)
    counts = Counter(r["group"] for r in accepted)
    assert len(accepted) >= 50 and len(counts) >= 4 and counts["repair"] >= 30, counts
    save_rows(ROOT / "teacher-lessons.jsonl", accepted)
    save_rows(ROOT / "teacher-audit.jsonl", data)
    write(ROOT / "teacher-frozen.json", {"model": bj_teacher.MODEL, "queried": len(source), "accepted": counts,
                                       "paired_states": len(replay), "retired_false_refusals": len(hard),
                                       "files": {p: sha(ROOT / p) for p in ("teacher-lessons.jsonl", "teacher-audit.jsonl",
                                                                           "matched-lessons.jsonl", "retired-refusals.jsonl")}})
    print(counts, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("prepare", "label"))
    ROOT.mkdir(exist_ok=True)
    {"prepare": prepare, "label": label}[parser.parse_args().stage]()
