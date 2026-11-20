"""Compare one confirmation with one retry on a paired, freshly frozen Q4 panel."""

import argparse
import time
from unittest.mock import patch

import torch

import ce_eval
import cf_eval
import cg_eval
from aq_protocol import prompt_ids
from ar_spec import equivalent
from ay_common import read, rows, sha, write
from bj_runtime import Session
from bl_spec import install
from bl_vm import CachedVM
from cg_language import parse_task
from cg_runtime import FormulaPreview, after_confirmation, confirmed_session
from ch_data import ROOT
from ch_runtime import retry_after_refusal


ARMS = ("full_cycle", "autonomous", "one_confirmation", "ordinary_retry", "refusal_retry")
RESULT_FILES = {arm: arm.replace("_", "-") + ".json" for arm in ARMS}


def status(phase, **data):
    value = {"phase": phase, "time": time.time(), **data}
    write(ROOT / "status.json", value)
    print(value, flush=True)


def freeze():
    assert not (ROOT / "frozen.json").exists()
    files = dict(cg_eval.check_frozen()["files"])
    wording = read(ROOT / "wording-frozen.json")
    assert sha(ROOT / "closed.jsonl") == wording["closed_sha256"]
    assert sha(ROOT / "wording-audit.jsonl") == wording["audit_sha256"]
    assert sha(ROOT / "closed-asts.jsonl") == read(ROOT / "ast-frozen.json")["sha256"]
    assert len(rows(ROOT / "closed.jsonl")) == 256
    for path in [*ce_eval.HERE.glob("ch_*.py"), *(ROOT / name for name in (
        "closed.jsonl", "closed-asts.jsonl", "ast-frozen.json", "wording-audit.jsonl", "wording-frozen.json",
    ))]:
        files[str(path.relative_to(ce_eval.REPO))] = sha(path)
    write(ROOT / "frozen.json", {
        "files": files,
        "arms": ARMS,
        "context": 1024,
        "KV": "FP32",
        "optimizer_updates": 0,
        "first_prompt_and_models": "same BU1500 and working Q4 actor as formula confirmation",
        "retry_budget": 1,
        "second_response": "same oracle-simulated yes/no reviewer, frozen before any generation on this panel",
        "retry_inputs": "original question, angle and pool, plus an instruction; no code or corrected expression",
        "retry_commit": "explicit second approval of the exact preview, then original code or verified replacement",
        "closed_model_generations_seen": False,
    })


def check_frozen():
    with patch.object(ce_eval, "ROOT", ROOT):
        return ce_eval.check_frozen()


def same_task_retries(goals, primary, rejected, decoder, vm, *, mention_refusal):
    by_id = {goal["id"]: goal for goal in goals}
    plans = {row["id"]: row for row in primary}
    retries = {}

    def generate(prompt):
        return decoder(None, None, [prompt], forced_action="write")[0]

    for row in rejected:
        if row["task_id"] in retries:
            continue
        goal = by_id[row["task_id"]]
        old = FormulaPreview.from_spec(plans[goal["id"]]["declared_spec"])
        assert old is not None and old.text() == row["formula_preview"] and row["confirmation"] is False
        retries[goal["id"]] = retry_after_refusal(goal["task"], goal["spec"]["angle"], goal["pool"], old, False,
                                                 generate, mention_refusal=mention_refusal)

    # A rewording of the same rejected formula need not prompt the user again.
    duplicate = set()
    for task, retry in retries.items():
        if retry.preview is None:
            continue
        goal = by_id[task]
        checks = goal["public_inputs"] + goal["checker_inputs"]
        if equivalent(retry.preview.spec(), plans[task]["declared_spec"], checks)["tested_equal"]:
            duplicate.add(task)
    verdicts = {task: cg_eval.decide(value.preview, by_id[task])
                for task, value in retries.items() if value.preview and task not in duplicate}

    result = {}
    fallback = {}
    for row in rejected:
        task = row["task_id"]
        goal = by_id[task]
        retry = retries[task]
        initial = goal["reference_body"] if row["initially_correct"] else goal["bad_body"]
        assert row["body"] == initial and not row["finished"]
        pool, checks = goal["pool"], goal["public_inputs"] + goal["checker_inputs"]
        reason = "same_formula_on_checks" if task in duplicate else retry.reason
        attempt = {"kind": "retry_translation", "prompt": retry.prompt, "generation": retry.generation, "result": reason}
        retry_fields = {"retry_status": reason, "retry_preview": None, "retry_confirmation": None}
        if retry.preview is None or task in duplicate:
            result[row["id"]] = {**row, **retry_fields, "history": [*row["history"], attempt]}
            continue

        accepted = verdicts[task]
        retry_fields.update(retry_preview=retry.preview.text(), retry_confirmation=accepted,
                            retry_status="approved" if accepted else "rejected")
        answered = {"kind": "retry_confirmation", "accepted": accepted}
        prefix = [*row["history"], attempt, answered]
        selected, reason = after_confirmation(retry.preview, accepted, initial, pool, checks, vm)
        if selected is not None:
            audit = ce_eval.audit_short_completion(goal, row, selected, retry.preview.spec(), reason, len(checks), vm)
            result[row["id"]] = {**row, **audit, **retry_fields, "route": f"retry_{reason}", "history": [*prefix, *audit["history"]]}
        else:
            result[row["id"]] = {**row, **retry_fields, "history": prefix}
            if accepted:
                fallback[row["id"]] = task

    if fallback:
        fallback_tasks = set(fallback.values())
        selected = [g for g in goals if g["id"] in fallback_tasks]
        retry_plans = {task: {"declared_spec": retries[task].preview.spec()} for task in fallback_tasks}
        installed = ce_eval.full_cycle
        with patch.object(installed, "Session", confirmed_session(Session)), \
             patch.object(installed, "generate", decoder), \
             patch.object(installed.core, "mutant", lambda goal, vm, kind: (goal["error_kind"], goal["bad_body"])):
            cycles = installed.episodes(None, None, selected, retry_plans, vm, "self")
        for cycle in cycles:
            identity = cycle["id"]
            if identity not in fallback:
                continue
            row = result[identity]
            result[identity] = {**row, **cycle, "initial_spec": row["initial_spec"], "route": "retry_full_cycle",
                                "history": [*row["history"], *cycle["history"]]}
    return result, {task: {"prompt": retry.prompt, "generation": retry.generation, "decode_status": retry.reason,
                          "duplicate_on_checks": task in duplicate,
                          "offered": retry.preview is not None and task not in duplicate}
                    for task, retry in retries.items()}


def run():
    manifest = check_frozen()
    assert not (ROOT / "complete.json").exists()
    torch.set_num_threads(2)
    install()
    goals = rows(ROOT / "closed.jsonl")
    vm = CachedVM()
    decoder = ce_eval.Decoder()
    status("initial", tasks=len(goals))
    with patch.object(ce_eval, "ROOT", ROOT), patch.object(cg_eval, "ROOT", ROOT):
        primary, full = ce_eval.full_records(goals, vm, decoder)
        assert len(full) == 2 * len(goals)
        write(ROOT / RESULT_FILES["full_cycle"], {"primary": primary, "records": full})
        status("autonomous", episodes=len(full))
        plans = {row["id"]: row for row in primary}
        autonomous = cf_eval.run_variant(goals, plans, full, parse_task, True, vm)
        write(ROOT / RESULT_FILES["autonomous"], {"records": autonomous})
        _, one = cg_eval.confirmation_arms(goals, primary, autonomous, decoder, vm)
        write(ROOT / RESULT_FILES["one_confirmation"], {"records": one})
        rejected = [row for row in one if row.get("confirmation") is False]
        for arm, mention in (("ordinary_retry", False), ("refusal_retry", True)):
            status("retry", arm=arm, refused_episodes=len(rejected))
            results, attempts = same_task_retries(goals, primary, rejected, decoder, vm, mention_refusal=mention)
            write(ROOT / RESULT_FILES[arm], {"records": [results.get(row["id"], row) for row in one], "attempts": attempts})

    decoder.verify_weights()
    assert check_frozen() == manifest
    status("native_parity", actual_model_calls=decoder.actual_calls)
    parity = ce_eval.native_parity(decoder, primary, full, autonomous)
    import ay_native as native
    native.ARMS = ["working", "translator"]
    engine = native.Engine(ce_eval.PREVIOUS / "server-results", arm="translator")
    retry_probes = []
    for arm in ("ordinary_retry", "refusal_retry"):
        for trial in list(read(ROOT / RESULT_FILES[arm])["attempts"].values())[:6]:
            output = engine.generate(trial["prompt"], "write")
            same = output["generated_token_ids"] == trial["generation"]["generated_token_ids"]
            retry_probes.append({"arm": arm, "output_equal": same,
                                 "input_equal": output.get("input_token_ids") == prompt_ids(decoder.tokenizers["translator"], trial["prompt"])})
    parity["retry_probes"] = retry_probes
    parity["retry_checked"] = len(retry_probes)
    parity["retry_matched"] = sum(p["input_equal"] and p["output_equal"] for p in retry_probes)
    write(ROOT / "native-verification.json", parity)
    assert check_frozen() == manifest
    write(ROOT / "complete.json", {"complete": True, "tasks": len(goals), "episodes_per_arm": len(full),
                                  "arms": ARMS, "actual_model_calls": decoder.actual_calls, "optimizer_updates": 0,
                                  "weights_verified": True, "native_matched": parity["matched"], "native_checked": parity["checked"]})
    status("complete", native_matched=parity["matched"], native_checked=parity["checked"])


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("stage", choices=("freeze", "run"))
    if cli.parse_args().stage == "freeze":
        freeze()
    else:
        run()
