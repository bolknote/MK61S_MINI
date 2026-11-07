#!/usr/bin/env python3
"""Gradient-free edits to TinyTalk, selected on calibration conversations.

The holdout uses different entity values and is evaluated only after selection.
No optimizer, backpropagation, extra parameters or changes to the prompt format.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "squeal-chat-20261105"))
from chat import PROFILES, manifest, render_prompt

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

PROFILE = PROFILES["tinytalk"]
SOURCE = PROFILE["directory"]
DESTINATION = SOURCE.parent / "surgery" / "selected"
REPORT = HERE / "weight-surgery.json"
ORIGINAL_SHA256 = "d7510ceac1d4f2a7d00b6f2da92cdce38706faa60a96c60884819d00ef58af77"


def datasets():
    # Eight counterfactual pairs: changing only the stated value must change
    # the answer. Holdout values below are not used in any selection score.
    templates = [
        ("person", "My name is {}.", "What is my name?", "Your name is {}.",
         ["Alice", "Tom"], ["Emma", "Jack", "Nora", "Sam"], ["Mike", "Sue"]),
        ("dog", "My dog is named {}.", "What is my dog's name?", "Your dog's name is {}.",
         ["Milo", "Ruby"], ["Buddy", "Oscar", "Daisy", "Max"], ["Rex", "Spot"]),
        ("color", "My favorite color is {}.", "What is my favorite color?", "Your favorite color is {}.",
         ["red", "green"], ["yellow", "purple", "orange", "white"], ["blue", "black"]),
        ("toy", "My favorite toy is a {}.", "What is my favorite toy?", "Your favorite toy is a {}.",
         ["kite", "ball"], ["truck", "train", "boat", "doll"], ["car", "bear"]),
        ("city", "I live in {}.", "Where do I live?", "You live in {}.",
         ["London", "Paris"], ["Berlin", "Rome", "Boston", "Denver"], ["Tokyo", "Madrid"]),
        ("number", "I have {} apples.", "How many apples do I have?", "You have {} apples.",
         ["three", "five"], ["one", "two", "four", "six"], ["seven", "eight"]),
        ("day", "Our picnic is {}.", "When is our picnic?", "Your picnic is {}.",
         ["Monday", "Friday"], ["Tuesday", "Thursday", "Sunday", "tomorrow"], ["Saturday", "Wednesday"]),
        ("food", "My favorite food is {}.", "What is my favorite food?", "Your favorite food is {}.",
         ["pizza", "soup"], ["bread", "pasta", "rice", "salad"], ["cake", "fish"]),
    ]
    final_holdout = {
        "person": ["Bob", "Eve", "Lily", "John"],
        "dog": ["Coco", "Lucky", "Pepper", "Rocky"],
        "color": ["pink", "brown", "gray", "gold"],
        "toy": ["robot", "puzzle", "drum", "plane"],
        "city": ["Milan", "Dublin", "Oslo", "Miami"],
        "number": ["nine", "ten", "eleven", "twelve"],
        "day": ["today", "tonight", "next week", "this weekend"],
        "food": ["meat", "cheese", "beans", "noodles"],
    }
    calibration, holdout = [], []
    for category, intro, question, sentence, cal, test, distractors in templates:
        test = final_holdout[category]
        assert not set(cal + distractors) & set(test)
        for destination, values, pool in ((calibration, cal, cal + distractors),
                                          (holdout, test, test)):
            for value in values:
                messages = [{"role": "user", "content": intro.format(value)},
                            {"role": "assistant", "content": "Thanks for telling me."},
                            {"role": "user", "content": question}]
                destination.append({"category": category, "value": value,
                                    "messages": messages, "answer": sentence.format(value),
                                    "choices": [sentence.format(v) for v in pool],
                                    "choice_values": list(pool)})
    guards = ["Hello! How are you?", "What do you like to do for fun?",
              "I had a good day at school.", "I am feeling sad today.",
              "Would you like to play a game?", "Do you like dogs?",
              "What is your favorite story?", "Thank you for talking to me."]
    return calibration, holdout, guards


def contains(text, value):
    aliases = {"one": "1", "two": "2", "three": "3", "four": "4",
               "five": "5", "six": "6", "seven": "7", "eight": "8",
               "nine": "9", "ten": "10", "eleven": "11", "twelve": "12"}
    return any(re.search(r"(?<!\w)" + re.escape(v) + r"(?!\w)", text, re.I)
               for v in (value, aliases[value]) if v) if value in aliases else bool(
                   re.search(r"(?<!\w)" + re.escape(value) + r"(?!\w)", text, re.I))


def speaker_confused(text, category, value):
    prefixes = {"person": r"(?:my name is|i'm|i am)", "dog": r"my dog's name is",
                "color": r"(?:my favorite color is|i like|i love)",
                "toy": r"(?:my favorite toy is|i like|i love)",
                "food": r"(?:my favorite food is|i like|i love)",
                "city": r"i live in", "number": r"i have"}
    return category in prefixes and bool(re.search(
        r"\b" + prefixes[category] + r"\s+(?:(?:a|an|the)\s+)?" + re.escape(value) + r"\b", text, re.I))


def bad_generation(reply):
    if not reply["ended_with_eos"] or not reply["text"]:
        return True
    words = re.findall(r"[\w']+", reply["text"].lower())
    trigrams = [tuple(words[i:i+3]) for i in range(len(words)-2)]
    return len(trigrams) != len(set(trigrams))


class Engine:
    def __init__(self):
        torch.set_num_threads(2)
        torch.manual_seed(42)
        self.tokenizer = AutoTokenizer.from_pretrained(SOURCE, local_files_only=True,
                                                      trust_remote_code=False)
        self.tokenizer.pad_token = self.tokenizer.eos_token
        self.tokenizer.padding_side = "left"
        self.model = self.load(SOURCE)

    @staticmethod
    def load(path):
        return AutoModelForCausalLM.from_pretrained(
            path, local_files_only=True, trust_remote_code=False, dtype=torch.float32,
            attn_implementation="eager").eval().requires_grad_(False)

    def prompt(self, messages):
        return render_prompt(self.tokenizer, messages, "tinytalk")

    @torch.inference_mode()
    def generate(self, messages_list, maximum=24):
        result = []
        for start in range(0, len(messages_list), 8):
            prompts = [self.prompt(m) for m in messages_list[start:start + 8]]
            batch = self.tokenizer(prompts, padding=True, add_special_tokens=False,
                                   return_tensors="pt")
            assert batch.input_ids.shape[1] + maximum <= 256
            output = self.model.generate(
                **batch, max_new_tokens=maximum, do_sample=False, use_cache=True,
                logits_to_keep=1, pad_token_id=self.tokenizer.eos_token_id,
                eos_token_id=self.tokenizer.eos_token_id)
            for row in output[:, batch.input_ids.shape[1]:]:
                ids = row.tolist()
                ended = self.tokenizer.eos_token_id in ids
                if ended:
                    ids = ids[:ids.index(self.tokenizer.eos_token_id) + 1]
                result.append({"text": self.tokenizer.decode(ids, skip_special_tokens=True).strip(),
                               "raw_text": self.tokenizer.decode(ids), "token_ids": ids,
                               "ended_with_eos": ended})
        return result

    def completion_rows(self, tasks):
        rows = []
        for task in tasks:
            prefix = self.tokenizer.encode(self.prompt(task["messages"]), add_special_tokens=False)
            for answer in task["choices"]:
                ids = self.tokenizer.encode(self.prompt(task["messages"]) + " " + answer,
                                            add_special_tokens=False)
                assert ids[:len(prefix)] == prefix
                ids.append(self.tokenizer.eos_token_id)
                rows.append((ids, len(prefix)))
        return rows

    @torch.inference_mode()
    def log_probabilities(self, rows):
        scores = []
        for start in range(0, len(rows), 8):
            batch = rows[start:start + 8]
            width = max(len(ids) for ids, _ in batch)
            ids = torch.full((len(batch), width), self.tokenizer.eos_token_id, dtype=torch.long)
            mask = torch.zeros_like(ids)
            for i, (tokens, _) in enumerate(batch):
                ids[i, :len(tokens)] = torch.tensor(tokens)
                mask[i, :len(tokens)] = 1
            hidden = self.model.transformer(input_ids=ids, attention_mask=mask,
                                            use_cache=False).last_hidden_state
            states, targets, sizes = [], [], []
            for i, (tokens, begin) in enumerate(batch):
                states.append(hidden[i, begin - 1:len(tokens) - 1])
                targets.extend(tokens[begin:]); sizes.append(len(tokens) - begin)
            logits = self.model.lm_head(torch.cat(states))
            losses = torch.nn.functional.cross_entropy(logits, torch.tensor(targets), reduction="none")
            offset = 0
            for size in sizes:
                scores.append(-float(losses[offset:offset + size].mean())); offset += size
        return scores

    def evaluate(self, tasks, rows):
        replies = self.generate([task["messages"] for task in tasks])
        scores = self.log_probabilities(rows)
        details = []
        for i, (task, reply) in enumerate(zip(tasks, replies)):
            values = scores[i * 4:i * 4 + 4]
            correct = task["choices"].index(task["answer"])
            predicted = max(range(4), key=lambda j: values[j])
            recalled = contains(reply["text"], task["value"])
            recalled = recalled and not any(contains(reply["text"], v) for v in task["choice_values"]
                                             if v != task["value"])
            confused = speaker_confused(reply["text"], task["category"], task["value"])
            bad = bad_generation(reply)
            mentioned = len(re.findall(r"(?<!\w)"+re.escape(task["value"])+r"(?!\w)",reply["text"],re.I))
            details.append(task | {"reply": reply, "recall_hit": bool(recalled),
                                   "context_answer": bool(recalled and not confused),
                                   "clean_context_answer": bool(recalled and not confused and not bad and mentioned <= 2),
                                   "bad_generation": bad,
                                   "speaker_confused": bool(confused),
                                   "choice_correct": predicted == correct, "choice_scores": values,
                                   "margin": values[correct] - max(v for j, v in enumerate(values) if j != correct)})
        return {"total": len(tasks), "recall_hits": sum(d["recall_hit"] for d in details),
                "context_answers": sum(d["context_answer"] for d in details),
                "clean_context_answers": sum(d["clean_context_answer"] for d in details),
                "bad_generations": sum(d["bad_generation"] for d in details),
                "choice_hits": sum(d["choice_correct"] for d in details),
                "mean_margin": sum(d["margin"] for d in details) / len(details), "details": details}

    @torch.inference_mode()
    def validate(self, tasks):
        messages = [task["messages"] for task in tasks[:3]]
        together = self.generate(messages)
        for message, expected in zip(messages, together):
            ids = self.tokenizer(self.prompt(message), add_special_tokens=False, return_tensors="pt")
            output = self.model.generate(**ids, do_sample=False, max_new_tokens=24,
                                         pad_token_id=self.tokenizer.eos_token_id, use_cache=True)
            assert output[0, ids.input_ids.shape[1]:].tolist() == expected["token_ids"]
        batch = self.tokenizer(self.prompt(messages[0]) + " " + tasks[0]["answer"],
                               add_special_tokens=False, return_tensors="pt")
        full = self.model(**batch, use_cache=False).logits[:, -2:]
        hidden = self.model.transformer(**batch, use_cache=False).last_hidden_state[:, -2:]
        error = float((full - self.model.lm_head(hidden)).abs().max())
        assert error < 2e-5
        return {"batched_greedy_matches_individual": True, "logits_reference_max_abs_error": error}


class Surgery:
    def __init__(self, engine, calibration):
        self.engine = engine
        self.model = engine.model
        self.original = {name: p.detach().clone() for name, p in self.model.named_parameters()}
        self.directions = []
        self.diagnostics = []
        records = [{"mlp": [], "attention_to_value": []} for _ in self.model.transformer.h]
        last = [0]
        handles = []
        for i, layer in enumerate(self.model.transformer.h):
            def hook(module, inputs, output, i=i):
                records[i]["mlp"].append(output[0, last[0]].detach().clone())
            handles.append(layer.mlp.c_proj.register_forward_hook(hook))
        with torch.inference_mode():
            for item in calibration:
                prompt = engine.prompt(item["messages"])
                encoded = engine.tokenizer(prompt, add_special_tokens=False,
                                           return_offsets_mapping=True, return_tensors="pt")
                offsets = encoded.pop("offset_mapping")[0].tolist()
                begin = prompt.index(item["value"])
                end = begin + len(item["value"])
                positions = [j for j, (a, b) in enumerate(offsets) if b > begin and a < end]
                assert positions
                last[0] = encoded.input_ids.shape[1] - 1
                out = self.model.transformer(**encoded, use_cache=False, output_attentions=True)
                for i, attention in enumerate(out.attentions):
                    records[i]["attention_to_value"].append(attention[0, :, -1, positions].sum(-1))
        for handle in handles:
            handle.remove()
        ranked = []
        for i, record in enumerate(records):
            activations = torch.stack(record["mlp"])
            mean = activations.mean(0)
            self.directions.append(mean / mean.norm().clamp_min(1e-12))
            attention = torch.stack(record["attention_to_value"]).mean(0)
            module = self.model.transformer.h[i].attn.attention
            geometry = []
            for head, amount in enumerate(attention):
                sl = slice(head * 8, (head + 1) * 8)
                output, value = module.out_proj.weight[:, sl], module.v_proj.weight[sl]
                similarity = float(torch.nn.functional.cosine_similarity(
                    output.reshape(-1), value.T.reshape(-1), dim=0))
                geometry.append({"head": head, "source_attention": float(amount),
                                 "output_value_transpose_cosine": similarity})
                ranked.append((float(amount), i, head))
            self.diagnostics.append({"layer": i, "mlp_mean_norm": float(mean.norm()),
                                     "mlp_variation_norm": float((activations - mean).norm(dim=1).mean()),
                                     "heads": geometry})
        self.top_heads = [{"layer": layer, "head": head, "source_attention": amount}
                          for amount, layer, head in sorted(ranked, reverse=True)[:8]]

    @torch.inference_mode()
    def restore(self):
        for name, parameter in self.model.named_parameters():
            parameter.copy_(self.original[name])

    @torch.inference_mode()
    def apply(self, operations):
        self.restore()
        for op in operations:
            kind = op["kind"]
            if kind == "eos_scale":
                self.model.transformer.wte.weight[self.engine.tokenizer.eos_token_id].mul_(op["scale"])
                continue
            layer = self.model.transformer.h[op["layer"]]
            attention = layer.attn.attention
            if kind == "head_output_scale":
                start = op["head"] * 8
                attention.out_proj.weight[:, start:start + 8].mul_(op["scale"])
            elif kind == "head_query_scale":
                start = op["head"] * 8
                attention.q_proj.weight[start:start + 8].mul_(op["scale"])
            elif kind == "head_inverse_value_mix":
                start = op["head"] * 8
                original = attention.out_proj.weight[:, start:start + 8].clone()
                inverse = torch.linalg.pinv(attention.v_proj.weight[start:start + 8])
                inverse *= original.norm() / inverse.norm().clamp_min(1e-12)
                attention.out_proj.weight[:, start:start + 8].copy_(
                    (1 - op["amount"]) * original + op["amount"] * inverse)
            elif kind == "subtract_mlp_mean":
                u = self.directions[op["layer"]]
                weight, bias = layer.mlp.c_proj.weight, layer.mlp.c_proj.bias
                weight.sub_(op["amount"] * torch.outer(u, u @ weight))
                bias.sub_(op["amount"] * u * (u @ bias))
            elif kind in ("attention_scale", "mlp_scale"):
                output = attention.out_proj if kind == "attention_scale" else layer.mlp.c_proj
                output.weight.mul_(op["scale"]); output.bias.mul_(op["scale"])
            else:
                raise ValueError(kind)

    def candidates(self):
        edits = [[]]
        for head in self.top_heads:
            base = {"layer": head["layer"], "head": head["head"]}
            edits.extend([[base | {"kind": "head_output_scale", "scale": scale}]
                          for scale in (0.5, 1.5, 2.0, 3.0)])
            edits.append([base | {"kind": "head_query_scale", "scale": 1.5}])
            edits.append([base | {"kind": "head_inverse_value_mix", "amount": 0.5}])
        for i in range(len(self.model.transformer.h)):
            edits.extend([[{"kind": "subtract_mlp_mean", "layer": i, "amount": amount}]
                          for amount in (0.25, 0.5)])
            edits.append([{"kind": "attention_scale", "layer": i, "scale": 1.5}])
            edits.append([{"kind": "mlp_scale", "layer": i, "scale": 0.75}])
        edits.extend([[{"kind": "eos_scale", "scale": scale}] for scale in (0.9, 1.1)])
        return edits


def main():
    started = time.perf_counter()
    origin = manifest(SOURCE, PROFILE["model"], PROFILE["revision"])
    assert origin["files"]["model.safetensors"]["sha256"] == ORIGINAL_SHA256
    engine = Engine()
    calibration, holdout, guard_questions = datasets()
    report = {"origin": origin, "method": "Direct tensor edits with forward-only selection; no gradients or optimizer",
              "exploratory_report": str(HERE / "weight-surgery-exploratory.json"),
              "protocol": {"calibration_questions": len(calibration), "holdout_questions": len(holdout),
                           "guard_questions": len(guard_questions), "generation": "greedy, 24 new tokens, context <=256",
                           "recall_metric": "Expected entity mentioned, no alternative mentioned",
                           "context_metric": "Recall excluding first-person claims about the user fact anywhere in the reply",
                           "clean_context_metric": "Context metric, requires EOS, no repeated trigram and at most two mentions of the entity",
                           "guard": "Mean NLL on original replies must increase by at most 0.35 nats/token",
                           "selection": "Calibration clean context answers, choice hits, margin; then least guard drift. No increase in malformed calibration or guard outputs.",
                           "limitation": "Small bespoke entity-recall test; not a general intelligence benchmark"}}
    report["verification"] = engine.validate(calibration)
    cal_rows = engine.completion_rows(calibration)
    baseline_cal = engine.evaluate(calibration, cal_rows)
    guard_messages = [[{"role": "user", "content": q}] for q in guard_questions]
    guard_original = engine.generate(guard_messages, maximum=40)
    baseline_bad_guards = sum(bad_generation(reply) for reply in guard_original)
    guard_rows = []
    for messages, reply in zip(guard_messages, guard_original):
        prefix = engine.tokenizer.encode(engine.prompt(messages), add_special_tokens=False)
        guard_rows.append((prefix + reply["token_ids"], len(prefix)))
    baseline_guard = -sum(engine.log_probabilities(guard_rows)) / len(guard_rows)
    report["baseline_calibration"] = baseline_cal
    report["baseline_guard_nll"] = baseline_guard
    surgery = Surgery(engine, calibration)
    report["diagnostics"] = surgery.diagnostics
    report["top_source_attention_heads"] = surgery.top_heads
    print("Baseline calibration:", json.dumps({k:v for k,v in baseline_cal.items() if k!='details'}), flush=True)
    print("Top heads:", json.dumps(surgery.top_heads), flush=True)

    candidates = []
    best_ops, best_metrics, best_guard = [], baseline_cal, baseline_guard

    def rank(metrics, guard):
        return (metrics["clean_context_answers"], metrics["choice_hits"],
                metrics["mean_margin"], -guard)

    def evaluate_candidate(operations):
        nonlocal best_ops, best_metrics, best_guard
        surgery.apply(operations)
        metrics = baseline_cal if not operations else engine.evaluate(calibration, cal_rows)
        guard = baseline_guard if not operations else -sum(engine.log_probabilities(guard_rows)) / len(guard_rows)
        eligible = (guard <= baseline_guard + 0.35
                    and metrics["bad_generations"] <= baseline_cal["bad_generations"])
        bad_guards = None
        if eligible:
            guards = guard_original if not operations else engine.generate(guard_messages,maximum=40)
            bad_guards = sum(bad_generation(reply) for reply in guards)
            eligible = bad_guards <= baseline_bad_guards
        summary = {k:v for k,v in metrics.items() if k!='details'}
        candidates.append({"operations": operations, "calibration": summary,
                           "guard_nll": guard, "bad_guard_generations": bad_guards, "eligible": eligible})
        print(json.dumps({"trial":len(candidates)-1,"operations":operations,
                          "calibration":summary,"guard_nll":guard,"eligible":eligible}), flush=True)
        if eligible and rank(metrics, guard) > rank(best_metrics, best_guard):
            best_ops, best_metrics, best_guard = operations, metrics, guard

    for operations in surgery.candidates():
        evaluate_candidate(operations)

    # Try up to three combinations of independently useful calibration edits.
    # Nothing from the holdout or the old smoke prompts participates here.
    useful = [c for c in candidates if c["eligible"] and len(c["operations"]) == 1
              and c["calibration"]["clean_context_answers"] > baseline_cal["clean_context_answers"]]
    useful.sort(key=lambda c: rank(c["calibration"], c["guard_nll"]), reverse=True)
    combos = []
    if useful:
        first = useful[0]["operations"][0]
        for other in useful[1:]:
            second = other["operations"][0]
            if first.get("layer") != second.get("layer"):
                pair = [first, second]
                if pair not in combos:
                    combos.append(pair)
                if len(combos) == 3:
                    break
    for operations in combos:
        evaluate_candidate(operations)

    # Selection is frozen before any holdout outputs are computed.
    report["candidates"] = candidates
    report["selected_operations"] = best_ops
    report["selected_calibration"] = best_metrics
    report["selected_guard_nll"] = best_guard
    test_rows = engine.completion_rows(holdout)
    surgery.restore()
    base_test = engine.evaluate(holdout, test_rows)
    surgery.apply(best_ops)
    edited_test = engine.evaluate(holdout, test_rows)
    report["baseline_holdout"] = base_test
    report["edited_holdout"] = edited_test
    edited_guards = engine.generate(guard_messages, maximum=40)
    report["chat_guards"] = [{"question":q,"before":a,"after":b}
                             for q,a,b in zip(guard_questions,guard_original,edited_guards)]

    # Audit the original English smoke questions after the edit has been fixed.
    old_smoke = json.loads((HERE / "smoke-greedy.json").read_text())
    messages = [sample["messages"] for sample in old_smoke["samples"]]
    surgery.restore()
    audit_original = engine.generate(messages, maximum=40)
    surgery.apply(best_ops)
    audit_edited = engine.generate(messages, maximum=40)
    report["smoke_audit"] = [{"messages":m,"before":a,"after":b}
                              for m,a,b in zip(messages,audit_original,audit_edited)]

    changed = sum(int((p != surgery.original[name]).sum())
                  for name,p in engine.model.named_parameters())
    report["changed_parameters"] = changed
    report["total_parameters"] = sum(p.numel() for p in engine.model.parameters())
    assert report["total_parameters"] == 8_278_400
    if best_ops:
        DESTINATION.mkdir(parents=True, exist_ok=True)
        engine.model.save_pretrained(DESTINATION, safe_serialization=True)
        for name in ("tokenizer.json","tokenizer_config.json","vocab.json","merges.txt",
                     "README.md","LICENSE","NOTICE.md"):
            shutil.copy2(SOURCE/name, DESTINATION/name)
        edit = {"origin_revision":PROFILE["revision"],"origin_sha256":ORIGINAL_SHA256,
                "operations":best_ops,"changed_parameters":changed,"report":str(REPORT),
                "selection_used_only_calibration":True}
        (DESTINATION/"weight-edit.json").write_text(json.dumps(edit,indent=2)+'\n')
        report["edited_directory"] = str(DESTINATION)
        report["edited_manifest"] = manifest(DESTINATION,PROFILE["model"],PROFILE["revision"])
        engine.model = engine.load(DESTINATION)
        reloaded = engine.generate([holdout[0]["messages"]])[0]
        assert reloaded["token_ids"] == edited_test["details"][0]["reply"]["token_ids"]
        report["saved_checkpoint_reproduces"] = True
    assert manifest(SOURCE,PROFILE["model"],PROFILE["revision"])["files"] == origin["files"]
    report["original_files_unchanged"] = True
    report["seconds"] = time.perf_counter()-started
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({"selected_operations":best_ops,"changed_parameters":changed,
                      "baseline_holdout":{k:v for k,v in base_test.items() if k!='details'},
                      "edited_holdout":{k:v for k,v in edited_test.items() if k!='details'},
                      "report":str(REPORT),"seconds":report["seconds"]}),flush=True)
    for before,after in zip(base_test["details"],edited_test["details"]):
        if before["clean_context_answer"] != after["clean_context_answer"]:
            print(json.dumps({"question":before["messages"][-1]["content"],"stated_value":before["value"],
                              "before":before["reply"]["text"],"after":after["reply"]["text"]}),flush=True)


if __name__ == "__main__":
    main()
