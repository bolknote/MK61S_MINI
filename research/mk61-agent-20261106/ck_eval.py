"""Paired Q4 replay with the unchanged Kon-Tiki actor and current SPEC checks."""

import argparse
from collections import Counter, defaultdict
import time
from unittest.mock import patch

import torch

import ce_eval
import cf_eval
import cg_eval
from ay_common import read, rows, sha, write
from bl_spec import install
from bl_vm import CachedVM
from ce_finish import measures, token_summary
from cg_language import parse_task
from ci_eval import clarify, choice_from_auditor
from ci_runtime import preserve_power_alias
from ck_data import ROOT
from ck_train import CURRENT, REPO


def status(folder, phase, **data):
    event = {"phase": phase, "unix": time.time(), **data}
    write(folder / "status.json", event)
    print(folder.name, event, flush=True)


def check_exam():
    from ci_eval import check_frozen
    check_frozen()
    manifest = read(ROOT / "exam-frozen.json")
    for path, digest in manifest["files"].items():
        assert sha(REPO / path) == digest, path
    return manifest


def model_path(step):
    if step == 0:
        return CURRENT / "translator" / "model.mkqb"
    path = ROOT / "checkpoints" / f"{step:06}" / "model.mkqb"
    assert sha(path) == read(path.parent / "manifest.json")["Q4_sha256"]
    return path


def decoder_for(step):
    if step == 0:
        return ce_eval.Decoder()
    from lowbit import load as load_packet
    original = ce_eval.load

    def load_translator(path, device):
        model, tokenizer = original(path, device)
        if path == CURRENT / "translator":
            load_packet(model, model_path(step))
        return model, tokenizer

    with patch.object(ce_eval, "load", load_translator):
        return ce_eval.Decoder()


def check_trajectory(goals, full, primary):
    assert [g["id"] for g in goals] == [r["id"] for r in primary]
    expected = [(g["id"], correct, f"{g['id']}:{'correct' if correct else g['error_kind']}")
                for g in goals for correct in (True, False)]
    assert expected == [(r["task_id"], r["initially_correct"], r["id"]) for r in full]


def metric(goals, primary, full, confirmed, assisted):
    check_trajectory(goals, full, primary)
    by_task = {g["id"]: g for g in goals}
    init = {r["id"]: r["generation"] for r in primary}
    pairs = defaultdict(list)
    for row in primary:
        contrast_id = by_task[row["id"]].get("contrast_id")
        if contrast_id is not None:
            pairs[contrast_id].append(bool(row["program_correct"]))
    assert all(len(x) == 2 for x in pairs.values())
    questions = [r for r in confirmed if type(r.get("confirmation")) is bool]
    clarifications = [r for r in assisted if r.get("clarification_asked") is True]
    unknown = [r for r in confirmed if r["route"] == "needs_confirmation"]
    asked = {r["id"] for r in [*questions, *clarifications, *unknown]}
    successful = [r for r in assisted if r["pass"]]
    first = {"tested": len(primary), "correct": sum(r["program_correct"] for r in primary),
             "composition_tested": sum(by_task[r["id"]]["family"] == "composition" for r in primary),
             "composition_correct": sum(r["program_correct"] and by_task[r["id"]]["family"] == "composition" for r in primary),
             "pairs_tested": len(pairs), "pairs_both_correct": sum(all(x) for x in pairs.values())}
    return {"first": first, "full_cycle": measures(full), "assisted": measures(assisted),
            "confirmations": len(questions), "tasks_with_confirmation": len({r["task_id"] for r in questions}),
            "rejected_formulas": sum(r["confirmation"] is False for r in questions),
            "clarifications": len(clarifications), "tasks_with_clarification": len({r["task_id"] for r in clarifications}),
            "blocked_known_parse_disagreement_or_check": len(unknown),
            "completed_without_user": sum(r["id"] not in asked for r in successful),
            "tokens": token_summary(assisted, init), "routes": dict(Counter(r["route"] for r in assisted))}


def evaluate(split, step, threads):
    torch.set_num_threads(threads)
    install()
    manifest = check_exam()
    if step != 0:
        assert read(ROOT / "training.json")["optimizer_updates"] >= step
    if split == "closed":
        selection = read(ROOT / "preselected.json")
        assert step in {0, selection["candidate_step"]}
    path = ROOT / (split + ".jsonl")
    goals = rows(path)
    folder = ROOT / "eval" / f"{split}-{step:06}"
    fingerprint = {"split": split, "step": step, "dataset_sha256": sha(path),
                   "translator_sha256": sha(model_path(step)), "actor_sha256": sha(CURRENT / "working/model.mkqb")}
    if (folder / "complete.json").exists():
        assert read(folder / "complete.json")["inputs"] == fingerprint
        return
    folder.mkdir(parents=True, exist_ok=True)
    vm = CachedVM()
    decoder = decoder_for(step)
    started = time.monotonic()
    full_path = folder / "full.json"
    with patch.object(ce_eval, "ROOT", folder), patch.object(cg_eval, "ROOT", folder):
        if full_path.exists():
            previous = read(full_path)
            assert previous["inputs"] == fingerprint
            primary, full = previous["primary"], previous["records"]
        else:
            status(folder, "initial", tasks=len(goals))
            primary, full = ce_eval.full_records(goals, vm, decoder)
            write(full_path, {"inputs": fingerprint, "primary": primary, "records": full})
        check_trajectory(goals, full, primary)
        status(folder, "independent_check", episodes=len(full))
        plans = {r["id"]: r for r in primary}
        with patch.object(cf_eval, "checked_program", preserve_power_alias):
            automatic = cf_eval.run_variant(goals, plans, full, parse_task, True, vm)
        _, confirmed = cg_eval.confirmation_arms(goals, primary, automatic, decoder, vm)
        rejected = [r for r in confirmed if r.get("confirmation") is False]
        chosen, attempts = clarify(goals, rejected, vm, answer=choice_from_auditor)
        assisted = [chosen.get(r["id"], r) for r in confirmed]
    decoder.verify_weights()
    assert check_exam() == manifest
    result = metric(goals, primary, full, confirmed, assisted)
    write(folder / "assisted.json", {"records": assisted, "attempts": attempts})
    write(folder / "metrics.json", result)
    write(folder / "complete.json", {"inputs": fingerprint, "seconds": time.monotonic() - started, "weights_verified": True,
                                     "full_sha256": sha(full_path), "metrics_sha256": sha(folder / "metrics.json"),
                                     "assisted_sha256": sha(folder / "assisted.json")})
    status(folder, "complete", first=result["first"], assisted=result["assisted"], clarifications=result["clarifications"])


def select():
    training = read(ROOT / "training.json")
    baseline = read(ROOT / "eval/development-000000/metrics.json")
    old = read(ROOT / "eval/retention-000000/metrics.json")
    assert old["full_cycle"]["repairs"] == 48
    candidates = []
    for relative in training["checkpoints"]:
        step = read(ROOT / relative / "manifest.json")["step"]
        dev = read(ROOT / "eval" / f"development-{step:06}" / "metrics.json")
        retention = read(ROOT / "eval" / f"retention-{step:06}" / "metrics.json")
        protected = (retention["full_cycle"]["repairs"] == 48
                     and dev["assisted"]["accepted_false_DONE"] <= baseline["assisted"]["accepted_false_DONE"]
                     and dev["assisted"]["corruption"] <= baseline["assisted"]["corruption"]
                     and dev["assisted"]["repairs"] >= baseline["assisted"]["repairs"])
        key = [protected, dev["first"]["correct"], dev["first"]["pairs_both_correct"],
               retention["full_cycle"]["repairs"], dev["assisted"]["completed"],
               -(dev["confirmations"] + dev["clarifications"]), -step]
        candidates.append({"step": step, "key": key, "protected": protected, "development": dev["first"],
                           "retention_repairs": retention["full_cycle"]["repairs"]})
    candidate = max(candidates, key=lambda row: row["key"])
    selected = candidate["protected"] and candidate["development"]["correct"] > baseline["first"]["correct"]
    result = {"candidate_step": candidate["step"], "recommendation_before_test": candidate["step"] if selected else 0,
              "development_baseline": baseline["first"], "retention_baseline": old["full_cycle"]["repairs"],
              "candidates": candidates, "closed_used_for_selection": False}
    write(ROOT / "preselected.json", result)
    print(result, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("split", choices=("development", "closed", "retention", "select"))
    parser.add_argument("--step", type=int, default=0)
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    if args.split == "select":
        select()
    else:
        evaluate(args.split, args.step, args.threads)
