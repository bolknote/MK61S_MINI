"""Test a short prompt with one independent SPEC comparison after review."""

import argparse
from functools import lru_cache
import time
from unittest.mock import patch

import torch

import bj_eval
import ce_eval
import ck_eval
import cm_eval
from aq_protocol import prompt_ids
from ar_spec import verify
from ay_common import read, rows, sha, write
from bj_runtime import Session as FullSession
from bl_spec import install
from bl_vm import CachedVM
from cg_language import parse_task
from ci_runtime import power_key
from cn_data import PREVIOUS, ROOT
from cn_eval import Decoder, actor_path, summarize
from cn_runtime import limit, needs_room, shortened
from cn_train import check_inputs
from bt_decode import one


@lru_cache(maxsize=2048)
def independent_spec(text, angle):
    return parse_task(text, angle)


def review_status(task, hypothesis):
    independent = independent_spec(task["task"], task["angle"])
    if independent is None:
        return None
    return hypothesis is not None and power_key(independent) == power_key(hypothesis)


def make_session(decoder, notify, correct_action):
    tokenizer = decoder.tokenizers["working"]

    class Session(FullSession):
        def request(self):
            full = super().request()
            if not self.history or self.history[-1]["kind"] != "replan":
                return full
            if not needs_room(full, self.history[-1]["body"], tokenizer):
                return full
            compact = shortened(full, self.task["task"], tokenizer)
            agrees = review_status(self.task, self.declared_spec)
            if notify:
                note = {True: "условие и SPEC совпадают", False: "условие и SPEC расходятся",
                        None: "проверка SPEC недоступна"}[agrees]
                marker = "После пересмотра SPEC доступны WRITE, RUN, DONE и UNSURE."
                compact = compact.replace(marker, f"Проверка: {note}.\n" + marker, 1)
            if len(prompt_ids(tokenizer, compact)) > limit(tokenizer):
                return full
            decoder.full_prompts[compact] = full
            if agrees is False:
                decoder.blocked.add(compact)
            if agrees is True and correct_action:
                result = verify(self.vm, self.body, self.pool, self.declared_spec, self.checker_inputs)
                if result["status"] == "FAIL" and not self.eligibility()[1]:
                    decoder.pending_write.add(compact)
            return compact

    return Session


class GuardedDecoder(Decoder):
    def __init__(self, device):
        super().__init__(device)
        self.blocked = set()
        self.pending_write = set()
        self.retries = {}

    def __call__(self, model, tokenizer, prompts, forced_action=None):
        results = super().__call__(model, tokenizer, prompts, forced_action)
        for prompt, output in zip(prompts, results):
            if prompt in self.blocked and output["action"] in ("write", "done"):
                output.update(action="unsure", body=[], guard_blocked=True)
            elif prompt in self.pending_write and output["action"] in ("done", "unsure"):
                # An independent parse agreed with the hypothesis, and the
                # emulator falsified the current program. Ask for one proposal.
                original = output["action"]
                if prompt not in self.retries:
                    self.retries[prompt] = one(self.models["working"], self.tokenizers["working"],
                                               prompt, ce_eval.CONTEXT, forced_action="write")
                output.update(self.retries[prompt], retry_after=original)
        return results


def run(split, step, notify, correct_action):
    torch.set_num_threads(2)
    install()
    manifest = check_inputs()
    assert step == read(ROOT / "preselected.json")["audit_step"]
    path = (ROOT if split == "fresh" else PREVIOUS) / f"{split}.jsonl"
    dataset = rows(path)
    variant = "retry" if correct_action else "cue" if notify else "guard"
    folder = ROOT / "review-check" / f"{split}-{variant}"
    fingerprint = {"dataset": sha(path), "actor": sha(actor_path(step)), "notify": notify,
                   "correct_action": correct_action, "source": sha(__file__)}
    if (folder / "complete.json").exists():
        assert read(folder / "complete.json")["inputs"] == fingerprint
        return
    started = time.monotonic()
    ck_eval.status(folder, "load", **fingerprint)
    decoder = GuardedDecoder("cuda:0")
    vm = CachedVM()
    if split == "fresh":
        baseline = read(ROOT / "eval/fresh-full-0000/full.json")
    else:
        baseline, _ = cm_eval.load_baseline(split)
    primary = baseline["primary"]
    cm_eval.seed_decoder(decoder, primary, baseline["records"])
    # Reuse only generations from the parent. The guarded model's actual action
    # distribution remains recorded, even when a proposed action is denied.
    parent = read(ROOT / "eval" / f"{split}-short-0000/full.json")
    cm_eval.seed_decoder(decoder, primary, parent["records"])
    with patch.object(ce_eval, "ROOT", folder), patch.multiple(
        bj_eval, Session=make_session(decoder, notify, correct_action), generate=decoder,
    ), patch.object(bj_eval.core, "mutant", lambda g, *_: (g["error_kind"], g["bad_body"])):
        decoder.set_step(step)
        result = bj_eval.episodes(None, None, dataset, {r["id"]: r for r in primary}, vm, "self")
        decoder.set_step(0)
    decoder.verify_weights()
    assert check_inputs() == manifest
    stats = summarize(dataset, primary, result, decoder)
    stats["blocked"] = [row["id"] for row in result if any(h.get("generation", {}).get("guard_blocked")
                                                        for h in row["history"])]
    stats["retried"] = [row["id"] for row in result if any(h.get("generation", {}).get("retry_after")
                                                        for h in row["history"])]
    stats["seconds"] = time.monotonic() - started
    write(folder / "metrics.json", stats)
    write(folder / "full.json", {"primary": primary, "records": result})
    write(folder / "complete.json", {"inputs": fingerprint, "metrics_sha256": sha(folder / "metrics.json"),
                                     "full_sha256": sha(folder / "full.json")})
    ck_eval.status(folder, "complete", **{k: v for k, v in stats.items() if k != "post_review"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("split", choices=("recovery", "development", "closed", "fresh"))
    parser.add_argument("step", type=int)
    parser.add_argument("--cue", action="store_true")
    parser.add_argument("--retry", action="store_true")
    args = parser.parse_args()
    run(args.split, args.step, args.cue, args.retry)
