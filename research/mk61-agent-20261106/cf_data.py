"""Build an independent task panel for the two short-path changes."""

import argparse
import random
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from itertools import product
from unittest.mock import patch

import bj_teacher
import ce_data
from ay_common import read, rows, save_rows, sha, write
from be_language import question
from bh_common import signature
from ce_wording import editorial_question
from full_isa_vm import build


ROOT = ce_data.ROOT.parent / "spec-short-path-authority-v1"
LITERALS = ["0.73957", "1.93957", "3.73957", "41.93957", "-0.73957"]
QUOTAS = {"steps": (30, 6), "structured": (30, 6), "freeform": (100, 20)}
SEED = 261113819


def build_asts():
    ROOT.mkdir(parents=True, exist_ok=True)
    path = ROOT / "closed-asts.jsonl"
    receipt = ROOT / "ast-frozen.json"
    if receipt.exists():
        assert sha(path) == read(receipt)["sha256"]
        return

    build()
    rng = random.Random(SEED)
    goals = []
    held = {}
    # The preceding panel is included in the signature and literal exclusion.
    with patch.object(ce_data, "ROOT", ROOT), patch.object(ce_data, "LITERALS", LITERALS):
        signatures, old_triples, prior_files = ce_data.existing_goals()
        ops = sorted(set(ce_data.NOUNS) | {"neg"})
        available = [t for t in product(ops, repeat=3) if len(set(t)) >= 2 and t not in old_triples]
        rng.shuffle(available)
        with ProcessPoolExecutor(max_workers=6) as pool:
            for cohort, (compositions, simple) in QUOTAS.items():
                prefix = f"cf:{cohort}"
                group, held[cohort] = ce_data.composition_rows(
                    pool, rng, prefix, compositions, available, signatures, old_triples,
                )
                simple_goals = ce_data.simple_rows(pool, rng, cohort, simple, signatures, old_triples)
                for goal in simple_goals:
                    goal["id"] = goal["id"].replace("ce:", "cf:", 1)
                group += simple_goals
                for index, goal in enumerate(group):
                    goal["wording_cohort"] = cohort
                    if cohort == "steps":
                        goal = ce_data.reword(goal, ce_data.step_question(goal["spec"], index), "authored_steps")
                    elif cohort == "structured":
                        style = ("bracket", "chain", "named")[index % 3]
                        text = question(goal["spec"], style, goal["id"])
                        goal = ce_data.reword(goal, text, "explicit_grammar")
                    goals.append(goal)
                print({"cohort": cohort, "tasks_ready": len(group), "total_ready": len(goals)}, flush=True)

    assert len(goals) == len({signature(g["spec"]) for g in goals}) == 256
    save_rows(path, goals)
    write(receipt, {"seed": SEED, "sha256": sha(path), "new_literals": LITERALS,
                    "prior_goal_files_checked": prior_files, "held_compositions": held,
                    "counts": dict(Counter(g["wording_cohort"] for g in goals))})


def build_wordings():
    path = ROOT / "closed-asts.jsonl"
    assert sha(path) == read(ROOT / "ast-frozen.json")["sha256"]
    receipt = ROOT / "wording-frozen.json"
    if receipt.exists():
        assert sha(ROOT / "closed.jsonl") == read(receipt)["closed_sha256"]
        return
    assert not (ROOT / "frozen.json").exists()
    goals = rows(path)
    free = [goal for goal in goals if goal["wording_cohort"] == "freeform"]
    bj_teacher.ROOT = ROOT
    bj_teacher.URL = "http://127.0.0.1:18108/v1/chat/completions"
    client = bj_teacher.Client()
    accepted = {}
    audit = []
    errors = []
    batches = [free[i:i + 4] for i in range(0, len(free), 4)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = {pool.submit(bj_teacher.chunk, client, batch): batch for batch in batches}
        for i, job in enumerate(as_completed(jobs), 1):
            batch = jobs[job]
            try:
                wordings, reviews = job.result()
            except Exception as error:
                errors.append({"ids": [goal["id"] for goal in batch], "error": repr(error)})
            else:
                audit.extend(reviews)
                for goal in batch:
                    values = wordings[goal["id"]]
                    if values:
                        accepted[goal["id"]] = values[0]["text"]
            if i % 4 == 0 or i == len(jobs):
                progress = {"batches_done": i, "total_batches": len(jobs),
                            "accepted": len(accepted), "failed_batches": len(errors)}
                write(ROOT / "wording-status.json", progress)
                print(progress, flush=True)

    final = []
    for index, goal in enumerate(goals):
        if goal["wording_cohort"] == "freeform":
            if goal["id"] in accepted:
                goal = ce_data.reword(goal, accepted[goal["id"]], "deepseek_blind_reviewed")
            else:
                goal = ce_data.reword(goal, editorial_question(goal["spec"], index), "local_editorial_templates")
        final.append(goal)
    assert len(final) == len({(g["task"], g["spec"]["angle"]) for g in final}) == 256
    save_rows(ROOT / "closed.jsonl", final)
    save_rows(ROOT / "wording-audit.jsonl", audit)
    write(receipt, {"closed_sha256": sha(ROOT / "closed.jsonl"), "audit_sha256": sha(ROOT / "wording-audit.jsonl"),
                    "wording_sources": dict(Counter(g["wording_source"] for g in final)),
                    "model": bj_teacher.MODEL, "errors": errors})


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("stage", choices=("asts", "wording"))
    if cli.parse_args().stage == "asts":
        build_asts()
    else:
        build_wordings()
