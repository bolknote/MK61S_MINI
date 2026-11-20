"""Run one full Q4 control and compare the two short-path changes factorially."""

import argparse
import time
from unittest.mock import patch

import torch

import ce_eval
from ar_spec import equivalent, verify
from ay_common import read, rows, sha, write
from bl_spec import install
from bl_vm import CachedVM
from ce_short_path import parse_task, short_path, spec_key
from cf_data import ROOT
from cf_language import expanded_parse
from cf_runtime import checked_program


ARMS = {
    "strict_agreement": (parse_task, False),
    "strict_priority": (parse_task, True),
    "expanded_agreement": (expanded_parse, False),
    "expanded_priority": (expanded_parse, True),
}


def status(phase, **data):
    state = {"phase": phase, "time": time.time(), **data}
    write(ROOT / "status.json", state)
    print(state, flush=True)


def freeze():
    prior = ce_eval.check_frozen()
    assert not (ROOT / "frozen.json").exists()
    wording = read(ROOT / "wording-frozen.json")
    assert sha(ROOT / "closed.jsonl") == wording["closed_sha256"]
    assert sha(ROOT / "wording-audit.jsonl") == wording["audit_sha256"]
    assert sha(ROOT / "closed-asts.jsonl") == read(ROOT / "ast-frozen.json")["sha256"]
    assert len(rows(ROOT / "closed.jsonl")) == 256
    files = {**prior["files"]}
    files.update({str(p.relative_to(ce_eval.REPO)): sha(p) for p in ce_eval.HERE.glob("cf_*.py")})
    for name in ("closed.jsonl", "closed-asts.jsonl", "ast-frozen.json", "wording-audit.jsonl", "wording-frozen.json"):
        path = ROOT / name
        files[str(path.relative_to(ce_eval.REPO))] = sha(path)
    write(ROOT / "frozen.json", {
        "files": files,
        "arms": list(ARMS),
        "weights": "same working actor and BU1500 translator as the preceding comparison",
        "context": 1024,
        "KV": "FP32",
        "optimizer_updates": 0,
        "tokens": "one initial neural translation is charged for every arm and episode",
        "fallback": "exact full-cycle trajectory with the original state if no parse, or if agreement is required and missing",
        "priority_unverified": "keep initial code and ask for clarification when a recognized task disagrees and no program passes",
        "fresh_tasks": 256,
        "closed_model_generations_seen": False,
    })


def check_frozen():
    with patch.object(ce_eval, "ROOT", ROOT):
        return ce_eval.check_frozen()


def needs_confirmation(goal, baseline, initial, independent, reason, vm):
    final = verify(vm, initial, goal["pool"], goal["spec"], goal["audit_inputs"])
    correct = final["status"] == "TESTED"
    return {
        **{key: baseline[key] for key in ("id", "task_id", "panel", "family", "initial", "initially_correct")},
        "gate": "independent_text_and_ROM",
        "route": "needs_confirmation",
        "fallback_reason": reason,
        "program_correct": correct,
        "spec_consistent": False,
        "finished": False,
        "eligible": False,
        "pass": False,
        "abstained": True,
        "body": initial,
        "task_audit": final,
        "declared_spec": independent,
        "initial_spec": baseline["initial_spec"],
        "gate_checks": [],
        "history": [{"kind": "unsure", "harness_forced": reason}],
        "rollback": False,
        "candidate_at_exit": initial,
        "candidate_correct_at_exit": correct,
        "DONE_claims": 0,
        "false_DONE_claims": 0,
        "replans": 0,
        "final_spec_intent": equivalent(independent, goal["spec"], goal["audit_inputs"]),
    }


def run_variant(goals, plans, baseline, parser, priority, vm, *, reference=False):
    by_id = {goal["id"]: goal for goal in goals}
    parsed = {goal["id"]: parser(goal["task"], goal["spec"]["angle"]) for goal in goals}
    output = []
    for row in baseline:
        goal = by_id[row["task_id"]]
        spec = parsed[goal["id"]]
        plan = plans[goal["id"]]["declared_spec"]
        initial = goal["reference_body"] if row["initially_correct"] else goal["bad_body"]
        angle, pool = goal["spec"]["angle"], goal["pool"]
        checks = goal["public_inputs"] + goal["checker_inputs"]
        agrees = spec is not None and plan is not None and spec_key(spec) == spec_key(plan)
        selected, route = checked_program(spec, plan, initial, angle, pool, checks, vm, prefer_parser=priority)
        if reference:
            expected = short_path(goal["task"], angle, pool, plan, initial, checks, vm)
            assert (selected, route, spec) == expected, goal["id"]
        if selected is not None:
            result = ce_eval.audit_short_completion(goal, row, selected, spec, route, len(checks), vm)
        elif priority and spec is not None and not agrees:
            # A known disagreement cannot be approved solely by the model's old hypothesis.
            result = needs_confirmation(goal, row, initial, spec, route, vm)
        else:
            result = {**row, "route": "full_cycle", "fallback_reason": route}
        result.update(independent_parse=spec, initial_agreement=agrees)
        output.append(result)
    return output


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
    assert len(baseline) == 2 * len(goals)
    write(ROOT / "full-cycle.json", {"primary": primary, "records": baseline})
    plans = {row["id"]: row for row in primary}
    for name, (parser, priority) in ARMS.items():
        status("check_variant", variant=name, episodes=len(baseline))
        variant = run_variant(goals, plans, baseline, parser, priority, vm, reference=name == "strict_agreement")
        write(ROOT / f"{name}.json", {"records": variant})
    decoder.verify_weights()
    assert check_frozen() == manifest
    status("native_parity", actual_model_calls=decoder.actual_calls)
    parity = ce_eval.native_parity(decoder, primary, baseline, variant)
    write(ROOT / "native-verification.json", parity)
    assert check_frozen() == manifest
    write(ROOT / "complete.json", {
        "complete": True,
        "tasks": len(goals),
        "episodes_per_arm": len(baseline),
        "arms": ["full_cycle", *ARMS],
        "actual_model_calls": decoder.actual_calls,
        "optimizer_updates": 0,
        "weights_verified": True,
        "native_matched": parity["matched"],
        "native_checked": parity["checked"],
    })
    status("complete", native_matched=parity["matched"], native_checked=parity["checked"])


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("stage", choices=("freeze", "run"))
    if cli.parse_args().stage == "freeze":
        freeze()
    else:
        run()
