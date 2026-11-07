#!/usr/bin/env python3
"""A bounded, gradient-free weight-editing experiment on a copy of Squeal 8M.

Edits are selected using 16 calibration questions. The separate 24-question
holdout and its free-generation examples are evaluated only after selection.
This is a small diagnostic experiment, not an intelligence benchmark.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import shutil
import time

from chat import MODEL_DIR, WORK, manifest, render_prompt

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

HERE = Path(__file__).resolve().parent
REPORT = HERE / "weight-surgery.json"
EDITED = WORK / "surgery" / "selected"
ORIGINAL_SHA256 = "a33c406fa70d8e5b07d02c681e5d3a7a3d89bb1e08c20be6e0c4d5e4d2ab2681"


def task(question, correct, alternatives, category, index, history=None):
    choices = [correct, *alternatives]
    # The model sees completions separately, but also avoid first-option ties.
    shift = index % len(choices)
    choices = choices[shift:] + choices[:shift]
    return {"messages": (history or []) + [{"role": "user", "content": question}],
            "correct": correct, "choices": choices, "category": category}


def datasets():
    calibration_rows = [
        ("Сколько будет 3 плюс 2? Ответь одним числом.", "5", ["4", "6", "7"], "arithmetic"),
        ("Вычисли 8 минус 6. Ответь одним числом.", "2", ["1", "3", "4"], "arithmetic"),
        ("У меня 2 яблока, дали ещё 4. Сколько теперь яблок? Ответь числом.", "6", ["4", "5", "8"], "arithmetic"),
        ("Какое число идёт после 6? Ответь числом.", "7", ["5", "6", "8"], "arithmetic"),
        ("Какого цвета обычно трава? Ответь одним словом.", "зелёная", ["красная", "синяя", "чёрная"], "facts"),
        ("Назови столицу России. Ответь одним словом.", "Москва", ["Париж", "Рим", "Минск"], "facts"),
        ("Как называется детёныш кошки? Ответь одним словом.", "котёнок", ["щенок", "телёнок", "жеребёнок"], "facts"),
        ("Чем слышит человек? Ответь одним словом.", "ушами", ["глазами", "руками", "ногами"], "facts"),
        ("Назови противоположность слова «большой».", "маленький", ["высокий", "круглый", "зелёный"], "instructions"),
        ("Какой день идёт после понедельника?", "вторник", ["среда", "пятница", "суббота"], "instructions"),
        ("Повтори только это слово: лимон.", "лимон", ["яблоко", "банан", "груша"], "instructions"),
        ("Выбери последнее слово в строке «дом лес кот».", "кот", ["дом", "лес", "стол"], "instructions"),
        ("Меня зовут Анна. Как меня зовут? Ответь только именем.", "Анна", ["Ольга", "Елена", "Ирина"], "context"),
        ("Мой любимый цвет синий. Назови мой любимый цвет.", "синий", ["красный", "белый", "жёлтый"], "context"),
        ("В коробке находится мяч. Какой предмет в коробке?", "мяч", ["ключ", "шарф", "стакан"], "context"),
        ("Я живу в городе Омск. В каком городе я живу?", "Омск", ["Рим", "Минск", "Тула"], "context"),
    ]
    heldout_rows = [
        ("Сколько получится 4 плюс 3? Ответь числом.", "7", ["6", "8", "9"], "arithmetic"),
        ("Сколько будет 9 минус 4? Ответь числом.", "5", ["3", "4", "6"], "arithmetic"),
        ("Вычисли 2 умножить на 3. Ответь числом.", "6", ["4", "5", "8"], "arithmetic"),
        ("Раздели 8 на 2. Ответь числом.", "4", ["2", "3", "6"], "arithmetic"),
        ("У Пети 3 книги. Он купил ещё одну. Сколько книг стало? Ответь числом.", "4", ["1", "2", "3"], "arithmetic"),
        ("Какое из чисел больше: 2 или 9? Ответь числом.", "9", ["2", "3", "1"], "arithmetic"),
        ("Назови столицу Франции одним словом.", "Париж", ["Рим", "Москва", "Минск"], "facts"),
        ("Какое домашнее животное лает? Ответь одним словом.", "собака", ["кошка", "корова", "лошадь"], "facts"),
        ("Что ярко светит на небе днём? Ответь одним словом.", "солнце", ["луна", "снег", "лампа"], "facts"),
        ("Какого цвета спелый красный помидор? Ответь одним словом.", "красный", ["зелёный", "синий", "белый"], "facts"),
        ("Какое время года наступает после зимы?", "весна", ["лето", "осень", "зима"], "facts"),
        ("Что взять, чтобы укрыться от дождя? Ответь одним словом.", "зонт", ["мяч", "книгу", "ложку"], "facts"),
        ("Назови противоположность слова «ночь».", "день", ["вечер", "зима", "утро"], "instructions"),
        ("Повтори только это слово: груша.", "груша", ["банан", "лимон", "яблоко"], "instructions"),
        ("Назови первый месяц года.", "январь", ["март", "июнь", "май"], "instructions"),
        ("Какой день идёт сразу после вторника?", "среда", ["пятница", "суббота", "вторник"], "instructions"),
        ("В строке «лиса волк заяц» назови среднее слово.", "волк", ["лиса", "заяц", "кот"], "instructions"),
        ("Из слов «стол, кошка, окно» выбери название животного.", "кошка", ["стол", "окно", "шкаф"], "instructions"),
        ("Меня зовут Иван. Как меня зовут? Ответь только именем.", "Иван", ["Пётр", "Роман", "Максим"], "context"),
        ("Я Мария. Назови моё имя.", "Мария", ["Анна", "Ольга", "Елена"], "context"),
        ("Мою собаку зовут Рекс. Как зовут мою собаку?", "Рекс", ["Шарик", "Бобик", "Барсик"], "context"),
        ("Я положил на стол ключ. Что я положил на стол?", "ключ", ["мяч", "нож", "шарф"], "context"),
        ("Я выбрал число три. Какое число я выбрал? Ответь цифрой.", "3", ["1", "2", "4"], "context"),
        ("Моя дверь красная. Какого цвета моя дверь?", "красная", ["белая", "синяя", "чёрная"], "context"),
    ]
    calibration = [task(*row, i) for i, row in enumerate(calibration_rows)]
    heldout = [task(*row, i) for i, row in enumerate(heldout_rows)]
    return calibration, heldout


def main():
    started = time.perf_counter()
    torch.set_num_threads(2)
    torch.manual_seed(42)
    before = manifest()
    assert before["files"]["model.safetensors"]["sha256"] == ORIGINAL_SHA256
    tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR, local_files_only=True,
                                             trust_remote_code=False)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_DIR, local_files_only=True, trust_remote_code=False,
        dtype=torch.float32, attn_implementation="eager").eval().requires_grad_(False)
    calibration, heldout = datasets()
    report = {"origin": before, "method": "Direct tensor edits; no gradients, optimizer or training loop",
              "protocol": {"calibration_questions": len(calibration),
                           "holdout_questions": len(heldout), "context_limit": 256,
                           "selection": "Calibration accuracy, then mean correct-vs-best-wrong log-probability margin, then correct-answer NLL",
                           "choice_score": "Mean teacher-forced token log-probability, including EOS; choices are never listed in the prompt",
                           "warning": "Small bespoke diagnostic set; not a standard benchmark or proof of general intelligence"},
              "candidates": []}

    def encode_tasks(tasks):
        rows = []
        for item in tasks:
            prompt = render_prompt(tokenizer, item["messages"])
            prefix = tokenizer.encode(prompt, add_special_tokens=False)
            for choice in item["choices"]:
                ids = tokenizer.encode(prompt + choice, add_special_tokens=False)
                assert ids[:len(prefix)] == prefix, "Answer changes the prompt tokenization"
                ids.append(tokenizer.eos_token_id)
                assert len(ids) <= 256
                rows.append((ids, len(prefix)))
        return rows

    @torch.inference_mode()
    def score(tasks, rows):
        scores = []
        for at in range(0, len(rows), 8):
            batch = rows[at:at + 8]
            width = max(len(ids) for ids, _ in batch)
            ids = torch.full((len(batch), width), tokenizer.pad_token_id, dtype=torch.long)
            mask = torch.zeros_like(ids)
            for i, (tokens, _) in enumerate(batch):
                ids[i, :len(tokens)] = torch.tensor(tokens)
                mask[i, :len(tokens)] = 1
            hidden = model.model(input_ids=ids, attention_mask=mask,
                                 use_cache=False).last_hidden_state
            states, targets, sizes = [], [], []
            for i, (tokens, begin) in enumerate(batch):
                states.append(hidden[i, begin - 1:len(tokens) - 1])
                targets.extend(tokens[begin:])
                sizes.append(len(tokens) - begin)
            logits = model.lm_head(torch.cat(states))
            losses = torch.nn.functional.cross_entropy(logits, torch.tensor(targets), reduction="none")
            offset = 0
            for size in sizes:
                scores.append(-float(losses[offset:offset + size].mean()))
                offset += size
        details = []
        for i, item in enumerate(tasks):
            values = scores[i * 4:i * 4 + 4]
            correct = item["choices"].index(item["correct"])
            predicted = max(range(4), key=lambda j: values[j])
            details.append({"messages": item["messages"], "category": item["category"],
                            "choices": item["choices"], "correct": item["correct"],
                            "predicted": item["choices"][predicted], "scores": values,
                            "is_correct": predicted == correct,
                            "margin": values[correct] - max(v for j, v in enumerate(values) if j != correct),
                            "gold_nll": -values[correct]})
        return {"correct": sum(x["is_correct"] for x in details), "total": len(details),
                "mean_margin": sum(x["margin"] for x in details) / len(details),
                "gold_nll": sum(x["gold_nll"] for x in details) / len(details),
                "details": details}

    @torch.inference_mode()
    def validate_scoring():
        text = render_prompt(tokenizer, calibration[0]["messages"]) + calibration[0]["correct"]
        batch = tokenizer(text, add_special_tokens=False, return_tensors="pt")
        full = model(**batch, use_cache=False).logits
        hidden = model.model(**batch, use_cache=False).last_hidden_state
        subset = model.lm_head(hidden[:, -3:])
        error = float((full[:, -3:] - subset).abs().max())
        assert torch.allclose(full[:, -3:], subset, atol=2e-5, rtol=2e-5), error
        return error

    report["scoring_reference_max_abs_error"] = validate_scoring()
    calibration_encoded = encode_tasks(calibration)
    base_calibration = score(calibration, calibration_encoded)
    report["baseline_calibration"] = base_calibration
    print("Baseline calibration:", base_calibration["correct"], "/", len(calibration), flush=True)

    # Read activations only on calibration prompts, before trying any edits.
    records = [{"mlp": [], "features": [], "attention": []} for _ in model.model.layers]
    last = [0]
    handles = []
    for i, layer in enumerate(model.model.layers):
        def mlp_hook(module, inputs, output, i=i):
            records[i]["mlp"].append(output[0, last[0]].clone())
            records[i]["features"].append(inputs[0][0, last[0]].clone())
        def attention_hook(module, inputs, output, i=i):
            records[i]["attention"].append(output[0, last[0]].clone())
        handles.append(layer.mlp.down_proj.register_forward_hook(mlp_hook))
        handles.append(layer.self_attn.o_proj.register_forward_hook(attention_hook))
    with torch.inference_mode():
        for item in calibration:
            batch = tokenizer(render_prompt(tokenizer, item["messages"]),
                              add_special_tokens=False, return_tensors="pt")
            last[0] = batch.input_ids.shape[1] - 1
            model.model(**batch, use_cache=False)
    for handle in handles:
        handle.remove()

    directions, columns, diagnostics = [], [], []
    for i, record in enumerate(records):
        outputs = torch.stack(record["mlp"])
        mean = outputs.mean(0)
        direction = mean / mean.norm().clamp_min(1e-12)
        directions.append(direction)
        features = torch.stack(record["features"]).mean(0)
        weight = model.model.layers[i].mlp.down_proj.weight
        contributions = (direction @ weight) * features
        selected = contributions.abs().topk(64).indices
        columns.append(selected)
        diagnostics.append({"layer": i,
                            "mlp_mean_norm": float(outputs.norm(dim=1).mean()),
                            "mlp_mean_direction_norm": float(mean.norm()),
                            "mlp_question_variation_norm": float((outputs - mean).norm(dim=1).mean()),
                            "attention_mean_norm": float(torch.stack(record["attention"]).norm(dim=1).mean()),
                            "selected_columns": selected.tolist()})
    report["diagnostics"] = diagnostics

    mlp_original = [layer.mlp.down_proj.weight.detach().clone() for layer in model.model.layers]
    attn_original = [layer.self_attn.o_proj.weight.detach().clone() for layer in model.model.layers]

    @torch.inference_mode()
    def restore():
        for i, layer in enumerate(model.model.layers):
            layer.mlp.down_proj.weight.copy_(mlp_original[i])
            layer.self_attn.o_proj.weight.copy_(attn_original[i])

    @torch.inference_mode()
    def apply(edit):
        restore()
        if edit["kind"] == "identity":
            return
        i, kind, strength = edit["layer"], edit["kind"], edit["strength"]
        layer = model.model.layers[i]
        if kind in ("subtract_mean_top64", "subtract_mean_all"):
            chosen = columns[i] if kind.endswith("top64") else torch.arange(mlp_original[i].shape[1])
            original = mlp_original[i][:, chosen]
            u = directions[i]
            layer.mlp.down_proj.weight[:, chosen] = original - strength * torch.outer(u, u @ original)
        elif kind == "scale_mlp":
            layer.mlp.down_proj.weight.mul_(strength)
        elif kind == "scale_attention":
            layer.self_attn.o_proj.weight.mul_(strength)
        else:
            raise ValueError(kind)

    edits = [{"kind": "identity"}]
    for i in range(len(model.model.layers)):
        edits.extend([{"kind": kind, "layer": i, "strength": strength}
                      for kind, strength in (("subtract_mean_top64", 0.5),
                                             ("subtract_mean_top64", 1.0),
                                             ("subtract_mean_all", 1.0),
                                             ("scale_mlp", 0.5),
                                             ("scale_attention", 2.0))])

    def rank(metrics):
        return metrics["correct"], metrics["mean_margin"], -metrics["gold_nll"]

    best_edit, best_metrics = edits[0], base_calibration
    for edit in edits:
        apply(edit)
        metrics = base_calibration if edit["kind"] == "identity" else score(calibration, calibration_encoded)
        summary = {k: v for k, v in metrics.items() if k != "details"}
        report["candidates"].append({"edit": edit, "calibration": summary})
        print(json.dumps({"edit": edit, "calibration": summary}), flush=True)
        if rank(metrics) > rank(best_metrics):
            best_edit, best_metrics = dict(edit), metrics

    # Freeze the chosen edit before encoding or evaluating the holdout.
    report["selected_edit"] = best_edit
    report["selected_calibration"] = best_metrics
    heldout_encoded = encode_tasks(heldout)
    restore()
    base_heldout = score(heldout, heldout_encoded)
    apply(best_edit)
    edited_heldout = score(heldout, heldout_encoded)
    report["baseline_heldout"] = base_heldout
    report["edited_heldout"] = edited_heldout

    @torch.inference_mode()
    def generate(item):
        batch = tokenizer(render_prompt(tokenizer, item["messages"]),
                          add_special_tokens=False, return_tensors="pt")
        out = model.generate(**batch, do_sample=False, max_new_tokens=48,
                             pad_token_id=tokenizer.pad_token_id,
                             eos_token_id=tokenizer.eos_token_id, use_cache=True)
        ids = out[0, batch.input_ids.shape[1]:]
        return {"text": tokenizer.decode(ids, skip_special_tokens=True).strip(),
                "raw_text": tokenizer.decode(ids), "token_ids": ids.tolist()}

    report["free_generation"] = []
    for i in (0, 6, 10, 12, 18, 20):
        restore()
        base_answer = generate(heldout[i])
        apply(best_edit)
        edited_answer = generate(heldout[i])
        report["free_generation"].append({"messages": heldout[i]["messages"],
                                          "expected": heldout[i]["correct"],
                                          "baseline": base_answer, "edited": edited_answer})

    changed = 0
    for i, layer in enumerate(model.model.layers):
        changed += int((layer.mlp.down_proj.weight != mlp_original[i]).sum())
        changed += int((layer.self_attn.o_proj.weight != attn_original[i]).sum())
    report["changed_parameters"] = changed
    report["total_parameters"] = sum(p.numel() for p in model.parameters())
    assert report["total_parameters"] == 7_858_368

    if best_edit["kind"] != "identity":
        EDITED.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(EDITED, safe_serialization=True)
        for name in ("tokenizer.json", "tokenizer_config.json", "chat_template.jinja", "README.md"):
            shutil.copy2(MODEL_DIR / name, EDITED / name)
        (EDITED / "weight-edit.json").write_text(json.dumps({
            "origin_revision": before["revision"], "origin_sha256": ORIGINAL_SHA256,
            "edit": best_edit, "changed_parameters": changed,
            "report": str(REPORT), "selection_used_only_calibration": True}, indent=2) + "\n")
        report["edited_model_directory"] = str(EDITED)
        report["edited_manifest"] = manifest(EDITED)
        # Confirm that the on-disk edited checkpoint reproduces in-memory output.
        expected = report["free_generation"][0]["edited"]["token_ids"]
        model = AutoModelForCausalLM.from_pretrained(
            EDITED, local_files_only=True, trust_remote_code=False,
            dtype=torch.float32, attn_implementation="eager").eval().requires_grad_(False)
        actual = generate(heldout[0])["token_ids"]
        assert actual == expected, "Saved edited checkpoint does not reproduce the selected edit"
        report["saved_checkpoint_reproduces"] = True

    assert manifest()["files"] == before["files"], "The original model files changed"
    report["original_files_unchanged"] = True
    report["seconds"] = time.perf_counter() - started
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"selected_edit": best_edit, "changed_parameters": changed,
                      "baseline_heldout": {k: v for k, v in base_heldout.items() if k != "details"},
                      "edited_heldout": {k: v for k, v in edited_heldout.items() if k != "details"},
                      "report": str(REPORT), "seconds": report["seconds"]}, ensure_ascii=False), flush=True)
    for sample in report["free_generation"]:
        print(json.dumps({"question": sample["messages"][-1]["content"],
                          "before": sample["baseline"]["text"],
                          "after": sample["edited"]["text"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
