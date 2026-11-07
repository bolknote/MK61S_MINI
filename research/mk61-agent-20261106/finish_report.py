"""Package both numerical artifacts and report functional results without an LLM grader."""
import hashlib
import json
from pathlib import Path
import shutil

from tasks import BUILD, HERE


def read(path):
    return json.loads(path.read_text())


def main():
    results = BUILD / "server-results"
    comparison = read(results / "language-comparison.json")
    report = {"models": {}, "selection_policy": read(BUILD / "language-selection-policy.json"),
              "original_checkpoint": read(BUILD / "flourish-original/origin.json"),
              "data_audit": read(BUILD / "data-audit.json"),
              "native_picocalc_inference_implemented": False,
              "host_inference_activations_and_cache": "FP32; Q4 weights are physically packed and reloaded before inference"}
    for arm in ["plan", "no-plan"]:
        scores = {}
        for fmt in ["fp32", "q4"]:
            for split in ["basic", "regression", "language-validation", "diagnostic", "fresh-natural"]:
                name = f"language-{arm}-{fmt}-{split}"
                value = read(results / "language-results" / (name + ".json"))
                scores[fmt + ":" + split] = {k: value[k] for k in ["total", "passed", "pass_rate", "valid_tool_tasks", "by_kind"]}
                if fmt == "q4" and split == "fresh-natural":
                    details = value["details"]
                    scores["tool_behavior"] = {
                        "trace_tasks": sum(any(h.get("tool") == "trace" for h in d["history"]) for d in details),
                        "success_after_failed_run": sum(d["pass"] and any(h.get("public_result", {}).get("pass") is False for h in d["history"][:-1]) for d in details),
                        "success_after_multiple_turns": sum(d["pass"] and len(d["history"]) > 1 for d in details),
                        "public_pass_hidden_fail": sum(d.get("public_pass", False) and not d["pass"] for d in details)}
        export = BUILD / "export" / arm
        hf = export / "hf"
        hf.mkdir(parents=True, exist_ok=True)
        source = results / ("language-" + arm) / "best"
        for path in source.iterdir():
            if path.is_file(): shutil.copy2(path, hf / path.name)
        packed_source = results / "language-results" / f"language-{arm}-q4-fresh-natural.mkq4"
        shutil.copy2(packed_source, export / "model.mkq4")
        manifest = {"arm": arm, "q4_file": str(export / "model.mkq4"), "q4_bytes": (export / "model.mkq4").stat().st_size,
                    "q4_sha256": hashlib.sha256((export / "model.mkq4").read_bytes()).hexdigest(),
                    "hf_directory": str(hf), "hf_weights_sha256": hashlib.sha256((hf / "model.safetensors").read_bytes()).hexdigest(),
                    "tokenizer_bytes": (hf / "tokenizer.json").stat().st_size,
                    "parameters": 3017984, "trained_context": 512,
                    "fp16_kv_bytes_per_token_design": 2560, "fp16_kv_512_design_bytes": 1310720,
                    "scores": scores}
        training = read(results / ("language-" + arm) / "training.json")
        manifest["selected_checkpoint_step_in_language_round"] = training["best_step"]
        manifest["completed_language_training_steps"] = training["steps"]
        manifest["weights_tokenizer_kv512_design_bytes"] = manifest["q4_bytes"] + manifest["tokenizer_bytes"] + 1310720
        (export / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        report["models"][arm] = manifest
    # Predetermined validation-only selection; the fresh audits never enter this rule.
    selected = max(["plan", "no-plan"], key=lambda arm: (report["models"][arm]["scores"]["q4:language-validation"]["pass_rate"], arm == "plan"))
    report["selected_by_validation"] = selected
    (BUILD / "final-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    lines = ["# Flourish-3M для программирования МК-61", "",
             "**Получился узкий генератор коротких программ для формализованных условий. "
             "Надёжного помощника, понимающего свободные русские описания, это обучение не дало.** "
             "Высокая точность на формальных задачах не переносится на обычные формулировки.", "",
             "Дообучены две версии одной русской модели: с коротким планом и с непосредственным выводом действий. "
             "Обе используют один и тот же ограниченный эмулятор и одинаковый бюджет ответа.", "",
             "| Вариант | Формулы и управление, Q4 | Новые русские описания, FP32 | Новые русские описания, Q4 |",
             "| --- | ---: | ---: | ---: |", "| Исходная модель | 0/98 | — | 0/24 |"]
    for arm, label in [("plan", "С планом"), ("no-plan", "Без плана")]:
        scores = report["models"][arm]["scores"]
        values = [scores["q4:regression"], scores["fp32:fresh-natural"], scores["q4:fresh-natural"]]
        lines.append("| " + label + " | " + " | ".join(f"{v['passed']}/{v['total']}" for v in values) + " |")
    lines += ["", "По заранее зафиксированному правилу выбран вариант **" + selected + "**: выше точность Q4 на полной проверочной выборке из 120 задач. "
              "Результаты итоговых словесных задач в выбор не входят.", "",
              "## Что обучалось", "",
              "Исходная модель — `akanemind/Flourish-3M`, revision `33b38dfec202c39c3698f7f2d1a9933a34a2de1a`; "
              "3 017 984 параметра, 10 слоёв, GQA 4/2, словарь 8192, контекст 512. Исходные веса сохранены.", "",
              "Доменное обучение: 462 нормализованных исторических листинга, 302 отобранных фрагмента из девяти русских книг "
              "и шесть справочных документов. OCR-таблицы программ не использовались как проверенные ответы.", "",
              "Первый этап: 34 320 примеров программ, коротких планов, вызовов, трассировок и исправлений; "
              "3000 шагов для каждой версии, QAT с шага 2001. На формулах появился навык, но первая проверка обычных "
              "русских описаний дала 0/12. Это диагностический результат, а не успешное обучение языковому программированию.", "",
              "Дополнительный этап: 25 333 новых примера русских условий и 16 000 примеров повтора; 2000 шагов "
              "для обеих версий с QAT с первого шага. После него проверены новые 24 описания. Две версии обучались "
              "на отдельных B200. Эффективный пакет 32, микропакет 16, накопление градиента 2.", "",
              "## Инструменты и проверка", "",
              "Модель выдаёт `<write>HEX</write><run/>` либо `<trace/>`; версия с планом предваряет действие тегом `<plan>`. "
              "Harness выполняет запрос на настоящем микрокодном ядре PicoCalc и возвращает наблюдение. "
              "При обучении наблюдение находится в контексте, но не является целевым ответом модели. "
              "Успех определяется запуском на показанных и скрытых входах, а не заявлением модели.", "",
              "Ограничения проверки: максимум 105 байтов программы, три хода, 160 новых токенов на ход, "
              "512 активных токенов, 256 команд калькулятора на запуск. Разбиение выражений выполнено до генерации "
              "примеров по структуре с удалёнными именами регистров. Задачи управления проверяют новые значения "
              "и назначения регистров изученных примитивов. У всех синтетических эталонов проверено реальное исполнение.", "",
              "Идея чередовать план, действие и наблюдение соответствует "
              "[ReAct](https://arxiv.org/abs/2210.03629). Наличие текста плана само по себе не доказывает правильность рассуждения; "
              "измеряется успешность программы. Это сравнительный запуск с одним seed, а не общий вывод о пользе CoT.", "",
              "В новых словесных задачах обе Q4-версии выдали допустимые вызовы инструментов в 24/24 случаях, "
              "но ни одна не запросила трассировку. У версии с планом только одна успешная задача потребовала "
              "исправления после неудачного запуска. Освоение протокола не означает надёжного использования обратной связи.", "",
              "При ручной проверке сохранённой Q4-версии с планом `X = R0 + R1` даёт правильный код "
              "`60 61 10 50`. Та же операция словами в `demo-task.json` вызывает вычитание "
              "`60 61 11 50`, которое модель повторяет после сообщения об ошибке. Это иллюстрация, не часть итогового набора.", "",
              "## Артефакты и границы", ""]
    for arm, item in report["models"].items():
        lines += [f"- `{arm}`: [{item['q4_bytes']:,} байт Q4]({item['q4_file']}); "
                  f"[HF checkpoint]({item['hf_directory']}); tokenizer {item['tokenizer_bytes']:,} байт."]
    lines += ["", "Q4 — собственный формат MKQ4v1: подписанные 4-битные матрицы, FP16-шкала на 32 веса, "
              "FP32-векторы нормализации. Веса реально упаковываются и загружаются заново перед тестом. "
              "Точное совпадение загруженных и ожидаемых квантованных весов проверено.", "",
              "Инференс проверен на хосте с FP32-активациями и KV-кешем. Расчёт целевого FP16 KV для 512 токенов — "
              "1 310 720 байт. Это проектный бюджет; нативный runtime PicoCalc, его память и скорость ещё не измерены. "
              "Расширение контекста сверх 512 не обучалось.", "",
              "Результаты относятся к коротким арифметическим программам, условиям, циклам и работе с регистрами. "
              "Генерация произвольной полной игры по свободному описанию этим набором не подтверждается.", "",
              "Полные ответы, реальные результаты эмулятора, скрытые проверки, версии данных и исходные журналы лежат "
              "в `.build/mk61-agent-20261106/`. Проверки harness: `python3 research/mk61-agent-20261106/self_test.py`.", ""]
    (HERE / "RESULTS.md").write_text("\n".join(lines))
    print(json.dumps({"selected": selected, "models": {arm: {"scores": item["scores"], "q4_bytes": item["q4_bytes"]}
                                                     for arm, item in report["models"].items()}}, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
