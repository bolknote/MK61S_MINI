"""Paired Q4 evaluation of early SPEC checks and limited prompt compaction."""

from collections import Counter
import copy
import time
from unittest.mock import patch

import torch

import bj_eval
import ce_eval
import ck_eval
import cl_eval
import cm_eval
import cn_eval
import co_eval
from aq_protocol import ACTION_ID, header_ids
from ar_spec import equivalent
from ay_common import read, rows, sha, write
from bl_spec import install
from bl_vm import CachedVM
from ce_finish import transitions
from ci_runtime import power_key
from cn_review_check import GuardedDecoder, make_session as previous_session
from cn_runtime import CONTEXT, limit
from co_train import parent_dir
from cp_data import ROOT as LONG_RUN
from cq_data import ROOT
from cq_language import independent_spec
from cq_runtime import make_session


MODES = ("current", "checked", "checked-compact")
DIAGNOSTIC_STEP = 46221


class Decoder(GuardedDecoder):
    def reset_policy(self):
        self.full_prompts.clear()
        self.blocked.clear()
        self.pending_write.clear()
        self.budgeted = {}
        self.verified = {}

    def verified_request(self, action, body):
        key = f"Харнесс подтвердил действие {len(self.verified) + 1}"
        self.verified[key] = {"action": action, "body": body, "codec_error": None, "input_tokens": 0,
                              "generated_token_ids": [], "profile": "harness", "phase": "independent_verification"}
        return key

    def __call__(self, model, tokenizer, prompts, forced_action=None):
        deferred = [p for p in prompts if p not in self.verified]
        answers = iter(super().__call__(model, tokenizer, deferred, forced_action))
        return [copy.deepcopy(self.verified[p]) if p in self.verified else next(answers) for p in prompts]


def scorer(goals, primary, records, decoder):
    result = cn_eval.summarize(goals, primary, records, decoder)
    co_eval.details(goals, records, decoder, result)
    header = len(header_ids(decoder.tokenizers["working"], "write"))
    budget = limit(decoder.tokenizers["working"])
    actual_write = Counter()
    automatic = Counter()
    compensated = set()
    for row in records:
        for i, event in enumerate(row["history"]):
            prompt = event.get("prompt")
            generation = event.get("generation", {})
            if generation.get("profile") == "harness":
                automatic[event["kind"]] += 1
            if event["kind"] in ("needs_confirmation", "write_rejected"):
                automatic[event["kind"]] += 1
            extra = prompt in decoder.budgeted
            compressed = extra or prompt in decoder.full_prompts
            if extra:
                compensated.add(row["id"])
                assert generation["input_tokens"] <= budget < decoder.budgeted[prompt]
            if generation.get("profile") != "actor":
                continue
            if generation.get("generated_token_ids", [])[:1] != [ACTION_ID["write"]]:
                continue
            error = generation["codec_error"]
            if error:
                actual_write["incomplete" if error == "incomplete" else "other_error"] += 1
                if i == 0 and error == "incomplete":
                    actual_write["incomplete_first"] += 1
                if compressed:
                    actual_write["compact_errors"] += 1
            else:
                actual_write["complete"] += 1
                if compressed:
                    used = generation["input_tokens"] + header + len(generation["generated_token_ids"])
                    assert used <= CONTEXT
                    actual_write["max_compact_context"] = max(actual_write["max_compact_context"], used)
                    actual_write["compact_complete"] += 1
    result["executor_write"] = actual_write
    result["automation"] = automatic
    result["extra_compact_episodes"] = len(compensated)
    result["extra_compact_calls"] = sum(h.get("prompt") in decoder.budgeted
                                        for r in records for h in r["history"])
    result["max_extra_compact_input"] = max((h["generation"]["input_tokens"]
                                            for r in records for h in r["history"]
                                            if h.get("prompt") in decoder.budgeted), default=0)
    asks = {r["id"] for r in records if any(h["kind"] == "needs_confirmation" for h in r["history"])}
    result["clarifications"] = len(asks)
    result["unsure"] = result["refusals"] - len(asks)
    result["unsure_correct_spec"] = sum(r["abstained"] and r["final_spec_intent"]["tested_equal"]
                                        and r["id"] not in asks for r in records)
    result["unsure_correct_code_and_spec"] = sum(r["abstained"] and r["candidate_correct_at_exit"]
                                                 and r["final_spec_intent"]["tested_equal"]
                                                 and r["id"] not in asks for r in records)
    result["preserved_original_code"] = sum(r["initially_correct"] and r["body"] == g["reference_body"]
                                            for g, r in zip(goals, records[::2], strict=True))
    return result


def parse_audit(goals):
    totals = {}
    for goal in goals:
        spec = independent_spec(goal["task"], goal["spec"]["angle"])
        grade = totals.setdefault(goal["family"], Counter())
        if spec is None:
            grade["unsupported"] += 1
        elif power_key(spec) == power_key(goal["spec"]):
            grade["right"] += 1
        elif equivalent(spec, goal["spec"], goal["audit_inputs"])["tested_equal"]:
            grade["equivalent_on_audit"] += 1
        else:
            grade["wrong"] += 1
    return totals


def diagnostic_primary(decoder):
    previous = LONG_RUN / "eval" / f"closed-{DIAGNOSTIC_STEP:04}"
    assert sha(previous / "full.json") == read(previous / "complete.json")["full_sha256"]
    run = read(previous / "full.json")
    short = set(run["short_prompts"])
    records = [{**r, "history": [h for h in r["history"] if h.get("prompt") not in short]}
               for r in run["records"]]
    cm_eval.seed_decoder(decoder, run["primary"], records)
    return run["primary"]


def load_actor(diagnostic):
    if not diagnostic:
        return parent_dir() / "model.mkqb"
    folder = LONG_RUN / "checkpoints" / f"{DIAGNOSTIC_STEP:06}"
    path = folder / "model.mkqb"
    assert sha(path) == read(folder / "manifest.json")["Q4_sha256"]
    return path


def evaluate(split, device):
    assert split in ("diagnostic", "closed")
    diagnostic = split == "diagnostic"
    path = (LONG_RUN if diagnostic else ROOT) / "closed.jsonl"
    receipt = ROOT / "eval" / split / "complete.json"
    if receipt.exists():
        return
    torch.set_num_threads(2)
    install()
    goals = rows(path)
    vm = CachedVM()
    decoder = Decoder(device)
    decoder.reset_policy()
    step = DIAGNOSTIC_STEP if diagnostic else 900
    actor = load_actor(diagnostic)
    sources = {"data": sha(path), "working": sha(ce_eval.PROFILES / "working/model.mkqb"),
               "actor": sha(actor), "translator": sha(cl_eval.model_path(cm_eval.STEP)),
               "context": CONTEXT, "actor_step": step}
    folder = receipt.parent
    with patch.object(ce_eval, "ROOT", folder):
        ck_eval.status(folder, "initial", split=split, tasks=len(goals))
        if diagnostic:
            primary = diagnostic_primary(decoder)
        else:
            decoder.phase = "initial"
            with patch.multiple(bj_eval.core, generate=decoder, render=ce_eval.render):
                primary = bj_eval.core.primary(None, None, goals, "spec", vm)
            decoder.phase = "full_cycle"
        with patch.object(cn_eval, "actor_path", lambda _: actor):
            decoder.set_step(step)
        frozen = ce_eval.frozen_digest(decoder.models["working"])
        previous = None
        files = {}
        for mode in MODES:
            decoder.reset_policy()
            dest = folder / mode
            ck_eval.status(dest, "full_cycle", split=split, tasks=len(goals))
            actual_calls = decoder.actual_calls
            started = time.monotonic()
            session = (previous_session(decoder, notify=False, correct_action=True) if mode == "current"
                       else make_session(decoder, fit_long_prompts=mode == "checked-compact"))
            with (
                patch.object(ce_eval, "ROOT", dest),
                patch.multiple(bj_eval, Session=session, generate=decoder),
                patch.object(bj_eval.core, "mutant", lambda goal, *_: (goal["error_kind"], goal["bad_body"])),
            ):
                records = bj_eval.episodes(None, None, goals, {r["id"]: r for r in primary}, vm, "self")
            result = scorer(goals, primary, records, decoder)
            if previous is None:
                previous = records
            else:
                result["paired"] = transitions(previous, records)
            result.update(seconds=time.monotonic() - started, actual_calls=decoder.actual_calls - actual_calls)
            write(dest / "metrics.json", result)
            write(dest / "full.json", {"primary": primary, "records": records, "inputs": sources, "mode": mode})
            for filename in ("full.json", "metrics.json"):
                entry = dest / filename
                files[str(entry.relative_to(folder))] = sha(entry)
            print(split, mode, {k: result[k] for k in ("repairs", "completed", "accepted_false_DONE",
                                                       "corruption", "unsure", "clarifications",
                                                       "executor_write", "extra_compact_episodes")}, flush=True)
    assert frozen == ce_eval.frozen_digest(decoder.models["working"])
    decoder.set_step(0)
    decoder.verify_weights()
    assert sources["actor"] == sha(actor)
    assert sources["data"] == sha(path)
    write(receipt, {"inputs": sources, "parser": parse_audit(goals), "files": files})
