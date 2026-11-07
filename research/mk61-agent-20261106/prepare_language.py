"""Teach Russian problem statements, preserving the disjoint expression families."""
import hashlib
import json
import random

from emulator import Emulator
from harness import check_program, feedback, initial_prompt
from prepare_controls import control_task
from prepare_training import answer_for
from tasks import BUILD, expression_task, make_generated, save_jsonl


def verbal(expr, rng):
    if isinstance(expr, str): return rng.choice([expr, "число из " + expr, "значение " + expr])
    op, *args = expr
    a = verbal(args[0], rng)
    if len(args) == 1:
        return rng.choice({"abs": [f"модуль ({a})", f"абсолютное значение ({a})"],
                           "neg": [f"({a}) с противоположным знаком", f"число, противоположное ({a})"],
                           "square": [f"квадрат ({a})", f"результат возведения ({a}) в квадрат"]}[op])
    b = verbal(args[1], rng)
    return rng.choice({"+": [f"сумма ({a}) и ({b})", f"результат сложения ({a}) с ({b})"],
                       "-": [f"разность ({a}) и ({b})", f"результат вычитания ({b}) из ({a})"],
                       "*": [f"произведение ({a}) и ({b})", f"результат умножения ({a}) на ({b})"],
                       "/": [f"частное ({a}) и ({b})", f"отношение ({a}) к ({b})"]}[op])


def statement(expr, rng):
    if not isinstance(expr, str) and len(expr) == 3 and all(isinstance(x, str) for x in expr[1:]):
        op, a, b = expr
        texts = {"+": [f"Прибавь {b} к {a}.", f"Сложи содержимое {a} и {b}.",
                        f"В {a} записаны накопленные баллы, в {b} новая премия. Начисли премию к баллам.",
                        f"Начальная энергия находится в {a}, добавленная энергия в {b}. Выдай общую энергию."],
                 "-": [f"Вычти {b} из {a}.", f"Уменьши значение {a} на значение {b}.",
                        f"В {a} лежат накопления, в {b} затраты. Найди остаток после затрат.",
                        f"Количество ресурсов в {a}, потрачено ресурсов из {b}. Сколько осталось?"],
                 "*": [f"Умножь {a} на {b}.", f"Перемножь значения {a} и {b}.",
                        f"В {a} записана цена, в {b} количество покупок. Рассчитай полную стоимость.",
                        f"Длина в {a}, ширина в {b}. Рассчитай площадь прямоугольной области."],
                 "/": [f"Раздели {a} на {b}.", f"Найди частное чисел из {a} и {b}.",
                        f"Общая сумма в {a}, число равных долей в {b}. Найди величину одной доли.",
                        f"Пройденный путь в {a}, затраченное время в {b}. Рассчитай среднюю скорость."]}
        return rng.choice(texts[op])
    if not isinstance(expr, str) and len(expr) == 2 and isinstance(expr[1], str):
        op, a = expr
        return rng.choice({"abs": [f"Найди абсолютную величину числа {a}.", f"Покажи модуль содержимого {a}.", f"Найди расстояние числа {a} от нуля."],
                           "neg": [f"Поменяй знак содержимого {a}.", f"Получи противоположное число для {a}."],
                           "square": [f"Умножь содержимое {a} само на себя.", f"Найди квадрат значения из {a}."]}[op])
    return rng.choice(["Вычисли: ", "Найди величину: ", "Требуется результат: "]) + verbal(expr, rng) + "."


def language_task(task, rng):
    result = dict(task)
    result["task"] = "Составь программу МК-61. " + statement(task["expression"], rng) + " Числа уже в регистрах. Ответ оставь в X, затем С/П."
    return result


def main():
    out = BUILD / "language-data"
    out.mkdir(parents=True, exist_ok=True)
    if (out / "manifest.json").exists(): raise SystemExit("Language dataset already frozen")
    rng = random.Random(61071)
    emulator = Emulator()
    tasks = make_generated("train", 19000, seed=61072)
    rows = []
    for i, task in enumerate(tasks):
        task = language_task(task, rng)
        assert check_program(emulator, task["reference_code"], task["public_tests"])["pass"]
        base = {"family": task["family"], "source": "verified_russian_expression_generator", "split": "train"}
        rows.append({**base, "kind": "russian_statement", "prompt": initial_prompt(task, examples=bool(i % 2)), "answer": answer_for(task)})
        if task.get("initial_code"):
            checked = check_program(emulator, task["initial_code"], task["public_tests"])
            rows.append({**base, "kind": "russian_repair", "prompt": initial_prompt(task, examples=bool(i % 2), observation=feedback(checked)),
                         "answer": answer_for(task)})
    replay = [json.loads(x) for x in (BUILD / "training/sft-combined-v2.jsonl").read_text().splitlines()]
    rows += rng.sample(replay, 16000)
    rng.shuffle(rows)
    save_jsonl(out / "train.jsonl", rows)
    validation = [language_task(t, rng) for t in make_generated("validation", 48, seed=61073)]
    old_validation = [json.loads(x) for x in (BUILD / "tasks/validation-extended-v2.jsonl").read_text().splitlines()]
    save_jsonl(out / "validation.jsonl", validation + old_validation)

    # New manually specified task descriptions. The first natural-language check
    # is now diagnostic; these descriptions are not used for training/selection.
    definitions = [
        ("Игрок имел R2 очков и получил ещё R3. Покажи обновлённый счёт.", ["+", "R2", "R3"]),
        ("На складе было R3 деталей. R1 деталей отгрузили. Выдай оставшееся количество.", ["-", "R3", "R1"]),
        ("Известны R0 рядов по R2 мест. Сколько всего мест?", ["*", "R0", "R2"]),
        ("За время R3 пройдено расстояние R1. Определи скорость.", ["/", "R1", "R3"]),
        ("Отобрази величину отклонения R2, не учитывая его знак.", ["abs", "R2"]),
        ("Полученное число из R3 должно иметь обратный знак.", ["neg", "R3"]),
        ("Число R0 требуется возвести во вторую степень.", ["square", "R0"]),
        ("Два вклада R1 и R2 объединяют, затем расходуют R3. Найди оставшуюся сумму.", ["-", ["+", "R1", "R2"], "R3"]),
        ("Координату R0 увеличивают на произведение скорости R1 и времени R2. Найди новую координату.", ["+", "R0", ["*", "R1", "R2"]]),
        ("Покажи расстояние между позициями R2 и R3 на одной оси.", ["abs", ["-", "R2", "R3"]]),
        ("Две партии товара: количества R0 и R2, цены соответственно R1 и R3. Найди суммарную стоимость.", ["+", ["*", "R0", "R1"], ["*", "R2", "R3"]]),
        ("Сумму чисел R2 и R3 нужно распределить на R1 равных частей.", ["/", ["+", "R2", "R3"], "R1"]),
        ("Отклонение R1 умножь на его собственное значение.", ["square", "R1"]),
        ("Для числа R0 нужен результат с изменённым знаком, затем к нему добавь R2.", ["+", ["neg", "R0"], "R2"]),
        ("Уплаченная сумма R0 минус количество R1, умноженное на цену R3: выдай сдачу.", ["-", "R0", ["*", "R1", "R3"]]),
        ("Вычисли, на сколько модуль R2 превышает модуль R3.", ["-", ["abs", "R2"], ["abs", "R3"]]),
        ("Сначала раздели R3 на R1, потом к результату прибавь R0.", ["+", ["/", "R3", "R1"], "R0"]),
        ("Величины R0 и R1 складывают, а полученный результат умножают на R2.", ["*", ["+", "R0", "R1"], "R2"]),
        ("Из квадрата R2 вычти R0.", ["-", ["square", "R2"], "R0"]),
        ("Найди противоположное число для суммы R1 и R3.", ["neg", ["+", "R1", "R3"]]),
        ("Сумма модулей чисел R0 и R3 должна оказаться на индикаторе.", ["+", ["abs", "R0"], ["abs", "R3"]]),
        ("Из содержимого R1 вычти результат деления R2 на R3.", ["-", "R1", ["/", "R2", "R3"]]),
        ("Делимое равно произведению R0 и R3; делитель лежит в R2. Выдай частное.", ["/", ["*", "R0", "R3"], "R2"]),
        ("Определи абсолютную величину суммы R1 и R2.", ["abs", ["+", "R1", "R2"]]),
    ]
    audit = []
    for i, (text, expr) in enumerate(definitions):
        task = expression_task(expr, rng, i, split="natural-v2")
        task.update(id=f"natural-v2:{i}", kind="natural_language", task="МК-61. " + text + " Вход в регистрах, ответ в X. Заверши С/П.")
        task.pop("initial_code", None)
        assert check_program(emulator, task["reference_code"], task["public_tests"] + task["hidden_tests"])["pass"]
        audit.append(task)
    save_jsonl(out / "audit.jsonl", audit)
    report = {"rows": len(rows), "new_russian_rows": len(rows) - 16000, "replay_rows": 16000,
              "validation_rows": len(validation) + len(old_validation), "fresh_audit_rows": len(audit),
              "old_natural_test_is_now_diagnostic": True,
              "audit_used_for_training_or_selection": False,
              "expression_families": "same immutable split as round1; no validation/test family added to gradients",
              "files": {name: hashlib.sha256((out / name).read_bytes()).hexdigest() for name in ["train.jsonl", "validation.jsonl", "audit.jsonl"]}}
    (out / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
