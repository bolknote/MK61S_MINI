#!/usr/bin/env python3
"""Continue TinyTalk using direct conversational targets and optional DPO, with Q4 throughout."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import random
import shutil
import time

from common import core, quantize, logps, load_model, qat_modules
from evaluate import assess, SCENARIOS, TEST_SCENARIOS
from grade import calibrate


def run(args):
    import torch
    from torch.nn import functional as F
    output = Path(args.output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Use a new run directory")
    output.mkdir(parents=True, exist_ok=True)
    model, tokenizer, device = load_model(args)
    reference, _, _ = load_model(args)
    reference.eval().requires_grad_(False);quantize.roundtrip(reference)
    qat = qat_modules(model,cuda_graphs=getattr(args,'cuda_qat_graphs',False)) if args.qat_start == 1 else None
    def original_weight(module):
        return module.parametrizations.weight.original if hasattr(module, "parametrizations") else module.weight
    frozen_words = frozen_positions = frozen_ids = None
    model.config.tinytalk_word_embeddings_frozen_in_sft = bool(args.freeze_word_embeddings)
    model.config.tinytalk_expanded_mlp_only = bool(args.expanded_mlp_only)
    if args.freeze_word_embeddings:
        embedding = original_weight(model.transformer.wte)
        allowed = set(getattr(model.config, "tinytalk_intent_token_ids", {}).values())
        frozen_ids = [i for i in range(embedding.shape[0]) if i not in allowed]
        frozen_words = embedding.detach()[frozen_ids].clone()
        mask = torch.zeros((embedding.shape[0], 1), device=device)
        mask[list(allowed)] = 1
        embedding.register_hook(lambda gradient: gradient * mask)
        position = original_weight(model.transformer.wpe)
        position.requires_grad_(False);frozen_positions = position.detach().clone()
        model.config.tinytalk_word_embeddings_frozen_in_sft = True
    frozen_layers = []
    if args.train_last_layers:
        assert 0 < args.train_last_layers <= model.config.num_layers
        for block in model.transformer.h[:-args.train_last_layers]:
            block.requires_grad_(False)
            frozen_layers.extend((parameter, parameter.detach().clone()) for parameter in block.parameters())
        model.config.tinytalk_conversation_train_last_layers = args.train_last_layers
    expanded_guard=None
    if args.expanded_mlp_only:
        assert args.qat_start==1 and not args.freeze_word_embeddings
        assert args.train_last_layers in [0,8]
        from expanded_only import ExpandedOnly
        expanded_guard=ExpandedOnly(model)
    context = getattr(model.config, "tinytalk_runtime_context", 256)
    source = core.read_rows(Path(args.data) / "train.jsonl")
    encoded, skipped = core.encode_rows(tokenizer, source, context)
    replay = [row for row in encoded if row[2] == "replay"]
    groups = {kind: [row for row in encoded if row[2] == kind] for kind in sorted({row[2] for row in encoded if row[2] != "replay"})}
    cases = core.read_rows(Path(args.suite) / "dev.jsonl")
    partition_sizes = [len(cases)]
    scenarios = None
    conversation_sizes = [18]
    if args.opened_audit_development:
        extra = core.read_rows(Path(args.suite) / "test.jsonl")
        partition_sizes.append(len(extra));cases += extra
        scenarios = SCENARIOS + TEST_SCENARIOS;conversation_sizes.append(18)
    if args.additional_development:
        assert args.opened_audit_development and args.additional_scenarios
        extra = core.read_rows(args.additional_development)
        partition_sizes.append(len(extra));cases += extra
        extra_scenarios = json.loads(Path(args.additional_scenarios).read_text())
        scenarios += extra_scenarios;conversation_sizes.append(3 * len(extra_scenarios))
    def development(qat_state):
        result = assess(model, tokenizer, device, cases, qat_state, output / "grade-cache", args.mode,
                        scenarios)
        if args.opened_audit_development:
            boundaries = [];at = 0
            for size in partition_sizes:
                boundaries.append((at,at+size));at += size
            rates, contexts = [], []
            contextual = {'remember_name','follow_hobby','correction','decline_idea','follow_story','name','pet','correct','reject','project'}
            for start, end in boundaries:
                grades = result['direct']['details'][start:end]
                rates.append(sum(g['pass'] for g in grades) / len(grades))
                context = [g for c,g in zip(cases[start:end],grades) if c.get('family') in contextual]
                contexts.append(sum(g['pass'] for g in context) / len(context))
            multi = result['multi_turn']['details']
            turn_rates = [];at = 0
            for size in conversation_sizes:
                turn_rates.append(sum(g['pass'] for g in multi[at:at+size]) / size);at += size
            result['development_partitions'] = {'previous_dev_direct': rates[0], 'opened_audit_direct': rates[1],
                    'context_rates': contexts, 'multi_turn_rates': turn_rates, 'new_reserved_audit_opened': False}
            if len(rates)>2:result['development_partitions']['opened_audit2_direct'] = rates[2]
            result['goal_met'] = result['goal_met'] and min(rates) >= .8 and min(contexts) >= .72 and min(turn_rates) >= .78
        return result
    assert replay and all(groups.values())
    pairs = []
    if args.mode in ["dpo", "hard_sft"]:
        manifest = json.loads((Path(args.pairs) / "manifest.json").read_text())
        assert manifest["reference_checkpoint_sha256"] == core.digest(Path(args.model) / "model.safetensors")
        for row in core.read_rows(Path(args.pairs) / "train.jsonl"):
            good, _ = core.encode_rows(tokenizer, [dict(row, target=row["chosen"])], context)
            bad, _ = core.encode_rows(tokenizer, [dict(row, target=row["rejected"])], context)
            if not good or not bad:continue
            pairs.append((good[0], bad[0], row["reference_chosen_logp"], row["reference_rejected_logp"]))
    report = {"settings": vars(args), "source_checkpoint_sha256": core.digest(Path(args.model) / "model.safetensors"),
              "source_code_sha256": {p.name: core.digest(p) for p in Path(__file__).resolve().parent.glob("*.py")},
              "parameters": sum(p.numel() for p in model.parameters()), "runtime_context": context, "training_rows": len(encoded), "skipped": skipped,
              "pairs": len(pairs), "data": json.loads((Path(args.data) / "manifest.json").read_text()),
              "target": {"acceptable_replies": 0.8, "context": 0.72, "multi_turn": 0.78},
              "calibration": calibrate(output / "grade-cache"), "test_opened": args.opened_audit_development,
              "new_reserved_audit_opened": False, "history": [], "best_step": 0}
    torch.cuda.reset_peak_memory_stats() if device == "cuda" else None
    baseline = development(qat)
    report["baseline"] = baseline
    def ranking(result):
        if args.balanced_selection:
            p=result.get('development_partitions',{})
            direct=[p[k] for k in ['previous_dev_direct','opened_audit_direct','opened_audit2_direct'] if k in p] or [result['direct']['pass_rate']]
            ratios=[v/.8 for v in direct]+[v/.72 for v in p.get('context_rates',[result['context_pass_rate']])]+[v/.78 for v in p.get('multi_turn_rates',[result['multi_turn']['pass_rate']])]
            return (int(result['goal_met']),min(ratios),result['selection_score'],result['direct']['mean_score'])
        return (int(result['goal_met']),result['selection_score'],result['direct']['mean_score'])
    report['selection_policy']='Worst normalized development partition, then weighted quality' if args.balanced_selection else 'Weighted direct/conversation quality after target gate'
    if expanded_guard:report['expanded_only']=expanded_guard.summary()
    best = ranking(baseline)
    def checkpoint(path):
        if qat:
            quantize.save_qat_checkpoint(model, path, qat)
        else:
            model.save_pretrained(path, safe_serialization=True)
        tokenizer.save_pretrained(path);quantize.copy_notices(args.model, path)
        extra = Path(args.model) / 'LANGUAGE_DATA.md'
        if extra.exists():shutil.copyfile(extra, Path(path) / extra.name)
    checkpoint(output / "best")
    embedding_ids = {id(original_weight(module)) for module in [model.transformer.wte, model.transformer.wpe]}
    optimizer = torch.optim.AdamW([
        {"params": [p for p in model.parameters() if id(p) not in embedding_ids], "lr_scale": 1.0},
        {"params": [p for p in model.parameters() if id(p) in embedding_ids], "lr_scale": args.embedding_lr_scale,
         "weight_decay": 0.0 if args.freeze_word_embeddings or expanded_guard else 0.01},
    ], lr=args.lr, weight_decay=0.0 if expanded_guard else 0.01)
    rng = random.Random(args.seed)
    kinds = sorted(groups)
    probabilities = {"idea": 0.14, "ask": 0.10, "emotion": 0.12, "chat": 0.12,
                     "followup": 0.12, "correction": 0.08, "clarify": 0.06, "role": 0.08,
                     "greeting": 0.04, "identity": 0.04, "sharing": 0.08, "preference": 0.06, "game": 0.08}
    weights = [1.0 if args.uniform_groups else probabilities.get(k, 0.1) for k in kinds]
    if args.natural_fraction or args.grounded_fraction or args.contrastive_fraction or args.branched_fraction or args.prefix_fraction:
        special = {k: v for k,v in [('natural_dialogue',args.natural_fraction), ('grounded_qa',args.grounded_fraction),
                                    ('contrastive_facts',args.contrastive_fraction),
                                    ('branched_dialogue',args.branched_fraction),
                                    ('branched_prefix',args.prefix_fraction)] if v}
        assert all(0 < v < 1 and k in groups for k,v in special.items())
        remaining = 1 - sum(special.values())
        assert remaining > 0 and len(kinds) > len(special)
        weights = [special.get(k, remaining / (len(kinds) - len(special))) for k in kinds]
    started = time.monotonic();consecutive_goal = 0
    for step in range(1, args.steps + 1):
        if step == args.qat_start and qat is None:
            qat = qat_modules(model,cuda_graphs=getattr(args,'cuda_qat_graphs',False))
        model.train();optimizer.zero_grad(set_to_none=True)
        amp = torch.autocast("cuda", dtype=torch.bfloat16) if device == "cuda" else core.nullcontext()
        pref = torch.tensor(0., device=device)
        if args.mode in ["dpo", "hard_sft"] and rng.random() < 0.7:
            selected = [rng.choice(pairs) for _ in range(args.batch_size // 2)]
            chosen, rejected, old_good, old_bad = zip(*selected)
            with amp:
                good_logp, ce, _, _ = logps(model, chosen, tokenizer, device, args.intent_weight, args.example_balanced_loss)
                if args.mode == 'dpo':
                    bad_logp, _, _, _ = logps(model, rejected, tokenizer, device)
                    reference_margin = torch.tensor(old_good, device=device) - torch.tensor(old_bad, device=device)
                    margin = good_logp - bad_logp - reference_margin
                    pref = -F.logsigmoid(args.beta * margin).mean()
                loss = ce + args.preference_weight * pref
        else:
            rows = [rng.choice(replay) if rng.random() < args.replay_fraction else rng.choice(groups[rng.choices(kinds, weights=weights)[0]]) for _ in range(args.batch_size)]
            with amp:
                _, ce, logits, _ = logps(model, rows, tokenizer, device, args.intent_weight, args.example_balanced_loss)
                with torch.no_grad():
                    _, _, ref_logits, _ = logps(reference, rows, tokenizer, device)
                kl = F.kl_div(F.log_softmax(logits.float(), -1), F.softmax(ref_logits.float(), -1), reduction="batchmean")
                loss = ce + args.kl * kl
        if not torch.isfinite(loss):
            raise ValueError("Non-finite loss")
        loss.backward();norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.)
        if not torch.isfinite(norm):
            raise ValueError("Non-finite gradient")
        rate = args.lr * min(1., step / 100) * (0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * step / args.steps)))
        for group in optimizer.param_groups:
            group["lr"] = rate * group["lr_scale"]
        optimizer.step()
        if expanded_guard:expanded_guard.restore()
        if step == 1 or step % 200 == 0:
            print(json.dumps({"step": step, "ce": float(ce.detach()), "dpo": float(pref.detach()),
                              "seconds": round(time.monotonic() - started, 1)}), flush=True)
        if step % args.eval_every == 0 or step == args.steps:
            if expanded_guard:
                expanded_guard.verify();report['inherited_parameters_verified']=True
            if args.freeze_word_embeddings:
                assert torch.equal(original_weight(model.transformer.wte).detach()[frozen_ids], frozen_words)
                assert torch.equal(original_weight(model.transformer.wpe).detach(), frozen_positions)
                report["frozen_embeddings_verified"] = True
            if frozen_layers:
                assert all(torch.equal(parameter.detach(), original) for parameter, original in frozen_layers)
                report["frozen_layers_verified"] = True
            result = development(qat)
            result.update(step=step, seconds=time.monotonic() - started)
            report["history"].append(result)
            score = ranking(result)
            if score > best and result["malformed"] <= 3:
                best = score;report["best_step"] = step;checkpoint(output / "best")
            consecutive_goal = consecutive_goal + 1 if result["goal_met"] else 0
            core.save(output / "training.json", report)
            print(json.dumps({"validation_step": step, "acceptable": result["direct"]["pass_rate"],
                              "context": result["context_pass_rate"], "multi_turn": result["multi_turn"]["pass_rate"],
                              "best_step": report["best_step"], "goal_met": result["goal_met"],
                              "errors": dict(Counter(r["error"] for r in result["direct"]["details"] if not r["pass"]))}), flush=True)
            if consecutive_goal >= 2:
                report["early_stop_reason"] = "Quality target met at two consecutive development checks"
                break
    checkpoint(output / "last")
    if expanded_guard:expanded_guard.verify()
    report["seconds"] = time.monotonic() - started
    report["best_sha256"] = core.digest(output / "best/model.safetensors")
    report["source_unchanged"] = report["source_checkpoint_sha256"] == core.digest(Path(args.model) / "model.safetensors")
    if device == "cuda":
        report["gpu"] = {"peak_allocated_bytes": torch.cuda.max_memory_allocated(), "peak_reserved_bytes": torch.cuda.max_memory_reserved()}
    core.save(output / "training.json", report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["sft", "dpo", "hard_sft"], required=True)
    parser.add_argument("--model", default="/previous")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--seed", type=int, default=68021)
    parser.add_argument("--data", default="data")
    parser.add_argument("--suite", default="suite")
    parser.add_argument("--pairs", default="pairs")
    parser.add_argument("--output", required=True)
    parser.add_argument("--steps", type=int, default=8000)
    parser.add_argument("--eval-every", type=int, default=1000)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=3e-5)
    parser.add_argument("--beta", type=float, default=0.1)
    parser.add_argument("--preference-weight", type=float, default=0.5)
    parser.add_argument("--kl", type=float, default=0.03)
    parser.add_argument("--replay-fraction", type=float, default=0.15)
    parser.add_argument("--qat-start", type=int, default=1)
    parser.add_argument("--embedding-lr-scale", type=float, default=0.15)
    parser.add_argument("--intent-weight", type=float, default=1.0)
    parser.add_argument("--uniform-groups", action="store_true")
    parser.add_argument("--natural-fraction", type=float, default=0,
                        help="Explicit probability of complete natural dialogues; divide the rest among old acts")
    parser.add_argument("--grounded-fraction", type=float, default=0,
                        help="Explicit probability of grounded reading exercises")
    parser.add_argument("--contrastive-fraction", type=float, default=0,
                        help="Explicit probability of balanced known/unknown questions on the same history")
    parser.add_argument("--branched-fraction", type=float, default=0,
                        help="Explicit probability of varied final requests sharing a conversational prefix")
    parser.add_argument("--prefix-fraction", type=float, default=0,
                        help="Explicit probability of fully vetted earlier turns of the contrasted dialogues")
    parser.add_argument("--example-balanced-loss", action="store_true",
                        help="Average target loss within each example before the batch, preserving short factual answers")
    parser.add_argument("--freeze-word-embeddings", action="store_true")
    parser.add_argument("--expanded-mlp-only", action="store_true",
                        help="Train only added MLP rows/columns; restore and verify every inherited parameter")
    parser.add_argument("--train-last-layers", type=int, default=0)
    parser.add_argument("--opened-audit-development", action="store_true",
                        help="The first audit is now observed; require both old partitions and reserve a new final audit.")
    parser.add_argument("--additional-development", help="Another previously opened audit; require this partition to pass separately")
    parser.add_argument("--additional-scenarios", help="Conversation scripts for the additional opened partition")
    parser.add_argument("--balanced-selection", action="store_true",help="Preserve progress on the worst development partition instead of trading it for easier prompts")
    parser.add_argument('--cuda-qat-graphs',action='store_true',help='Replay the original Q4 CUDA operations without changing arithmetic')
    run(parser.parse_args())
