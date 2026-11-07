"""A separately frozen natural-Russian transfer check, never used in training."""
import hashlib
import json
import random

from emulator import Emulator
from harness import check_program
from tasks import BUILD, expression_task, save_jsonl


def main():
    path = BUILD / "tasks/natural.jsonl"
    if path.exists(): raise SystemExit("Natural-language test is already frozen")
    definitions = [
        ("К игровому счёту в R0 прибавь заработанные очки из R1.", ["+", "R0", "R1"]),
        ("Из запаса топлива R0 вычти расход R1.", ["-", "R0", "R1"]),
        ("Найди площадь прямоугольника: его стороны лежат в R2 и R3.", ["*", "R2", "R3"]),
        ("Сложи взносы из R0 и R1, а сумму раздели на число участников из R2.", ["/", ["+", "R0", "R1"], "R2"]),
        ("В R0 лежит число со знаком. Выдай его модуль.", ["abs", "R0"]),
        ("Возведи число из R1 в квадрат.", ["square", "R1"]),
        ("Смени знак числа из R2.", ["neg", "R2"]),
        ("Выручка равна цене из R0, умноженной на количество из R1. Вычти расходы из R2.", ["-", ["*", "R0", "R1"], "R2"]),
        ("Найди сумму двух произведений: первого числа R0 на второе R1 и третьего R2 на четвёртое R3.", ["+", ["*", "R0", "R1"], ["*", "R2", "R3"]]),
        ("Найди расстояние между координатами R0 и R1 на числовой прямой.", ["abs", ["-", "R0", "R1"]]),
        ("Вычисли отношение числа в R3 к числу в R2.", ["/", "R3", "R2"]),
        ("Из модуля числа R0 вычти модуль числа R1.", ["-", ["abs", "R0"], ["abs", "R1"]]),
    ]
    rows = []
    emulator = Emulator()
    rng = random.Random(61069)
    for index, (text, expression) in enumerate(definitions):
        task = expression_task(expression, rng, index, split="natural")
        task.update(id=f"natural:{index}", kind="natural_language", task="Напиши программу МК-61. " + text + " Вход уже в регистрах, результат оставь в X и остановись.")
        task.pop("initial_code", None)
        assert check_program(emulator, task["reference_code"], task["public_tests"] + task["hidden_tests"])["pass"]
        rows.append(task)
    save_jsonl(path, rows)
    manifest = {"rows": len(rows), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "used_for_training_or_selection": False,
                "purpose": "Semantic transfer from formula-style instruction tuning to new natural Russian task descriptions"}
    path.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
