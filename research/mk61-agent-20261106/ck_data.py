"""Disjoint MK-61 composition families and arithmetic minimal pairs."""

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from decimal import Decimal
from difflib import SequenceMatcher
from itertools import product
import json
import random
from unittest.mock import patch

import bj_teacher
import ce_data
from ar_spec import equivalent
from ay_codec import compile_spec, encode
from ay_common import read, rows, save_rows, sha, write
from az_data import numbers
from az_teacher import pool_for
from be_language import paths3, question
from bh_common import signature
from bs_data import worker
from ce_wording import editorial_question
from full_isa_math import UNARY
from full_isa_protocol import REGISTERS
from full_isa_vm import build


ROOT = ce_data.ROOT.parent / "kon-tiki-paired-compositions-v1"
SOURCE = ROOT.parent / "spec-formula-clarification-v1"
LITERALS = {
    "train": ("0.46371", "1.96371", "4.46371", "12.96371", "-0.46371", "-3.78125"),
    "development": ("0.42163", "1.92163", "4.42163", "41.92163", "-0.42163"),
    "closed": ("0.53786", "1.53786", "3.53786", "37.53786", "-0.53786"),
}
COUNTS = {"development": (16, 4, 4), "closed": (32, 5, 12), "train": (64, 4, 32)}
PAIR_KINDS = ("operator", "order", "argument", "power")
TRAIN_PAIR_KINDS = (*PAIR_KINDS, "repeat", "sign")
GROUPS = (("asin", "sin"), ("atan", "tan"), ("ln", "log10"), ("sqrt", "square"),
          ("abs", "neg"), ("int", "frac"), ("cos", "sin"), ("exp", "pow10"))


def pair_expressions(kind, rng, literals, index):
    leaf = {"constant": rng.choice(literals)} if index % 4 == 0 else rng.choice(REGISTERS)
    if kind == "operator":
        a, b = rng.choice(GROUPS)
        return [a, leaf], [b, leaf]
    if kind == "order":
        a, b = rng.sample(list(UNARY), 2)
        return [a, [b, leaf]], [b, [a, leaf]]
    if kind == "argument":
        op = rng.choice(("-", "/", "pow"))
        other = rng.choice(REGISTERS) if isinstance(leaf, dict) else {"constant": rng.choice(literals)}
        return [op, leaf, other], [op, other, leaf]
    if kind == "power":
        return ["pow10", leaf], ["pow", leaf, {"constant": "10"}]
    if kind == "repeat":
        op = rng.choice(["square", "sqrt", "cos", "sin", "atan", "ln", "reciprocal"])
        return [op, leaf], [op, [op, leaf]]
    assert kind == "sign"
    base = [rng.choice(["sin", "cos", "ln", "sqrt", "exp", "reciprocal"]), leaf]
    return ["sign", base], ["neg", base]


def build_jobs(rng, split, family, group, specs, seen, excluded):
    result = []
    for index, spec in enumerate(specs):
        key = signature(spec)
        if key in seen or paths3(spec["X"]) & excluded:
            return []
        seen.add(key)
        result.append((spec, f"ck:{split}:{group}:{index:02}", split, family, rng.randrange(2**31),
                       "bracket", rng.choice(("operation", "argument", "order")), sorted(excluded) if split == "train" else []))
    return result


def compositions(executor, rng, split, families, size, available, seen, excluded, occupied):
    accepted = []
    used = []
    attempts = 0
    while len(used) < families:
        if not available:
            raise RuntimeError(f"Insufficient composition families for {split}")
        outer, middle, inner = triple = available.pop()
        if triple in occupied:
            continue
        jobs = []
        for variant in range(16):
            expr = [outer, [middle, [inner, rng.choice(REGISTERS)]]]
            if variant % 2:
                expr = [rng.choice(("+", "-", "*")), expr, {"constant": rng.choice(LITERALS[split])}]
            jobs.extend(build_jobs(rng, split, "composition", f"composition:{attempts:03}:{variant:02}",
                                  [ce_data.make_spec(expr, rng)], seen, excluded))
        attempts += 1
        valid = [item for item in executor.map(worker, jobs) if item is not None]
        if len(valid) < size:
            continue
        accepted.extend(valid[:size])
        used.append(triple)
        occupied.update(path for row in valid[:size] for path in paths3(row["spec"]["X"]))
        if len(used) % 16 == 0:
            print({"split": split, "composition_families": len(used), "goals": len(accepted)}, flush=True)
    return accepted, used


def pairs(executor, rng, split, count, seen, excluded):
    accepted = []
    kinds = TRAIN_PAIR_KINDS if split == "train" else PAIR_KINDS
    for kind in kinds:
        done = 0
        for batch in range(50):
            jobs = []
            for index in range(12):
                index += 12 * batch
                a, b = pair_expressions(kind, rng, LITERALS[split], index)
                left = ce_data.make_spec(a, rng)
                right = {**left, "X": b, "writes": {r: b for r in left["writes"]}}
                jobs.extend(build_jobs(rng, split, kind, f"pair:{kind}:{index:04}", (left, right), seen, excluded))
            # Each generated job pair stays adjacent through parallel ROM validation.
            values = list(executor.map(worker, jobs))
            for left, right in zip(values[::2], values[1::2], strict=True):
                if left is None or right is None:
                    continue
                bank = left["checker_inputs"] + right["checker_inputs"]
                if not any(equivalent(left["spec"], right["spec"], [x])["reason"] == "COUNTEREXAMPLE" for x in bank):
                    continue
                group = left["id"].rsplit(":", 1)[0]
                accepted.extend({**goal, "contrast_id": group, "contrast_side": side}
                                for side, goal in enumerate((left, right)))
                done += 1
                if done == count:
                    break
            if done == count:
                break
        if done != count:
            raise RuntimeError((split, kind, count, done))
        print({"split": split, "pair_kind": kind, "pairs": done}, flush=True)
    return accepted


def protected_history():
    goals = {g["id"]: g for g in rows(SOURCE / "closed.jsonl")}
    history = read(SOURCE / "full-cycle.json")["records"]
    chosen = [goals[r["task_id"]] for r in history if r["pass"] and not r["initially_correct"]]
    random.Random(261114551).shuffle(chosen)
    return chosen[:48]


def build_asts():
    ROOT.mkdir(parents=True, exist_ok=True)
    build()
    with patch.object(ce_data, "ROOT", ROOT), patch.object(ce_data, "LITERALS", [*LITERALS["development"], *LITERALS["closed"]]):
        seen, occupied, old_files = ce_data.existing_goals()
    rng = random.Random(261114539)
    available = [t for t in product(UNARY, repeat=3) if len(set(t)) >= 2 and t not in occupied]
    rng.shuffle(available)
    holdout = set()
    used = {}
    with ProcessPoolExecutor(7) as executor:
        for split, (families, variants, pair_count) in COUNTS.items():
            print({"stage": "AST", "split": split}, flush=True)
            fresh, used[split] = compositions(executor, rng, split, families, variants, available, seen, holdout, occupied)
            fresh += pairs(executor, rng, split, pair_count, seen, holdout)
            save_rows(ROOT / f"{split}-asts.jsonl", fresh)
            holdout.update(path for goal in fresh for path in paths3(goal["spec"]["X"]))
    save_rows(ROOT / "retention.jsonl", protected_history())
    files = [f"{split}-asts.jsonl" for split in COUNTS] + ["retention.jsonl"]
    write(ROOT / "ast-frozen.json", {"files": {name: sha(ROOT / name) for name in files},
                                     "composition_families": used, "previous_jsonl_scanned": old_files})


def local_pair(goal, index):
    spec = goal["spec"]
    if goal["family"] != "power":
        return editorial_question(spec, index)
    expr = spec["X"]
    base, power = ({"constant": "10"}, expr[1]) if expr[0] == "pow10" else expr[1:]
    display = lambda value: value if isinstance(value, str) else value["constant"]
    text = f"Возведи {display(base)} в степень {display(power)}."
    if spec["writes"]:
        text += f" Запиши ответ в {next(iter(spec['writes']))}."
    return text


def teacher_pairs(client, batch):
    shape = bj_teacher.schema({key: {"type": "string"} for key in ("id", "a", "b")})
    system = (
        "Сформулируй две почти одинаковые короткие задачи для МК-61 из каждой пары деревьев. "
        "Пусть изменится только смысловое различие между a и b. Пиши обычным русским языком, "
        "сохраняй порядок операций, адрес регистра, все числа и явно заданную запись store. "
        "Пустой store означает результат в X и сохранение памяти. Никаких формул, английских функций или ответов. "
        "Углы уже настроены. Числа пиши цифрами с точкой. int означает целую часть к нулю, frac дробную часть, "
        "sign означает возврат знака, neg означает смену знака. Для pow10 назови 10 основанием. "
        "Каждая задача самодостаточна. Верни JSON items с id, a и b."
    )
    source = [{"id": str(i), "a": a["spec"]["X"], "b": b["spec"]["X"],
               "store": next(iter(a["spec"]["writes"]), ""), "angle": a["spec"]["angle"]} for i, (a, b) in enumerate(batch)]
    proposed = {item.get("id"): item for item in client.call(system, source, shape, "ck_pairs")}
    candidates = [[], []]
    for index, pair in enumerate(batch):
        item = proposed.get(str(index), {})
        texts = [(item.get(key) or "").strip() for key in ("a", "b")]
        if not all(texts) or texts[0] == texts[1] or SequenceMatcher(None, *texts, autojunk=False).ratio() < 0.52:
            continue
        for side, (goal, text) in enumerate(zip(pair, texts, strict=True)):
            candidates[side].append({"id": goal["id"], "goal": goal, "text": text})
    valid = []
    audit = []
    for side in candidates:
        verdicts = bj_teacher.reviewed(client, side) if side else {}
        accepted = {}
        for item in side:
            report = verdicts.get(item["id"])
            ok = bj_teacher.acceptable(item, report)
            audit.append({"id": item["id"], "text": item["text"], "review": report, "accepted": ok})
            if ok:
                accepted[item["id"]] = item["text"]
        valid.append(accepted)
    return {key: value for a, b in batch if a["id"] in valid[0] and b["id"] in valid[1]
            for key, value in ((a["id"], valid[0][a["id"]]), (b["id"], valid[1][b["id"]]))}, audit


def teacher_compositions(client, batch):
    found, audit = bj_teacher.chunk(client, batch)
    return {key: entries[0]["text"] for key, entries in found.items() if entries}, audit


def pair_layout(left, right):
    base = pool_for("")
    pool = base + sorted((set(left["pool"]) | set(right["pool"])) - set(base), key=Decimal)
    for row in (left, right):
        row.update(pool=pool, reference_body=compile_spec(row["spec"], pool), spec_body=encode(row["spec"], pool),
                   bad_body=compile_spec(row["bad_spec"], pool), bad_spec_body=encode(row["bad_spec"], pool))


def wording(goals, edits, split):
    worded = []
    pair_rows = defaultdict(list)
    for row in goals:
        if "contrast_id" in row:
            pair_rows[row["contrast_id"]].append(row)
    for index, row in enumerate(goals):
        pairs_ = pair_rows.get(row.get("contrast_id"))
        if pairs_ and row["contrast_side"] == 1:
            continue
        group = pairs_ or [row]
        use_teacher = all(g["id"] in edits for g in group)
        labelled = []
        for goal in group:
            if use_teacher:
                text, source = edits[goal["id"]], "deepseek_blind_reviewed"
            elif pairs_:
                text, source = local_pair(goal, index), "authored_pair"
            elif split != "train" and index % 5 == 0:
                text, source = question(goal["spec"], ("bracket", "chain", "named")[(index // 5) % 3], goal["id"]), "explicit_grammar"
            else:
                text, source = editorial_question(goal["spec"], index), "local_editorial_templates"
            fresh = ce_data.reword(goal, text, source)
            fresh["wording_cohort"] = "structured" if source == "explicit_grammar" else "freeform"
            labelled.append(fresh)
        if pairs_ and split == "train":
            pair_layout(*labelled)
        worded.extend(labelled)
    assert len(worded) == len(goals)
    return worded


def build_wording():
    frozen = read(ROOT / "ast-frozen.json")
    for name, digest in frozen["files"].items():
        assert sha(ROOT / name) == digest, name
    bj_teacher.ROOT = ROOT
    bj_teacher.URL = "http://127.0.0.1:18132/v1/chat/completions"
    train = rows(ROOT / "train-asts.jsonl")
    contrast = [g for g in train if "contrast_id" in g]
    pair_groups = list(zip(contrast[::2], contrast[1::2], strict=True))
    assert all(a["contrast_id"] == b["contrast_id"] and (a["contrast_side"], b["contrast_side"]) == (0, 1)
               for a, b in pair_groups)
    comp = [g for g in train if "contrast_id" not in g]
    client = bj_teacher.Client()
    edits, audit, failures = {}, [], []
    groups = [(teacher_pairs, pair_groups[i:i + 4]) for i in range(0, len(pair_groups), 4)]
    groups += [(teacher_compositions, comp[i:i + 4]) for i in range(0, len(comp), 4)]
    with ThreadPoolExecutor(10) as pool:
        jobs = {pool.submit(run, client, batch): index for index, (run, batch) in enumerate(groups)}
        for index, job in enumerate(as_completed(jobs), 1):
            try:
                values, checks = job.result()
            except Exception as error:
                failures.append({"batch": jobs[job], "error": repr(error)[:500]})
            else:
                edits.update(values)
                audit.extend(checks)
            if index % 8 == 0 or index == len(jobs):
                progress = {"checked_batches": index, "total": len(jobs), "accepted": len(edits), "failed": len(failures)}
                write(ROOT / "teacher-status.json", progress)
                print(progress, flush=True)
    train = wording(train, edits, "train")
    counts = Counter(g["wording_source"] for g in train)
    reviewed_pairs = sum(g["wording_source"] == "deepseek_blind_reviewed" and "contrast_id" in g for g in train) // 2
    reviewed_comp = sum(g["wording_source"] == "deepseek_blind_reviewed" and "contrast_id" not in g for g in train)
    assert reviewed_pairs >= 48 and reviewed_comp >= 96, (reviewed_pairs, reviewed_comp, failures)
    final = {"train": train, **{split: wording(rows(ROOT / f"{split}-asts.jsonl"), {}, split)
                                 for split in ("development", "closed")}}
    for split, items in final.items():
        assert len(items) == len({(g["spec"]["angle"], g["task"]) for g in items}), split
        save_rows(ROOT / (split + ".jsonl"), items)
    save_rows(ROOT / "teacher-audit.jsonl", sorted(audit, key=lambda item: (item["id"], item.get("attempt", -1), item["text"])))
    write(ROOT / "wording-frozen.json", {"model": bj_teacher.MODEL, "train_wordings": counts,
                                         "reviewed_pairs": reviewed_pairs, "reviewed_compositions": reviewed_comp,
                                         "closed_teacher_queries": 0, "failures": failures,
                                         "files": {n: sha(ROOT / n) for n in [*(s + ".jsonl" for s in final), "teacher-audit.jsonl"]}})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("asts", "wording"))
    if parser.parse_args().stage == "asts":
        build_asts()
    else:
        build_wording()
