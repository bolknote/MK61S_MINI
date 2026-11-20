"""Score the three-model benchmark on matched tasks and starts."""

from collections import Counter
from statistics import mean

from ay_common import read, sha, write
from br_finish import paired
from ce_finish import measures, transitions
from cj_benchmark import ROOT, SERVICES, SOURCE, closed_data, policy


MODELS = {"3m": "Kon-Tiki 3M Q4", **{role: model for role, (model, _) in SERVICES.items()}}


def checked_ids(goals, first, *panels):
    assert [x["id"] for x in first] == [g["id"] for g in goals]
    expected = [(f"{g['id']}:{start}", g["id"], start == "correct")
                for g in goals for start in ("correct", g["error_kind"])]
    for panel in panels:
        assert [(r["id"], r["task_id"], r["initially_correct"]) for r in panel] == expected


def primary_metrics(records):
    return {
        "tasks": len(records), "correct_program": sum(row["program_correct"] for row in records),
        "correct_spec": sum(row["intent"]["tested_equal"] for row in records),
        "invalid_output": sum(bool(row["codec_error"]) for row in records),
    }


def resource_metrics(first, records, small):
    primary = {row["id"]: row["generation"] for row in first}
    entries = [[primary[row["task_id"]], *(entry["generation"] for entry in row["history"] if "generation" in entry)]
               for row in records]
    for calls in entries:
        assert all(g["input_tokens"] is not None and (small or g["completion_tokens"] is not None) for g in calls)
        if not small:
            assert not any(g["reasoning_sent"] for g in calls)
    processed = [sum(g["input_tokens"] for g in calls if not small or "cache" in g) for calls in entries]
    generated = [sum(len(g["generated_token_ids"]) if small else g["completion_tokens"] for g in calls) for calls in entries]
    return {"mean_calls": mean(map(len, entries)), "mean_input": mean(processed), "mean_output": mean(generated)}


def model_metrics(role, goals, first, full, assisted):
    checked_ids(goals, first, full, assisted)
    groups = {g["id"]: g["wording_cohort"] for g in goals}
    cohorts = {}
    for cohort in [*dict.fromkeys(groups.values()), "without_deepseek_wording"]:
        def included(task):
            return (groups[task] != "freeform" if cohort == "without_deepseek_wording" else groups[task] == cohort)

        cohorts[cohort] = {
            "primary": primary_metrics([r for r in first if included(r["id"])]),
            "full": measures([r for r in full if included(r["task_id"])]),
            "assisted": measures([r for r in assisted if included(r["task_id"])]),
        }
    return {
        "primary": primary_metrics(first), "full": measures(full), "assisted": measures(assisted),
        "resources": {name: resource_metrics(first, values, role == "3m")
                      for name, values in (("full", full), ("assisted", assisted))},
        "assisted_routes": dict(Counter(row["route"] for row in assisted)),
        "full_final_state": {"has_format_failure": sum(any(h["kind"] == "generation_error" for h in r["history"]) for r in full),
                              "without_done_or_abstention": sum(not r["finished"] and not r["abstained"] for r in full)},
        "cohorts": cohorts,
    }


def render(result):
    stats = result["metrics"]
    table = [
        "# Сравнение 3M, DeepSeek и Qwen на задачах МК-61", "",
        "Последний набор `spec-formula-clarification-v1` содержит 256 русских задач. Для каждой проверена программа с первого ответа и два сценария отладки с одинаковыми у всех моделей стартами. В первом сценарии код верный, во втором в нём внесена ошибка. Проверка ROM сравнивает X и память на 32 отложенных входах. Задачи в этом наборе относятся к арифметическим формулам, включая композиции и записи в регистр.", "",
        "Полный цикл отличается от режима с подтверждением. В полном цикле агент использует WRITE, RUN, TRACE, DIAG, DONE и UNSURE с общим лимитом 12 шагов. Он получает фактический результат открытых тестов и подсказки о собственной гипотезе. Ожидаемые ответы скрыты до оценки. В режиме с подтверждением у всех один и тот же независимый разбор текста, проверка исходного кода и уточнение SPEC с максимум тремя вариантами. Если нужен ответ пользователя, отдельный имитатор выбирает по отложенным проверкам. Это оценка покрытия при точных ответах пользователя.", "",
        "| Модель | Первая программа /256 | Полный цикл /512 | Исправления /256 | Принятые ложные `DONE` | Порча правильного кода | С подтверждением /512 | Исправления с подтверждением /256 | Ложные `DONE` с подтверждением | Порча с подтверждением |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for role, name in MODELS.items():
        a, b = stats[role]["full"], stats[role]["assisted"]
        table.append(f"| {name} | {stats[role]['primary']['correct_program']} | {a['completed']} | {a['repairs']} | {a['accepted_false_DONE']} | {a['corruption']} | {b['completed']} | {b['repairs']} | {b['accepted_false_DONE']} | {b['corruption']} |")
    table += ["", "Большие модели получили одинаковую инструкцию по действиям и могли возвращать обычную формулу в JSON. Формула компилировалась тем же компилятором, что и компактная SPEC нашей 3M. Использованы имеющиеся результаты Q4 окна 1024 для тех же файлов задач и стартов. Для обеих серверных моделей thinking выключен, температура 0, лимит 512 токенов на ответ. Токенизаторы и настройки вывода отличаются.", "",
              "В первой пробе на этом наборе обе серверные модели повторяли WRITE. Переиспользованный запрос сохранял подсказку из протокола маленькой модели. После исправления серверам дали отдельную инструкцию для отладки, проверили передачу RUN и DONE на внешней задаче и заново начали оба полных цикла. Первый перевод сделан с прежним запросом, его ответы остались теми же.", "",
              "| Модель | Верный смысл SPEC /256 | Неразбираемый первый ответ | Все попытки ложного `DONE` в цикле | Среднее число вызовов в цикле | Токены на эпизод, вход / выход |",
              "|---|---:|---:|---:|---:|---:|"]
    for role, name in MODELS.items():
        values = stats[role]
        usage = values["resources"]["full"]
        table.append(f"| {name} | {values['primary']['correct_spec']} | {values['primary']['invalid_output']} | {values['full']['false_DONE_claims']} | {usage['mean_calls']:.2f} | {usage['mean_input']:.1f} / {usage['mean_output']:.1f} |")
    table += ["", "Учтены первый перевод и дальнейшие вызовы. Вход серверов включает справочник и системную инструкцию. Вход 3M учитывает фактически обработанные токены, а лимит окна может завершить цикл до обработки следующего снимка. Число токенов относится к своему токенизатору.", "",
              "DeepSeek участвовал в составлении и проверке 160 свободных формулировок отдельными запросами. Во время сравнения получал только те же условия и состояние, что и Qwen. Результаты остальных 96 условий отдельно показаны ниже.", "",
              "| Модель | Первая программа /96 | Полный цикл /192 | Исправления /96 | С подтверждением /192 |",
              "|---|---:|---:|---:|---:|"]
    for role, name in MODELS.items():
        values = stats[role]["cohorts"]["without_deepseek_wording"]
        table.append(f"| {name} | {values['primary']['correct_program']} | {values['full']['completed']} | {values['full']['repairs']} | {values['assisted']['completed']} |")
    table += ["", "Веса всех трёх моделей использованы без обновлений. Парные сравнения, детализация по типам формулировки и списки восстановленных и потерянных исправлений сохранены в `comparison.json`.", ""]
    return "\n".join(table)


def main():
    goals, _ = closed_data()
    assert read(ROOT / "policy.json") == policy()
    previous = read(SOURCE / "full-cycle.json")
    first = {"3m": previous["primary"]}
    full = {"3m": previous["records"]}
    assisted = {"3m": read(SOURCE / "clarification.json")["records"]}
    hashes = {}
    for role, (model, _) in SERVICES.items():
        folder = ROOT / role
        receipt = read(folder / "complete.json")
        assert receipt == {"model": model, "tasks": 256, "episodes": 512}
        first[role] = read(folder / "translation.json")
        full[role] = read(folder / "cycle.json")
        assisted[role] = read(folder / "assisted.json")["records"]
        hashes[role] = {name: sha(folder / name) for name in ("translation.json", "cycle.json", "assisted.json")}
        for rows in (full[role], assisted[role]):
            for row in rows:
                assert all(h["generation"]["model"] == model for h in row["history"] if "generation" in h)
        assert all(row["generation"]["model"] == model for row in first[role])
    metrics = {role: model_metrics(role, goals, first[role], full[role], assisted[role]) for role in MODELS}
    pairs = (("3m", "deepseek"), ("3m", "qwen"), ("qwen", "deepseek"))
    comparisons = {mode: {f"{a}:{b}": {"paired": paired(values[a], values[b]),
                                         "transitions": transitions(values[a], values[b])} for a, b in pairs}
                   for mode, values in (("full", full), ("assisted", assisted))}
    result = {"complete": True, "optimizer_updates": 0, "policy": policy(), "result_hashes": hashes,
              "metrics": metrics, "paired_comparisons": comparisons}
    path = ROOT / "MK61_MODEL_COMPARISON.md"
    path.write_text(render(result))
    result.update(report=str(path), report_sha256=sha(path))
    write(ROOT / "comparison.json", result)
    print(path, flush=True)


if __name__ == "__main__":
    main()
