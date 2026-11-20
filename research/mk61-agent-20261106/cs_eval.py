"""Compare grammar coverage and the direct compiler on the same Q4 inputs."""

from collections import Counter
from unittest.mock import patch

import torch

import bj_eval
import ce_eval
import ck_eval
import cl_eval
import cm_eval
import cn_eval
import cq_eval
import cr_eval
from ar_spec import equivalent, verify
from ay_common import read, rows, sha, write
from bl_spec import install
from bl_vm import CachedVM
from ce_finish import transitions
from cn_runtime import CONTEXT
from cq_eval import load_actor
from cq_language import independent_spec
from cr_runtime import make_session as previous_session
from cs_data import PREVIOUS, ROOT
from cs_language import parse_task
from cs_runtime import checked_program, make_session


MODES = ("baseline", "nested", "nested-direct")


def previous_primary(decoder):
    root = PREVIOUS / "eval/closed"
    seal = read(root / "complete.json")
    mode = "bounded-compiler"
    for name in ("full.json", "metrics.json"):
        path = f"{mode}/{name}"
        assert sha(root / path) == seal["files"][path]
    old = read(root / mode / "full.json")
    short_ids = {r["id"] for r in read(root / mode / "metrics.json")["post_review"]["rows"] if r["short"]}
    records = []
    for row in old["records"]:
        skip = cm_eval.after_review(row)["prompt"] if row["id"] in short_ids else None
        history = [h for h in row["history"] if h.get("generation", {}).get("profile") in ("actor", "translator")
                   and h["generation"]["phase"] != "forced_write" and h["prompt"] != skip]
        records.append({**row, "history": history})
    cm_eval.seed_decoder(decoder, old["primary"], records)
    return old["primary"]


def compile_primary(goal, fallback, vm):
    text = goal["task"]
    angle = goal["spec"]["angle"]
    pool = goal["pool"]
    spec = parse_task(text, angle)
    runtime = [*goal["public_inputs"], *goal["checker_inputs"]]
    program = checked_program(spec, pool, vm, runtime)
    if program is None:
        return fallback
    # The held-out target first appears here, after the compiler's decision.
    audit = goal["audit_inputs"]
    grade = verify(vm, program, pool, goal["spec"], audit)
    generation = {"profile": "harness", "phase": "direct_initial", "action": "write", "codec_error": None,
                  "input_tokens": 0, "generated_token_ids": [], "body": program, "format": "hex"}
    return {**fallback, "prompt": "", "generation": generation, "codec_error": None, "declared_spec": spec,
            "program": program, "program_correct": grade["status"] == "TESTED",
            "intent": equivalent(spec, goal["spec"], audit), "task_audit": grade,
            "own_spec_consistency": verify(vm, program, pool, spec, audit)}


def measures(goals, records, primary, decoder, parser):
    with (patch.object(cr_eval, "independent_spec", parser), patch.object(cq_eval, "independent_spec", parser)):
        scores = cr_eval.add_metrics(goals, primary, records, decoder)
        scores["parser"] = cq_eval.parse_audit(goals)
    calls = lambda g: g.get("profile") in ("actor", "translator") and g.get("codec_error") != "context_overflow"
    inputs = sum(g["generation"]["input_tokens"] for g in primary if calls(g["generation"]))
    strata = {}
    by_task = {g["id"]: g for g in goals}
    for row in records:
        goal = by_task[row["task_id"]]
        status = "parsed" if parser(goal["task"], goal["spec"]["angle"]) is not None else "unparsed"
        group = strata.setdefault(f'{goal["family"]}:{status}', Counter())
        group["correct_total" if row["initially_correct"] else "wrong_total"] += 1
        if row["pass"]:
            group["correct_done" if row["initially_correct"] else "repairs"] += 1
        for event in row["history"]:
            generation = event.get("generation", {})
            if calls(generation):
                inputs += generation["input_tokens"] * (1 + bool(generation.get("retry_after")))
            if event.get("direct_compiler"):
                group["direct_repair_attempts"] += 1
                if row["pass"] and not row["initially_correct"] and event["kind"] == "write":
                    group["direct_repairs"] += 1
    scores.update(strata=strata, input_tokens=inputs,
                  direct_first_programs=sum(r["generation"]["phase"] == "direct_initial" for r in primary))
    return scores


def evaluate(split, device):
    assert split in ("diagnostic", "closed")
    diagnostic = split == "diagnostic"
    path = (PREVIOUS if diagnostic else ROOT) / "closed.jsonl"
    folder = ROOT / "eval" / split
    receipt = folder / "complete.json"
    actor = load_actor(False)
    inputs = {"data": sha(path), "actor": sha(actor), "working": sha(ce_eval.PROFILES / "working/model.mkqb"),
              "translator": sha(cl_eval.model_path(cm_eval.STEP)), "context": CONTEXT}
    if receipt.is_file():
        assert read(receipt)["inputs"] == inputs
        return
    torch.set_num_threads(2)
    install()
    goals = rows(path)
    vm = CachedVM()
    decoder = cr_eval.Decoder(device)
    decoder.reset_policy()
    ck_eval.status(folder, "initial", split=split, tasks=len(goals))
    if diagnostic:
        neural = previous_primary(decoder)
    else:
        decoder.phase = "initial"
        with patch.object(ce_eval, "ROOT", folder), patch.multiple(bj_eval.core, generate=decoder, render=ce_eval.render):
            neural = bj_eval.core.primary(None, None, goals, "spec", vm)
    decoder.phase = "full_cycle"
    with patch.object(cn_eval, "actor_path", lambda _: actor):
        decoder.set_step(900)
    frozen = ce_eval.frozen_digest(decoder.models["working"])
    baseline = None
    files = {}
    for mode in MODES:
        decoder.reset_policy()
        dest = folder / mode
        ck_eval.status(dest, "full_cycle", split=split, tasks=len(goals))
        direct = mode == "nested-direct"
        primary = ([compile_primary(g, n, vm) for g, n in zip(goals, neural, strict=True)] if direct else neural)
        initial = {r["id"]: r for r in primary}
        session = (previous_session(decoder, use_compiler=True) if mode == "baseline"
                   else make_session(decoder, direct=direct))
        with (patch.object(ce_eval, "ROOT", dest), patch.multiple(bj_eval, Session=session, generate=decoder),
              patch.object(bj_eval.core, "mutant", lambda goal, *_: (goal["error_kind"], goal["bad_body"]))):
            records = bj_eval.episodes(None, None, goals, initial, vm, "self")
        parser = independent_spec if mode == "baseline" else parse_task
        stats = measures(goals, records, primary, decoder, parser)
        if baseline is None:
            baseline = records
        else:
            stats["paired"] = transitions(baseline, records)
        write(dest / "metrics.json", stats)
        write(dest / "full.json", {"mode": mode, "inputs": inputs, "primary": primary, "records": records})
        files.update({f"{mode}/{name}": sha(dest / name) for name in ("metrics.json", "full.json")})
        print(split, mode, {k: stats[k] for k in ("first_correct", "repairs", "completed", "accepted_false_DONE",
                                                "corruption", "clarifications", "unsure", "neural_calls", "input_tokens",
                                                "direct_first_programs", "parser", "recovery")}, flush=True)
    assert frozen == ce_eval.frozen_digest(decoder.models["working"])
    decoder.set_step(0)
    decoder.verify_weights()
    assert inputs["data"] == sha(path) and inputs["actor"] == sha(actor)
    write(receipt, {"inputs": inputs, "files": files})
