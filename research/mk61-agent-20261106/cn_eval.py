"""Compare Q4 executors on identical states and full tool trajectories."""

import argparse
from collections import Counter
from functools import partial
from statistics import median
import time
from unittest.mock import patch

import torch

import bj_eval
import ce_eval
import ck_eval
import cl_eval
import cm_eval
from aq_protocol import ACTION_ID, header_ids, prompt_ids
from ay_common import read, rows, sha, write
from bj_runtime import Session as FullSession
from bl_spec import install
from bl_vm import CachedVM
from bt_decode import one
from ce_finish import measures
from ck_train import CURRENT
from cn_data import PREVIOUS, ROOT
from cn_runtime import CONTEXT, Session, limit
from cn_train import MILESTONES, check_inputs
from lowbit import load as load_packet


def actor_path(step):
    if step == 0:
        return CURRENT / "working/model.mkqb"
    folder = ROOT / "checkpoints" / f"{step:06}"
    path = folder / "model.mkqb"
    assert sha(path) == read(folder / "manifest.json")["Q4_sha256"]
    return path


class Decoder(ce_eval.Decoder):
    def __init__(self, device):
        original_load = ce_eval.load

        def pinned_load(path, _):
            return original_load(path, device)

        with patch.object(ce_eval, "load", pinned_load), patch.object(ck_eval, "model_path", cl_eval.model_path):
            self.__dict__.update(ck_eval.decoder_for(cm_eval.STEP).__dict__)
        self.original = self.models["working"]
        self.change_cache = {}
        self.step = 0
        self.full_prompts = {}
        self.phase = "full_cycle"

    def set_step(self, step):
        if step and step != self.step:
            model, _ = ce_eval.load(CURRENT / "working", next(self.original.parameters()).device)
            load_packet(model, actor_path(step))
            ce_eval.compact_head(model, ce_eval.output_ids(self.tokenizers["working"]))
            self.models["working"] = model
        elif not step:
            self.models["working"] = self.original
        self.step = step

    def __call__(self, model, tokenizer, prompts, forced_action=None):
        if not self.step or forced_action or self.phase == "initial":
            return super().__call__(model, tokenizer, prompts, forced_action)
        checkpoint_model = self.models["working"]
        self.models["working"] = self.original
        try:
            output = []
            for prompt in prompts:
                if prompt not in self.full_prompts:
                    output.extend(super().__call__(model, tokenizer, [prompt]))
                    continue
                key = (self.step, prompt)
                if key not in self.change_cache:
                    self.change_cache[key] = one(checkpoint_model, self.tokenizers["working"], prompt, CONTEXT)
                    self.actual_calls += 1
                output.append({**self.change_cache[key], "profile": "actor", "phase": "actor"})
            return output
        finally:
            self.models["working"] = checkpoint_model


def capture_session(decoder, compact):
    if not compact:
        return FullSession
    tok = decoder.tokenizers["working"]

    class Candidate(Session):
        def request(self):
            prompt = super().request()
            if self.history and self.history[-1]["kind"] == "replan":
                full = FullSession.request(self)
                if full != prompt:
                    decoder.full_prompts[prompt] = full
            return prompt

    return partial(Candidate, tokenizer=tok)


def summarize(goals, primary, episodes, decoder):
    ck_eval.check_trajectory(goals, episodes, primary)
    result = measures(episodes)
    result["first_correct"] = sum(r["program_correct"] for r in primary)
    result["first_total"] = len(primary)
    tok = decoder.tokenizers["working"]
    taken = []
    for row in episodes:
        step = cm_eval.after_review(row)
        if step is None:
            continue
        gen = step["generation"]
        is_short = step["prompt"] in decoder.full_prompts
        write = gen["generated_token_ids"][:1] == [ACTION_ID["write"]]
        used = gen["input_tokens"] + len(header_ids(tok, "write")) + len(gen["generated_token_ids"])
        taken.append({
            "id": row["id"], "short": is_short, "prompt": gen["input_tokens"],
            "full_prompt": len(prompt_ids(tok, decoder.full_prompts[step["prompt"]])) if is_short else gen["input_tokens"],
            "kind": step["kind"], "error": gen["codec_error"], "write": write,
            "write_total": used if write and gen["codec_error"] is None else None,
            "passed": row["pass"], "final_code_correct": row["program_correct"],
        })
    short = [x for x in taken if x["short"]]
    complete = [x["write_total"] for x in short if x["write_total"] is not None]
    assert all(x <= limit(tok) for x in (r["prompt"] for r in short))
    assert all(x <= CONTEXT for x in complete)
    result["post_review"] = {
        "episodes": len(taken), "shortened": len(short),
        "median_prompt_saved": median([x["full_prompt"] - x["prompt"] for x in short]) if short else 0,
        "max_short_prompt": max((x["prompt"] for x in short), default=0),
        "max_short_write_total": max(complete, default=0),
        "writes_short_attempted": sum(x["write"] for x in short),
        "writes_short_completed": len(complete),
        "errors": Counter(r["error"] for r in taken if r["error"]),
        "actions_short": Counter(r["kind"] for r in short),
        "rows": taken,
    }
    targets = set(read(PREVIOUS / "preselected.json")["targets"])
    result["target_repairs"] = [r["id"] for r in episodes if r["pass"] and r["id"] in targets]
    return result


def run(split, step, mode, device):
    torch.set_num_threads(2)
    install()
    manifest = check_inputs()
    if split in ("closed", "fresh") and step:
        assert step == read(ROOT / "preselected.json")["audit_step"]
    path = (ROOT if split == "fresh" else PREVIOUS) / f"{split}.jsonl"
    goals = rows(path)
    fingerprint = {"data": sha(path), "translator": sha(cl_eval.model_path(cm_eval.STEP)),
                   "actor": sha(actor_path(step)), "step": step, "mode": mode, "split": split}
    folder = ROOT / "eval" / f"{split}-{mode}-{step:04}"
    complete = folder / "complete.json"
    if complete.exists():
        receipt = read(complete)
        assert receipt["inputs"] == fingerprint
        assert receipt["full_sha256"] == sha(folder / "full.json")
        assert receipt["metrics_sha256"] == sha(folder / "metrics.json")
        return
    started = time.monotonic()
    ck_eval.status(folder, "load", **fingerprint)
    decoder = Decoder(device)
    vm = CachedVM()
    if split == "fresh":
        old = ROOT / "eval/fresh-full-0000/full.json"
        if old.exists():
            baseline = read(old)
        else:
            assert mode == "full" and step == 0
            with patch.object(ce_eval, "ROOT", folder):
                decoder.phase = "initial"
                primary, records = ce_eval.full_records(goals, vm, decoder)
            baseline = {"primary": primary, "records": records}
    else:
        baseline, _ = cm_eval.load_baseline(split)
    primary, records = baseline["primary"], baseline["records"]
    if mode == "full":
        result = records
    else:
        cm_eval.seed_decoder(decoder, primary, records)
        if step:
            compact_path = ROOT / "eval" / f"{split}-short-0000/full.json"
            if compact_path.exists():
                compact_control = read(compact_path)
                cm_eval.seed_decoder(decoder, primary, compact_control["records"])
        with patch.object(ce_eval, "ROOT", folder), patch.multiple(
            bj_eval, generate=decoder, Session=capture_session(decoder, True),
        ), patch.object(bj_eval.core, "mutant", lambda goal, *_: (goal["error_kind"], goal["bad_body"])):
            decoder.set_step(step)
            result = bj_eval.episodes(None, None, goals, {r["id"]: r for r in primary}, vm, "self")
            decoder.set_step(0)
    decoder.verify_weights()
    assert check_inputs() == manifest
    stats = summarize(goals, primary, result, decoder)
    stats.update(actual_calls=decoder.actual_calls, seconds=time.monotonic() - started)
    write(folder / "full.json", {"inputs": fingerprint, "primary": primary, "records": result})
    write(folder / "metrics.json", stats)
    write(complete, {"inputs": fingerprint, "full_sha256": sha(folder / "full.json"),
                     "metrics_sha256": sha(folder / "metrics.json")})
    ck_eval.status(folder, "complete", **{k: v for k, v in stats.items() if k != "post_review"},
                   post_review={k: v for k, v in stats["post_review"].items() if k != "rows"})


def select():
    def metric(split, mode, step):
        folder = ROOT / "eval" / f"{split}-{mode}-{step:04}"
        assert read(folder / "complete.json")["metrics_sha256"] == sha(folder / "metrics.json")
        return read(folder / "metrics.json")

    def retained_ids(split, mode, step):
        return {r["id"] for r in read(ROOT / "eval" / f"{split}-{mode}-{step:04}" / "full.json")["records"]
                if r["pass"] and not r["initially_correct"]}

    targets = set(read(PREVIOUS / "preselected.json")["targets"])
    dev_base = metric("development", "full", 0)
    rec_base = retained_ids("recovery", "full", 0)
    results = []
    for step in MILESTONES:
        dev = metric("development", "short", step)
        rec = metric("recovery", "short", step)
        kept = len(rec_base & retained_ids("recovery", "short", step))
        recovered = len(targets & set(rec["target_repairs"]))
        safe = dev["accepted_false_DONE"] <= dev_base["accepted_false_DONE"] and dev["corruption"] <= dev_base["corruption"]
        target_fit = all(item["short"] and item["write_total"] <= CONTEXT for item in rec["post_review"]["rows"]
                         if item["id"] in rec["target_repairs"] and item["write_total"] is not None)
        good = safe and recovered == len(targets) and kept == len(rec_base) and target_fit
        quality = (good, safe, recovered, kept, dev["repairs"], dev["completed"],
                   -dev["accepted_false_DONE"], -dev["corruption"], -step)
        results.append({"step": step, "key": quality, "targets": recovered, "retained": kept,
                        "dev_repairs": dev["repairs"], "dev_false_DONE": dev["accepted_false_DONE"],
                        "dev_corruption": dev["corruption"], "passes_selection": good})
    best = max(results, key=lambda x: x["key"])
    write(ROOT / "preselected.json", {"audit_step": best["step"], "passes_selection": best["passes_selection"],
                                      "candidates": results, "used_closed": False})
    print(best, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("split", choices=("recovery", "development", "closed", "fresh", "select"))
    parser.add_argument("--step", type=int, default=0)
    parser.add_argument("--mode", choices=("full", "short"), default="short")
    parser.add_argument("--device", default="cuda:0")
    args = parser.parse_args()
    if args.split == "select":
        select()
    else:
        run(args.split, args.step, args.mode, args.device)
