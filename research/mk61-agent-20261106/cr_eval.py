"""Compare bounded repair and compiler fallback with the previous Q4 cycle."""

from collections import Counter
from unittest.mock import patch

import torch

import bj_eval
import ce_eval
import ck_eval
import cl_eval
import cm_eval
import cn_eval
from aq_protocol import ACTION_ID, header_ids
from ay_codec import decode
from ay_common import read, rows, sha, write
from bl_spec import install
from bl_vm import CachedVM
from bt_decode import one
from ce_finish import transitions
from ci_runtime import power_key
from cn_runtime import CONTEXT
from cq_eval import Decoder as ParentDecoder, load_actor, parse_audit, scorer
from cq_language import independent_spec
from cq_runtime import make_session as previous_session
from cr_data import PREVIOUS, ROOT
from cr_runtime import COUNTEREXAMPLES, WriteRequest, make_session


MODES = ("current", "bounded", "bounded-compiler")


class Decoder(ParentDecoder):
    def __init__(self, device):
        super().__init__(device)
        self.forced_cache = {}

    def recovery_request(self, action, body, phase):
        prompt = self.verified_request(action, body)
        self.verified[prompt]["phase"] = phase
        return prompt

    def forced_write(self, prompt):
        use_checkpoint = prompt in self.full_prompts
        key = (use_checkpoint, prompt)
        if key not in self.forced_cache:
            model = self.models["working"] if use_checkpoint else self.original
            self.forced_cache[key] = one(model, self.tokenizers["working"], prompt, CONTEXT, forced_action="write")
            self.actual_calls += 1
        result = {**self.forced_cache[key], "profile": "actor", "phase": "forced_write"}
        if result["codec_error"]:
            # The cycle may continue on a decoder failure when there is a compiler fallback.
            result.update(action="unsure", body=[], write_codec_error=result["codec_error"], codec_error=None)
        return result

    def __call__(self, model, tokenizer, prompts, forced_action=None):
        free = [p for p in prompts if not isinstance(p, WriteRequest)]
        output = iter(super().__call__(model, tokenizer, free, forced_action))
        return [self.forced_write(p) if isinstance(p, WriteRequest) else next(output) for p in prompts]


def done_counts(goal, row, totals):
    spec = independent_spec(goal["task"], goal["spec"]["angle"]) or row["initial_spec"]
    checks = iter(row["gate_checks"])
    seen = set()
    for h in row["history"]:
        if h["kind"] == "replan":
            spec = decode(h["body"], goal["pool"], goal["spec"]["angle"])
        if h["kind"] == "done_blocked":
            totals["blocked_repeats"] += 1
        if h["kind"] not in ("done", "done_rejected"):
            continue
        verdict = next(checks)
        if h["kind"] == "done":
            continue
        totals["rejected"] += 1
        if verdict["reason"] in COUNTEREXAMPLES:
            key = (h["revision"], tuple(h["evaluated_body"]), power_key(spec) if spec is not None else None)
            if key in seen:
                totals["repeated_counterexample"] += 1
            seen.add(key)
    assert next(checks, None) is None


def add_metrics(goals, primary, records, decoder):
    # Restore errors hidden from the runner while it advanced to a fallback.
    for row in records:
        for h in row["history"]:
            g = h.get("generation", {})
            if "write_codec_error" in g:
                g["codec_error"] = g["write_codec_error"]
    result = scorer(goals, primary, records, decoder)
    actions = Counter()
    calls = Counter()
    repairs = Counter()
    claims = Counter()
    max_write_context = 0
    max_forced_context = 0
    header = len(header_ids(decoder.tokenizers["working"], "write"))

    def inference(generation):
        role = generation.get("profile")
        if role not in ("actor", "translator"):
            return
        calls[role] += int(generation.get("codec_error") != "context_overflow")
        if generation.get("retry_after"):
            calls[role] += 1

    for g in primary:
        inference(g["generation"])
    tasks = {g["id"]: g for g in goals}
    for row in records:
        done_counts(tasks[row["task_id"]], row, claims)
        applied = None
        for h in row["history"]:
            g = h.get("generation", {})
            inference(g)
            completed_write = (g.get("profile") == "actor" and g.get("codec_error") is None
                               and g.get("generated_token_ids", [])[:1] == [ACTION_ID["write"]])
            if completed_write:
                # In the log the action replaces END; the actual wire header is counted separately.
                used = g["input_tokens"] + header + len(g["generated_token_ids"])
                assert used <= CONTEXT
                max_write_context = max(max_write_context, used)
            if g.get("phase") == "forced_write":
                actions["neural_attempts"] += 1
                if completed_write:
                    max_forced_context = max(max_forced_context, used)
                    actions["neural_complete"] += 1
                if h["kind"] == "write":
                    actions["neural_commits"] += 1
            if g.get("phase") in ("compile_confirmed_spec", "compile_unavailable"):
                actions["compiler_attempts"] += 1
                if h["kind"] == "write":
                    actions["compiler_commits"] += 1
            if h["kind"] == "write":
                applied = h.get("repair_source", "ordinary_model")
        if row["pass"] and not row["initially_correct"]:
            assert applied is not None
            repairs[applied] += 1
    assert sum(repairs.values()) == result["repairs"]
    result.update(done=claims, recovery=actions, inference=calls, repair_source=repairs,
                  neural_calls=sum(calls.values()), write_max_context=max_write_context,
                  forced_write_max_context=max_forced_context)
    return result


def read_previous(decoder):
    root = PREVIOUS / "eval/closed"
    manifest = read(root / "complete.json")
    path = root / "checked-compact/full.json"
    assert sha(path) == manifest["files"]["checked-compact/full.json"]
    metrics = root / "checked-compact/metrics.json"
    assert sha(metrics) == manifest["files"]["checked-compact/metrics.json"]
    previous = read(path)
    short_ids = {r["id"] for r in read(metrics)["post_review"]["rows"] if r["short"]}
    records = []
    for row in previous["records"]:
        excluded = cm_eval.after_review(row)["prompt"] if row["id"] in short_ids else None
        history = [h for h in row["history"] if h.get("generation", {}).get("profile") in ("actor", "translator")
                   and h["prompt"] != excluded]
        records.append({**row, "history": history})
    cm_eval.seed_decoder(decoder, previous["primary"], records)
    return previous["primary"]


def evaluate(split, device):
    assert split in ("diagnostic", "closed")
    diagnostic = split == "diagnostic"
    path = (PREVIOUS if diagnostic else ROOT) / "closed.jsonl"
    folder = ROOT / "eval" / split
    receipt = folder / "complete.json"
    if receipt.exists():
        return
    torch.set_num_threads(2)
    install()
    goals = rows(path)
    vm = CachedVM()
    decoder = Decoder(device)
    decoder.reset_policy()
    actor = load_actor(False)
    inputs = {"data": sha(path), "actor": sha(actor), "working": sha(ce_eval.PROFILES / "working/model.mkqb"),
              "translator": sha(cl_eval.model_path(cm_eval.STEP)), "context": CONTEXT}
    ck_eval.status(folder, "initial", split=split, tasks=len(goals))
    if diagnostic:
        primary = read_previous(decoder)
    else:
        decoder.phase = "initial"
        with patch.object(ce_eval, "ROOT", folder), patch.multiple(
            bj_eval.core, generate=decoder, render=ce_eval.render,
        ):
            primary = bj_eval.core.primary(None, None, goals, "spec", vm)
    decoder.phase = "full_cycle"
    with patch.object(cn_eval, "actor_path", lambda _: actor):
        decoder.set_step(900)
    frozen = ce_eval.frozen_digest(decoder.models["working"])
    initial = {r["id"]: r for r in primary}
    baseline = None
    files = {}
    for mode in MODES:
        decoder.reset_policy()
        dest = folder / mode
        ck_eval.status(dest, "full_cycle", split=split, tasks=len(goals))
        session = (previous_session(decoder, fit_long_prompts=True) if mode == "current"
                   else make_session(decoder, use_compiler=mode == "bounded-compiler"))
        with (
            patch.object(ce_eval, "ROOT", dest),
            patch.multiple(bj_eval, Session=session, generate=decoder),
            patch.object(bj_eval.core, "mutant", lambda goal, *_: (goal["error_kind"], goal["bad_body"])),
        ):
            records = bj_eval.episodes(None, None, goals, initial, vm, "self")
        result = add_metrics(goals, primary, records, decoder)
        if baseline is None:
            baseline = records
        else:
            result["paired"] = transitions(baseline, records)
        write(dest / "metrics.json", result)
        write(dest / "full.json", {"primary": primary, "records": records, "inputs": inputs, "mode": mode})
        for filename in ("full.json", "metrics.json"):
            file = dest / filename
            files[str(file.relative_to(folder))] = sha(file)
        print(split, mode, {k: result[k] for k in ("repairs", "repair_source", "completed", "accepted_false_DONE",
                                                    "corruption", "unsure", "clarifications", "done", "neural_calls",
                                                    "recovery", "forced_write_max_context")}, flush=True)
    assert frozen == ce_eval.frozen_digest(decoder.models["working"])
    decoder.set_step(0)
    decoder.verify_weights()
    assert inputs["actor"] == sha(actor) and inputs["data"] == sha(path)
    write(receipt, {"inputs": inputs, "parser": parse_audit(goals), "files": files})
