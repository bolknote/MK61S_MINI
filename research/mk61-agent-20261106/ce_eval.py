"""Paired Q4 evaluation of the independent SPEC check and the existing cycle."""

import copy
import hashlib
import time

import torch

import bj_eval as full_cycle
from aq_protocol import prompt_ids
from ar_spec import equivalent, verify
from ay_common import read, rows, sha, write
from be_model import load
from bj_runtime import Session, render
from bl_spec import install
from bl_vm import CachedVM
from bt_decode import one
from bu_model import frozen_digest
from cd_common import ROOT as PREVIOUS, compact_head, output_ids
from ce_data import HERE, REPO, ROOT
from ce_short_path import short_path


PROFILES = PREVIOUS / "profiles"
CONTEXT = 1024


def status(phase, **data):
    record = {"phase": phase, "time": time.time(), **data}
    write(ROOT / "status.json", record)
    print(record, flush=True)


def check_frozen():
    manifest = read(ROOT / "frozen.json")
    for name, digest in manifest["files"].items():
        assert sha(REPO / name) == digest, name
    return manifest


def freeze():
    assert not (ROOT / "frozen.json").exists()
    assert sha(ROOT / "closed-asts.jsonl") == read(ROOT / "ast-frozen.json")["sha256"]
    assert len(rows(ROOT / "closed.jsonl")) == 256
    names = ["ce_short_path.py", "ce_data.py", "ce_wording.py", "ce_teacher.py", "ce_eval.py",
             "bj_eval.py", "bj_runtime.py", "az_runtime.py", "ay_eval.py", "ay_runtime.py",
             "ar_runtime.py", "as_runtime.py", "ar_spec.py", "bl_spec.py", "bh_spec.py",
             "ay_codec.py", "be_language.py", "ha_protocol.py", "bt_decode.py"]
    files = [HERE / name for name in names]
    files += [ROOT / name for name in ("closed.jsonl", "ast-frozen.json", "closed-asts.jsonl")]
    for role in ("working", "translator"):
        files.extend(p for p in (PROFILES / role).rglob("*") if p.is_file())
        files.extend(PREVIOUS / "server-results" / "export" / role / name
                     for name in ("model.mka", "protocol.json", "output-token-ids.json"))
    for path in (ROOT / "teacher-wording.json", ROOT / "teacher-audit.jsonl"):
        if path.exists():
            files.append(path)
    for name in ("action-probe.dylib", "codec-probe.dylib"):
        files.append(PREVIOUS / "server-results/native" / name)
    from full_isa_vm import build
    files.append(build())
    manifest = {
        "files": {str(path.relative_to(REPO)): sha(path) for path in files},
        "context": CONTEXT,
        "KV": "FP32",
        "model_dtype": "Q4 weights, FP32 calculation",
        "optimizer_updates": 0,
        "actor": "working",
        "translator": "BU1500",
        "closed_model_generations_seen": False,
        "fallback": "full cycle, same initial SPEC and starting program",
        "gate_inputs": ["task", "angle", "pool", "model SPEC", "current program", "public and existing checker inputs"],
        "finish_condition": "structural SPEC agreement, verified existing or freshly compiled program",
        "comparison_units": "256 tasks, one correct start and one wrong start each",
        "bootstrap_unit": "task",
        "token_convention": "submitted prompts including context rejections, processed prompts separately, reported action and body without terminator",
    }
    write(ROOT / "frozen.json", manifest)


class Decoder:
    def __init__(self):
        self.models = {}
        self.tokenizers = {}
        self.cache = {}
        self.actual_calls = 0
        self.logical_calls = 0
        self.phase = "initial"
        for role in ("working", "translator"):
            model, tokenizer = load(PROFILES / role, "cpu")
            compact_head(model, output_ids(tokenizer))
            self.models[role] = model
            self.tokenizers[role] = tokenizer
        assert self.tokenizers["working"].get_vocab() == self.tokenizers["translator"].get_vocab()
        self.digests = {role: frozen_digest(model) for role, model in self.models.items()}

    def __call__(self, model, tokenizer, prompts, forced_action=None):
        role = "translator" if forced_action == "write" else "working"
        phase = self.phase if self.phase == "initial" else "replan" if role == "translator" else "actor"
        results = []
        for prompt in prompts:
            key = (role, forced_action, prompt)
            cached = key in self.cache
            if not cached:
                self.cache[key] = one(self.models[role], self.tokenizers[role], prompt, CONTEXT, False, forced_action)
                self.actual_calls += 1
            result = copy.deepcopy(self.cache[key])
            result.update(profile="translator" if role == "translator" else "actor", phase=phase, cache_hit=cached)
            if cached:
                result["seconds"] = 0.0
            self.logical_calls += 1
            results.append(result)
            if self.logical_calls % 200 == 0:
                status(self.phase, logical_calls=self.logical_calls, actual_calls=self.actual_calls)
        return results

    def verify_weights(self):
        assert {role: frozen_digest(model) for role, model in self.models.items()} == self.digests


def full_records(goals, vm, decoder):
    old_generate, old_core_generate = full_cycle.generate, full_cycle.core.generate
    old_render, old_mutant = full_cycle.core.render, full_cycle.core.mutant
    try:
        full_cycle.generate = decoder
        full_cycle.core.generate = decoder
        full_cycle.core.render = render
        full_cycle.core.mutant = lambda goal, vm, kind: (goal["error_kind"], goal["bad_body"])
        primary = full_cycle.core.primary(None, None, goals, "spec", vm)
        assert len(primary) == len(goals)
        decoder.phase = "full_cycle"
        status("full_cycle", initial_translations=len(primary), logical_calls=decoder.logical_calls)
        records = full_cycle.episodes(None, None, goals, {r["id"]: r for r in primary}, vm, "self")
        return primary, records
    finally:
        full_cycle.generate, full_cycle.core.generate = old_generate, old_core_generate
        full_cycle.core.render, full_cycle.core.mutant = old_render, old_mutant


def audit_short_completion(goal, baseline, selected, spec, route, checked, vm):
    # Only the separate scorer uses audit_inputs or the expected task SPEC.
    audit = verify(vm, selected, goal["pool"], goal["spec"], goal["audit_inputs"])
    program_correct = audit["status"] == "TESTED"
    return {
        **{key: baseline[key] for key in ("id", "task_id", "panel", "family", "initial", "initially_correct")},
        "gate": "independent_text_and_ROM",
        "route": route,
        "program_correct": program_correct,
        "spec_consistent": True,
        "finished": True,
        "eligible": True,
        "pass": program_correct,
        "abstained": False,
        "body": selected,
        "task_audit": audit,
        "declared_spec": spec,
        "initial_spec": baseline["initial_spec"],
        "gate_checks": [{"status": "TESTED", "cases": checked, "independent_text": True}],
        "history": [{"kind": "done", "evaluated_body": selected, "harness_forced": "independent_SPEC_and_ROM"}],
        "rollback": False,
        "candidate_at_exit": selected,
        "candidate_correct_at_exit": program_correct,
        "DONE_claims": 0,
        "false_DONE_claims": 0,
        "replans": 0,
        "final_spec_intent": equivalent(spec, goal["spec"], goal["audit_inputs"]),
    }


def short_records(goals, primary, baseline, vm):
    goals = {goal["id"]: goal for goal in goals}
    plans = {plan["id"]: plan for plan in primary}
    result = []
    for row in baseline:
        goal = goals[row["task_id"]]
        plan = plans[goal["id"]]
        initial = goal["reference_body"] if row["initially_correct"] else goal["bad_body"]
        public = goal["public_inputs"]
        checks = goal["checker_inputs"]
        selected, route, spec = short_path(goal["task"], goal["spec"]["angle"], goal["pool"],
                                           plan["declared_spec"], initial, public + checks, vm)
        if selected is None:
            # With unchanged inputs the fallback is the identical, deterministic cycle.
            result.append({**row, "route": "full_cycle", "fallback_reason": route, "independent_parse": spec})
        else:
            result.append(audit_short_completion(goal, row, selected, spec, route, len(public) + len(checks), vm))
    return result


def native_parity(decoder, primary, baseline, short):
    import ay_native as native

    native.ARMS = ["working", "translator"]
    engine = native.Engine(PREVIOUS / "server-results", arm="working")
    probes = [("translator", "write", row["prompt"], row["generation"]) for row in primary[::32]]
    accepted = {row["task_id"] for row in short if row["route"] != "full_cycle"}
    verified = [row for row in primary if row["id"] in accepted]
    probes.extend(("translator", "write", row["prompt"], row["generation"]) for row in verified[:4])
    histories = [h for row in baseline for h in row["history"] if h.get("generation", {}).get("profile") == "actor" and not h["generation"].get("codec_error")]
    for action in ("write", "run", "trace", "diag", "done", "unsure"):
        matches = [h for h in histories if h["generation"]["action"] == action]
        probes.extend(("working", None, h["prompt"], h["generation"]) for h in matches[:2])
    probes.extend(("working", None, h["prompt"], h["generation"])
                  for h in sorted(histories, key=lambda h: h["generation"]["input_tokens"])[-2:])
    results = []
    seen = set()
    for role, forced, prompt, expected in probes:
        if (role, prompt) in seen:
            continue
        seen.add((role, prompt))
        engine.tool = role
        actual = engine.generate(prompt, forced)
        actual_input = actual.get("input_token_ids")
        exact_input = actual_input == prompt_ids(decoder.tokenizers[role], prompt)
        exact_output = actual["generated_token_ids"] == expected["generated_token_ids"]
        results.append({"profile": role, "action": expected["action"], "input_tokens": expected["input_tokens"],
                        "input_equal": exact_input, "output_equal": exact_output,
                        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()})
    return {"checked": len(results), "matched": sum(r["input_equal"] and r["output_equal"] for r in results), "cases": results}


def main():
    manifest = check_frozen()
    assert not (ROOT / "complete.json").exists()
    torch.set_num_threads(2)
    install()
    goals = rows(ROOT / "closed.jsonl")
    vm = CachedVM()
    status("initial", tasks=len(goals))
    decoder = Decoder()
    primary, baseline = full_records(goals, vm, decoder)
    assert len(baseline) == 2 * len(goals)
    write(ROOT / "full-cycle.json", {"primary": primary, "records": baseline, "summary": full_cycle.metrics(baseline)})
    status("short_path", completed_full_episodes=len(baseline))
    short = short_records(goals, primary, baseline, vm)
    write(ROOT / "short-path.json", {"records": short, "summary": full_cycle.metrics(short)})
    decoder.verify_weights()
    assert check_frozen() == manifest
    status("native_parity", episodes=len(short), actual_model_calls=decoder.actual_calls)
    parity = native_parity(decoder, primary, baseline, short)
    write(ROOT / "native-verification.json", parity)
    assert check_frozen() == manifest
    write(ROOT / "complete.json", {"complete": True, "optimizer_updates": 0, "tasks": len(goals),
                                  "episodes_per_variant": len(baseline), "actual_model_calls": decoder.actual_calls,
                                  "logical_full_cycle_calls": decoder.logical_calls, "weights_verified": True,
                                  "profile_digests": decoder.digests, "native_matched": parity["matched"], "native_checked": parity["checked"]})
    status("complete", native_matched=parity["matched"], native_checked=parity["checked"])


if __name__ == "__main__":
    import sys

    if sys.argv[1:] == ["freeze"]:
        freeze()
    else:
        main()
