"""Compare targeted clarification and one neural retry on the same Q4 outputs."""

import argparse
from collections import defaultdict
from dataclasses import asdict
import time
from unittest.mock import patch

import torch

import ce_eval
import cf_eval
import cg_eval
import ch_eval
from aq_protocol import prompt_ids
from ay_common import read, rows, sha, write
from bl_spec import install
from bl_vm import CachedVM
from cg_language import parse_task
from cg_runtime import FormulaPreview, after_confirmation
from ci_data import ROOT
from ci_runtime import collect_edits, preserve_power_alias, question_text, select_preview


ARMS = ("full_cycle", "prior_confirmation", "canonical_confirmation", "ordinary_retry", "clarification")
RESULT_FILES = {arm: arm.replace("_", "-") + ".json" for arm in ARMS}


def status(phase, **data):
    value = {"phase": phase, "time": time.time(), **data}
    write(ROOT / "status.json", value)
    print(value, flush=True)


def check_frozen():
    with patch.object(ce_eval, "ROOT", ROOT):
        return ce_eval.check_frozen()


def freeze():
    assert not (ROOT / "frozen.json").exists()
    files = dict(ch_eval.check_frozen()["files"])
    wording = read(ROOT / "wording-frozen.json")
    assert sha(ROOT / "closed.jsonl") == wording["closed_sha256"]
    assert sha(ROOT / "wording-audit.jsonl") == wording["audit_sha256"]
    assert sha(ROOT / "closed-asts.jsonl") == read(ROOT / "ast-frozen.json")["sha256"]
    goals = rows(ROOT / "closed.jsonl")
    assert len(goals) == len({goal["id"] for goal in goals}) == 256
    for path in [*ce_eval.HERE.glob("ci_*.py"), *(ROOT / n for n in (
        "closed.jsonl", "closed-asts.jsonl", "ast-frozen.json", "wording-audit.jsonl", "wording-frozen.json",
    ))]:
        files[str(path.relative_to(ce_eval.REPO))] = sha(path)
    write(ROOT / "frozen.json", {
        "files": files, "arms": ARMS, "context": 1024, "KV": "FP32", "optimizer_updates": 0,
        "power_alias": "structural normalization of base 10 power after current code passes all 18 working checks",
        "user_respondent": "separate audit compares each displayed SPEC on 32 held-out inputs and returns yes/no or option index",
        "clarification": "at most three single changes, ranked using only original task and rejected formula",
        "clarification_budget": "one additional question after first explicit refusal, no extra neural request",
        "retry_budget": "one ordinary neural retry and at most one additional confirmation question",
        "commit": "only selected preview after checking against the current program or a freshly compiled program",
        "closed_model_generations_seen": False,
    })


def choice_from_auditor(options, goal):
    # This separate test respondent supplies only the selected option number.
    return next((i for i, edit in enumerate(options, 1) if cg_eval.decide(edit.preview, goal)), 0)


def clarify(goals, rejected, vm, *, answer):
    by_id = {goal["id"]: goal for goal in goals}
    groups = defaultdict(list)
    for row in rejected:
        if row.get("confirmation") is not False or row["finished"]:
            raise ValueError("A clarification requires a refused preview")
        groups[row["task_id"]].append(row)
    result = {}
    attempts = {}
    for task, episodes in groups.items():
        goal = by_id[task]
        refused = FormulaPreview.from_spec(episodes[0]["initial_spec"])
        assert refused is not None
        pool = goal["pool"]
        options = collect_edits(goal["task"], refused, pool)
        chosen = answer(options, goal) if options else None
        selected = select_preview(options, chosen)
        attempted = bool(options)
        attempts[task] = {
            "task": goal["task"], "refused_preview": refused.text(),
            "question": question_text(refused, options) if attempted else None,
            "options": [asdict(edit) for edit in options], "selected": chosen,
        }
        for row in episodes:
            initial = goal["reference_body"] if row["initially_correct"] else goal["bad_body"]
            assert row["body"] == initial and row["formula_preview"] == refused.text()
            checks = goal["public_inputs"] + goal["checker_inputs"]
            verified = None
            reason = "no_options" if not attempted else "awaiting_choice" if chosen is None else "none_selected"
            if selected is not None:
                verified, reason = after_confirmation(selected, True, initial, pool, checks, vm)
            event = {"kind": "targeted_clarification", "asked": attempted, "selected": chosen, "result": reason}
            history = [*row["history"], event]
            outcome = row
            if verified is not None:
                audit = ce_eval.audit_short_completion(goal, row, verified, selected.spec(), reason, len(checks), vm)
                outcome = {**row, **audit, "route": f"clarified_{reason}"}
                history.extend(audit["history"])
            result[row["id"]] = {**outcome, "history": history, "clarification_asked": attempted,
                                 "clarification_choice": chosen, "clarification_status": reason}
    return result, attempts


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
        write(ROOT / RESULT_FILES["full_cycle"], {"primary": primary, "records": full})
        plans = {row["id"]: row for row in primary}
        status("previous_confirmation", episodes=len(full))
        prior_autonomous = cf_eval.run_variant(goals, plans, full, parse_task, True, vm)
        _, prior = cg_eval.confirmation_arms(goals, primary, prior_autonomous, decoder, vm)
        write(ROOT / RESULT_FILES["prior_confirmation"], {"records": prior})
        status("power_alias", episodes=len(full))
        with patch.object(cf_eval, "checked_program", preserve_power_alias):
            autonomous = cf_eval.run_variant(goals, plans, full, parse_task, True, vm)
        _, base = cg_eval.confirmation_arms(goals, primary, autonomous, decoder, vm)
        write(ROOT / RESULT_FILES["canonical_confirmation"], {"records": base})
        rejected = [row for row in base if row.get("confirmation") is False]
        status("ordinary_retry", refused_episodes=len(rejected))
        retry, retry_attempts = ch_eval.same_task_retries(goals, primary, rejected, decoder, vm, mention_refusal=False)
        write(ROOT / RESULT_FILES["ordinary_retry"], {"records": [retry.get(r["id"], r) for r in base], "attempts": retry_attempts})
        status("targeted_clarification", refused_episodes=len(rejected))
        choice, choice_attempts = clarify(goals, rejected, vm, answer=choice_from_auditor)
        write(ROOT / RESULT_FILES["clarification"], {"records": [choice.get(r["id"], r) for r in base], "attempts": choice_attempts})

    decoder.verify_weights()
    assert check_frozen() == manifest
    status("native_parity", actual_model_calls=decoder.actual_calls)
    parity = ce_eval.native_parity(decoder, primary, full, autonomous)
    import ay_native as native
    native.ARMS = ["working", "translator"]
    engine = native.Engine(ce_eval.PREVIOUS / "server-results", arm="translator")
    retries = list(retry_attempts.values())[:6]
    matched = 0
    for trial in retries:
        prompt = trial["prompt"]
        output = engine.generate(prompt, "write")
        matched += (output["generated_token_ids"] == trial["generation"]["generated_token_ids"] and
                    output.get("input_token_ids") == prompt_ids(decoder.tokenizers["translator"], prompt))
    parity.update(retry_checked=len(retries), retry_matched=matched)
    write(ROOT / "native-verification.json", parity)
    assert check_frozen() == manifest
    write(ROOT / "complete.json", {
        "complete": True, "tasks": len(goals), "episodes_per_arm": len(full), "arms": ARMS,
        "actual_model_calls": decoder.actual_calls, "optimizer_updates": 0, "weights_verified": True,
        "native_matched": parity["matched"] + matched, "native_checked": parity["checked"] + len(retries),
    })
    status("complete", checked=parity["checked"] + len(retries), matched=parity["matched"] + matched)


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("stage", choices=("freeze", "run"))
    if cli.parse_args().stage == "freeze":
        freeze()
    else:
        run()
