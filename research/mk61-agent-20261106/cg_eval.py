"""Measure parser changes and formula preview with an isolated yes/no scorer."""

import argparse
import time
from unittest.mock import patch

import torch

import ce_eval
import cf_eval
from ar_spec import equivalent
from ay_common import read, rows, sha, write
from bj_runtime import Session
from bl_spec import install
from bl_vm import CachedVM
from cf_language import expanded_parse
from cg_data import ROOT
from cg_language import parse_task
from cg_runtime import FormulaPreview, after_confirmation, confirmed_session


ARMS = ("full_cycle", "previous_short", "autonomous", "awaiting_confirmation", "with_confirmation")
RESULT_FILES = {arm: arm.replace("_", "-") + ".json" for arm in ARMS}


def status(phase, **data):
    value = {"phase": phase, "time": time.time(), **data}
    write(ROOT / "status.json", value)
    print(value, flush=True)


def freeze():
    assert not (ROOT / "frozen.json").exists()
    files = dict(cf_eval.check_frozen()["files"])
    wording = read(ROOT / "wording-frozen.json")
    assert sha(ROOT / "closed.jsonl") == wording["closed_sha256"]
    assert sha(ROOT / "wording-audit.jsonl") == wording["audit_sha256"]
    assert sha(ROOT / "closed-asts.jsonl") == read(ROOT / "ast-frozen.json")["sha256"]
    assert len(rows(ROOT / "closed.jsonl")) == 256
    for path in [*ce_eval.HERE.glob("cg_*.py"), *(ROOT / name for name in (
        "closed.jsonl", "closed-asts.jsonl", "ast-frozen.json", "wording-audit.jsonl", "wording-frozen.json",
    ))]:
        files[str(path.relative_to(ce_eval.REPO))] = sha(path)
    write(ROOT / "frozen.json", {
        "files": files,
        "arms": ARMS,
        "context": 1024,
        "KV": "FP32",
        "weights": "working actor and BU1500, unchanged Q4 packages",
        "optimizer_updates": 0,
        "model_outputs_on_exam_seen": False,
        "confirmation_scope": "only initial neural SPEC on tasks outside the expanded independent parser",
        "confirmation_response": "separate scorer returns yes only after matching the displayed formula on 32 audit inputs",
        "rejection": "stop pending clarification with original program",
        "approved_candidate_checks": "18 runtime inputs, original program tested before compiling",
        "approved_fallback": "full cycle anchored to the exact approved formula, original initial program",
    })


def check_frozen():
    with patch.object(ce_eval, "ROOT", ROOT):
        return ce_eval.check_frozen()


def decide(preview, goal):
    # Only the external test respondent reads the reference specification.
    # The runtime receives a boolean tied to the exact preview text.
    return bool(equivalent(preview.spec(), goal["spec"], goal["audit_inputs"])["tested_equal"])


def confirmation_arms(goals, primary, autonomous, decoder, vm):
    goals_by_id = {goal["id"]: goal for goal in goals}
    plans = {row["id"]: row for row in primary}
    waiting = []
    assisted = []
    deferred = {}
    for row in autonomous:
        goal = goals_by_id[row["task_id"]]
        plan = plans[row["task_id"]]["declared_spec"]
        preview = FormulaPreview.from_spec(plan)
        if row["route"] != "full_cycle" or row["fallback_reason"] != "unsupported_text" or preview is None:
            waiting.append(row)
            assisted.append(row)
            continue
        initial = goal["reference_body"] if row["initially_correct"] else goal["bad_body"]
        pool = goal["pool"]
        checks = goal["public_inputs"] + goal["checker_inputs"]
        message = preview.text()
        _, reason = after_confirmation(preview, None, initial, pool, checks, vm)
        pending = cf_eval.needs_confirmation(goal, row, initial, plan, reason, vm)
        waiting.append({**pending, "route": reason, "formula_preview": message, "confirmation": None})
        accepted = decide(preview, goal)
        selected, reason = after_confirmation(preview, accepted, initial, pool, checks, vm)
        if selected is not None:
            result = ce_eval.audit_short_completion(goal, row, selected, preview.spec(), reason, len(checks), vm)
            assisted.append({**result, "formula_preview": message, "confirmation": True})
        elif not accepted:
            assisted.append({**pending, "route": reason, "fallback_reason": reason,
                             "formula_preview": message, "confirmation": False})
        else:
            deferred[row["id"]] = (message, reason, goal["id"])
            assisted.append(row)

    status("confirmed_fallback", episodes=len(deferred))
    if deferred:
        needs_cycle = {value[2] for value in deferred.values()}
        installed = ce_eval.full_cycle
        with patch.object(ce_eval, "ROOT", ROOT), patch.object(installed, "Session", confirmed_session(Session)), \
             patch.object(installed, "generate", decoder), \
             patch.object(installed.core, "mutant", lambda goal, vm, kind: (goal["error_kind"], goal["bad_body"])):
            cycles = installed.episodes(None, None, [g for g in goals if g["id"] in needs_cycle], plans, vm, "self")
        resumed = {row["id"]: row for row in cycles}
        for i, row in enumerate(assisted):
            if row["id"] in deferred:
                message, reason, _ = deferred[row["id"]]
                assisted[i] = {**resumed[row["id"]], "route": "confirmed_full_cycle", "fallback_reason": reason,
                               "formula_preview": message, "confirmation": True}
    return waiting, assisted


def run():
    manifest = check_frozen()
    assert not (ROOT / "complete.json").exists()
    torch.set_num_threads(2)
    install()
    goals = rows(ROOT / "closed.jsonl")
    vm = CachedVM()
    status("initial", tasks=len(goals))
    decoder = ce_eval.Decoder()
    with patch.object(ce_eval, "ROOT", ROOT):
        primary, baseline = ce_eval.full_records(goals, vm, decoder)
    assert len(baseline) == len(goals) * 2
    write(ROOT / RESULT_FILES["full_cycle"], {"primary": primary, "records": baseline})
    status("short_paths", episodes=len(baseline))
    plans = {row["id"]: row for row in primary}
    previous = cf_eval.run_variant(goals, plans, baseline, expanded_parse, True, vm)
    autonomous = cf_eval.run_variant(goals, plans, baseline, parse_task, True, vm)
    write(ROOT / RESULT_FILES["previous_short"], {"records": previous})
    write(ROOT / RESULT_FILES["autonomous"], {"records": autonomous})
    waiting, assisted = confirmation_arms(goals, primary, autonomous, decoder, vm)
    write(ROOT / RESULT_FILES["awaiting_confirmation"], {"records": waiting})
    write(ROOT / RESULT_FILES["with_confirmation"], {"records": assisted})
    decoder.verify_weights()
    assert check_frozen() == manifest
    status("native_parity", actual_model_calls=decoder.actual_calls)
    parity = ce_eval.native_parity(decoder, primary, baseline, autonomous)
    write(ROOT / "native-verification.json", parity)
    assert check_frozen() == manifest
    write(ROOT / "complete.json", {"complete": True, "tasks": len(goals), "episodes_per_arm": len(baseline),
                                  "arms": ARMS, "actual_model_calls": decoder.actual_calls, "optimizer_updates": 0,
                                  "weights_verified": True, "native_matched": parity["matched"],
                                  "native_checked": parity["checked"]})
    status("complete", native_matched=parity["matched"], native_checked=parity["checked"])


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("stage", choices=("freeze", "run"))
    if cli.parse_args().stage == "freeze":
        freeze()
    else:
        run()
