"""Paired closed tests with the same short prompt, independent check and retry."""

import argparse
from collections import Counter
import time
from unittest.mock import patch

import torch

import bj_eval
import ce_eval
import ck_eval
import cl_eval
import cm_eval
import cn_eval
from aq_protocol import ACTION_ID, header_ids
from ar_spec import equivalent
from ay_common import read, rows, sha, write
from ay_codec import decode
from bl_spec import install
from bl_vm import CachedVM
from ce_finish import transitions
from cn_review_check import GuardedDecoder, make_session
from cn_runtime import CONTEXT, limit
from co_data import PREVIOUS, PARENT, ROOT
from co_train import PARENT_STEP, STEPS, check_inputs, parent_dir


def actor_file(step):
    if not step:
        return parent_dir() / "model.mkqb"
    folder = ROOT / "checkpoints" / f"{step:06}"
    path = folder / "model.mkqb"
    assert sha(path) == read(folder / "manifest.json")["Q4_sha256"]
    return path


class Decoder(GuardedDecoder):
    def __call__(self, model, tokenizer, prompts, forced_action=None):
        # Primary and repeated translations still go through the frozen translator.
        if forced_action:
            return cn_eval.Decoder.__call__(self, model, tokenizer, prompts, forced_action)
        return super().__call__(model, tokenizer, prompts)

def details(goals, episodes, decoder, metrics):
    by_id = {g["id"]: g for g in goals}
    short_prompts = decoder.full_prompts
    outcomes = Counter()
    writes = Counter()
    max_window = 0
    for row in episodes:
        event = cm_eval.after_review(row)
        if event is None or event["prompt"] not in short_prompts:
            if row["abstained"]:
                outcomes["other_refusal"] += 1
            continue
        prompt = event["prompt"]
        gen = event["generation"]
        original = decoder.change_cache[(decoder.step, prompt)]
        goal = by_id[row["task_id"]]
        revised = next(h["body"] for h in row["history"] if h["kind"] == "replan")
        spec = decode(revised, goal["pool"], goal["spec"]["angle"])
        correct = equivalent(spec, goal["spec"], goal["public_inputs"] + goal["checker_inputs"] +
                             goal["audit_inputs"])["tested_equal"]
        label = "correct_SPEC" if correct else "wrong_SPEC"
        outcomes[f"opportunity_{label}"] += 1
        if original["action"] == "unsure":
            outcomes[f"raw_UNSURE_{label}"] += 1
        if row["abstained"]:
            if event["kind"] == "unsure":
                key = "guard" if gen.get("guard_blocked") else "model"
                outcomes[f"refusal_{label}_{key}"] += 1
            else:
                outcomes["other_refusal"] += 1
        if gen.get("retry_after"):
            outcomes["runtime_retries"] += 1
        # Include every attempted WRITE from the first compact executor call.
        # A denied WRITE still took context before the guard rejected it.
        generations = [("model", original)]
        if gen.get("retry_after"):
            generations.append(("retry", gen))
        for phase, generation in generations:
            if generation["generated_token_ids"][:1] != [ACTION_ID["write"]]:
                continue
            writes[f"{phase}_attempts"] += 1
            if generation["codec_error"]:
                writes[f"{phase}_incomplete"] += 1
                continue
            used = (generation["input_tokens"] + len(header_ids(decoder.tokenizers["working"], "write")) +
                    len(generation["generated_token_ids"]))
            assert used <= CONTEXT and generation["input_tokens"] <= limit(decoder.tokenizers["working"])
            max_window = max(max_window, used)
            writes[f"{phase}_complete"] += 1
    assert sum(v for k, v in outcomes.items() if "refusal" in k) == metrics["refusals"]
    metrics["refusal_detail"] = outcomes
    metrics["write_detail"] = {**writes, "max_tokens_with_header_and_END": max_window}


def path_for(split):
    if split == "retired":
        return PARENT / "fresh.jsonl"
    if split in ("recovery", "development"):
        return PREVIOUS / f"{split}.jsonl"
    return ROOT / f"{split}.jsonl"


def evaluate(split, step=0):
    torch.set_num_threads(2)
    install()
    manifest = check_inputs()
    if split == "closed":
        assert step in (0, read(ROOT / "preselected.json")["audit_step"])
    goals = rows(path_for(split))
    folder = ROOT / "eval" / f"{split}-{step:04}"
    receipt = folder / "complete.json"
    fingerprint = {"data": sha(path_for(split)), "actor": sha(actor_file(step)),
                   "translator": sha(cl_eval.model_path(cm_eval.STEP)),
                   "source": sha(__file__), "context": CONTEXT, "step": step}
    if receipt.exists():
        completed = read(receipt)
        assert completed["inputs"] == fingerprint
        assert completed["full_sha256"] == sha(folder / "full.json")
        assert completed["metrics_sha256"] == sha(folder / "metrics.json")
        return
    t0 = time.monotonic()
    ck_eval.status(folder, "load", **fingerprint)
    decoder = Decoder("cuda:0")
    vm = CachedVM()
    plans_path = ROOT / "eval" / f"{split}-0000/full.json"
    old = None
    if step:
        old = read(plans_path)
        assert sha(plans_path) == read(plans_path.parent / "complete.json")["full_sha256"]
        primary = old["primary"]
    elif split in ("recovery", "development", "retired"):
        base = PARENT / "eval" / f"{'fresh' if split == 'retired' else split}-full-0000"
        assert sha(base / "full.json") == read(base / "complete.json")["full_sha256"]
        baseline = read(base / "full.json")
        primary = baseline["primary"]
        cm_eval.seed_decoder(decoder, primary, baseline["records"])
    else:
        decoder.phase = "initial"
        with patch.multiple(bj_eval.core, generate=decoder, render=ce_eval.render):
            primary = bj_eval.core.primary(None, None, goals, "spec", vm)
        decoder.phase = "full_cycle"

    if old is not None:
        # Only identical requests served by the original executor/translator
        # can be cached. Compact actions and kernel overrides are recalculated.
        short = set(old["short_prompts"])
        context_rows = []
        for row in old["records"]:
            history = [h for h in row["history"] if h.get("prompt") not in short]
            context_rows.append({**row, "history": history})
        cm_eval.seed_decoder(decoder, primary, context_rows)

    # cn_eval uses step 0 for the original model. Every compact call in both
    # arms must use the already-distilled executor packet or its continuation.
    with (
        patch.object(ce_eval, "ROOT", folder),
        patch.object(cn_eval, "actor_path", lambda _: actor_file(step)),
        patch.multiple(bj_eval, Session=make_session(decoder, False, True), generate=decoder),
        patch.object(bj_eval.core, "mutant", lambda g, *_: (g["error_kind"], g["bad_body"])),
    ):
        decoder.set_step(step or PARENT_STEP)
        records = bj_eval.episodes(None, None, goals, {r["id"]: r for r in primary}, vm, "self")
        metrics = cn_eval.summarize(goals, primary, records, decoder)
        details(goals, records, decoder, metrics)
        decoder.set_step(0)
    decoder.verify_weights()
    assert check_inputs() == manifest
    if old is not None:
        metrics["paired"] = transitions(old["records"], records)
    metrics["seconds"] = time.monotonic() - t0
    metrics["neural_calls"] = decoder.actual_calls
    log = {"inputs": fingerprint, "primary": primary, "records": records, "short_prompts": sorted(decoder.full_prompts)}
    write(folder / "full.json", log)
    write(folder / "metrics.json", metrics)
    write(receipt, {"inputs": fingerprint, "full_sha256": sha(folder / "full.json"),
                    "metrics_sha256": sha(folder / "metrics.json")})
    ck_eval.status(folder, "complete", **{k: v for k, v in metrics.items() if k not in ("post_review", "paired")})


def select():
    def m(split, step):
        folder = ROOT / "eval" / f"{split}-{step:04}"
        assert read(folder / "complete.json")["metrics_sha256"] == sha(folder / "metrics.json")
        return read(folder / "metrics.json")

    def avoidable(d):
        return sum(v for k, v in d["refusal_detail"].items() if k.startswith("refusal_correct_SPEC"))

    def raw_correct(d):
        return d["refusal_detail"].get("raw_UNSURE_correct_SPEC", 0)

    splits = ("validation", "recovery")
    baseline = [m(s, 0) for s in splits]
    ranked = []
    for step in STEPS:
        candidate = [m(s, step) for s in splits]
        safe = all(all(c[k] <= b[k] for k in ("accepted_false_DONE", "corruption")) for b, c in zip(baseline, candidate))
        repairs_lost = sum(len(c["paired"]["repairs"]["lost"]) for c in candidate)
        refusals = sum(avoidable(c) for c in candidate)
        raw = sum(raw_correct(c) for c in candidate)
        valid = safe and not repairs_lost and refusals < sum(avoidable(b) for b in baseline)
        key = (valid, safe, -repairs_lost, -refusals, -raw, sum(c["repairs"] for c in candidate),
               sum(c["completed"] for c in candidate), -step)
        ranked.append({"step": step, "key": key, "passes": valid, "safe": safe,
                       "repair_losses": repairs_lost, "avoidable_refusals": refusals,
                       "raw_correct_SPEC_UNSURE": raw})
    chosen = max(ranked, key=lambda r: r["key"])
    write(ROOT / "preselected.json", {"audit_step": chosen["step"], "pass": chosen["passes"],
                                      "validation": ranked, "used_closed": False})
    print(chosen, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("recovery", "development", "retired", "validation", "closed", "select"))
    parser.add_argument("--step", type=int, default=0)
    args = parser.parse_args()
    if args.stage == "select":
        select()
    else:
        evaluate(args.stage, args.step)
