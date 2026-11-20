"""Paired Q4 replay of a post-review prompt change with frozen weights."""

import argparse
from collections import Counter
from functools import partial
from pathlib import Path
import time
from unittest.mock import patch

import torch

import bj_eval
import ce_eval
import ck_eval
import cl_eval
from aq_protocol import header_ids
from ay_common import read, rows, sha, write
from bl_spec import install
from bl_vm import CachedVM
from ce_finish import measures, transitions
from cl_data import ROOT as SOURCE
from cl_train import check_frozen
from cm_runtime import Session


ROOT = SOURCE.with_name("kon-tiki-post-replan-v1")
STEP = 38632
POLICY = Path(__file__).with_name("cm_runtime.py")
DECODE_FIELDS = ("action", "body", "codec_error", "generated_token_ids", "input_tokens", "context", "cache")


def generation_result(generation):
    return {name: generation.get(name) for name in DECODE_FIELDS}


def load_baseline(split):
    folder = SOURCE / "eval" / f"{split}-{STEP:06d}"
    receipt = read(folder / "complete.json")
    path = folder / "full.json"
    assert receipt["full_sha256"] == sha(path)
    baseline = read(path)
    assert baseline["inputs"] == receipt["inputs"]
    assert baseline["inputs"] == {
        "split": split,
        "step": STEP,
        "dataset_sha256": sha(SOURCE / f"{split}.jsonl"),
        "translator_sha256": sha(cl_eval.model_path(STEP)),
        "actor_sha256": sha(ce_eval.PROFILES / "working/model.mkqb"),
    }
    return baseline, receipt


def load_decoder(device):
    load = ce_eval.load
    with patch.object(ce_eval, "load", lambda path, _: load(path, device)):
        with patch.object(ck_eval, "model_path", cl_eval.model_path):
            return ck_eval.decoder_for(STEP)


def seed_decoder(decoder, primary, records):
    def remember(item):
        output = item["generation"]
        actor = output["profile"] == "actor"
        key = ("working" if actor else "translator", None if actor else "write", item["prompt"])
        previous = decoder.cache.setdefault(key, output)
        assert generation_result(previous) == generation_result(output)

    for row in primary:
        remember(row)
    for row in records:
        for step in row["history"]:
            if "generation" in step:
                remember(step)
    return len(decoder.cache)


def comparable_record(row):
    return {**row, "history": [
        {**step, "generation": generation_result(step["generation"])} if "generation" in step else step
        for step in row["history"]
    ]}


def after_review(row):
    for previous, step in zip(row["history"], row["history"][1:]):
        if previous["kind"] == "replan" and "generation" in step:
            return step
    return None


def summarize_action(step, write_header_tokens):
    output = step["generation"]
    length = output["input_tokens"]
    action = step["kind"]
    result = {
        "prompt_tokens": length,
        "write_room": ce_eval.CONTEXT - length - write_header_tokens,
        "action": action,
        "codec_error": output["codec_error"],
        "generated_tokens": len(output["generated_token_ids"]),
    }
    if action == "write":
        result["context_tokens_used"] = length + write_header_tokens + len(output["generated_token_ids"])
    return result


def evaluate(split, device, target_only):
    torch.set_num_threads(2)
    install()
    manifest = check_frozen("exam")
    policy = {"runtime_sha256": sha(POLICY), "evaluation_sha256": sha(__file__),
              "context": ce_eval.CONTEXT, "device": device, "optimizer_updates": 0}
    if split == "closed":
        assert not target_only
        assert read(ROOT / "policy.json") == policy
    baseline, receipt = load_baseline(split)
    goals = rows(SOURCE / f"{split}.jsonl")
    primary, old = baseline["primary"], baseline["records"]
    if target_only:
        targets = read(SOURCE / "preselected.json")["targets"]
        tasks = {r["task_id"] for r in old if r["id"] in targets}
        goals = [g for g in goals if g["id"] in tasks]
        primary = [r for r in primary if r["id"] in tasks]
        old = [r for r in old if r["task_id"] in tasks]
    ck_eval.check_trajectory(goals, old, primary)

    folder = ROOT / ("targets" if target_only else split)
    started = time.monotonic()
    ck_eval.status(folder, "load_models", episodes=len(old))
    decoder = load_decoder(device)
    tokenizer = decoder.tokenizers["working"]
    seeded = seed_decoder(decoder, primary, old)
    vm = CachedVM()
    plans = {r["id"]: r for r in primary}

    # The explicitly unmodified arm must reproduce the full old trajectory.
    # Any novel candidate prompt is evaluated on the loaded Q4 models.
    decoder.phase = "full_cycle"
    ck_eval.status(folder, "baseline", seeded=seeded)
    compact = partial(Session, tokenizer=tokenizer, context=ce_eval.CONTEXT)
    with patch.object(ce_eval, "ROOT", folder), patch.multiple(
        bj_eval, generate=decoder
    ), patch.object(bj_eval.core, "mutant", lambda goal, *_: (goal["error_kind"], goal["bad_body"])):
        replay = bj_eval.episodes(None, None, goals, plans, vm, "self")
        assert decoder.actual_calls == 0
        assert list(map(comparable_record, replay)) == list(map(comparable_record, old))
        ck_eval.status(folder, "candidate", episodes=len(old))
        with patch.object(bj_eval, "Session", compact):
            new = bj_eval.episodes(None, None, goals, plans, vm, "self")
    ck_eval.check_trajectory(goals, new, primary)
    decoder.verify_weights()
    assert check_frozen("exam") == manifest
    assert sha(POLICY) == policy["runtime_sha256"]
    assert sha(__file__) == policy["evaluation_sha256"]

    header = len(header_ids(tokenizer, "write"))
    edited = {}
    for before, after in zip(old, new):
        old_step, new_step = after_review(before), after_review(after)
        if old_step is None or new_step is None:
            assert comparable_record(before) == comparable_record(after)
            continue
        if old_step["prompt"] == new_step["prompt"]:
            assert comparable_record(before) == comparable_record(after)
            continue
        edited[before["id"]] = {
            "before": summarize_action(old_step, header), "after": summarize_action(new_step, header),
            "pass_before": before["pass"], "pass_after": after["pass"],
        }
    result = {
        "policy": policy,
        "inputs": baseline["inputs"],
        "baseline_sha256": receipt["full_sha256"],
        "first_programs": {"correct": sum(r["program_correct"] for r in primary), "total": len(primary),
                           "composition_correct": sum(r["program_correct"] for r in primary if r["family"] == "composition"),
                           "composition_total": sum(r["family"] == "composition" for r in primary)},
        "before": measures(old),
        "after": measures(new),
        "transitions": transitions(old, new),
        "altered_prompts": edited,
        "post_review_generation_errors": {
            arm: dict(Counter(step["generation"]["codec_error"] for row in group
                              if (step := after_review(row)) is not None and step["generation"]["codec_error"]))
            for arm, group in (("before", old), ("after", new))
        },
        "actual_candidate_calls": decoder.actual_calls,
        "verified_weight_digests": decoder.digests,
        "seconds": time.monotonic() - started,
    }
    full_path = folder / "full.json"
    write(full_path, {"inputs": baseline["inputs"], "primary": primary, "records": new})
    write(folder / "comparison.json", result)
    write(folder / "complete.json", {"comparison_sha256": sha(folder / "comparison.json"),
                                     "full_sha256": sha(full_path)})
    ck_eval.status(folder, "complete", changed=len(edited), before=result["before"], after=result["after"])


def seal(device):
    policies = [read(ROOT / split / "comparison.json")["policy"] for split in ("recovery", "development")]
    assert policies[0] == policies[1]
    policy = policies[0]
    assert policy["runtime_sha256"] == sha(POLICY) and policy["evaluation_sha256"] == sha(__file__)
    assert policy["device"] == device
    write(ROOT / "policy.json", policy)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("targets", "recovery", "development", "seal", "closed"))
    parser.add_argument("--device", default="cuda:0")
    args = parser.parse_args()
    if args.stage == "seal":
        seal(args.device)
    else:
        evaluate("recovery" if args.stage == "targets" else args.stage, args.device, args.stage == "targets")
