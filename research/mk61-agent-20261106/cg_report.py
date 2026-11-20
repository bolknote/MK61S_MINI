"""Summarize autonomous changes and the separate simulated-confirmation arm."""

from collections import Counter

from ar_spec import equivalent
from ay_common import read, rows, sha, write
from bl_spec import install
from br_finish import paired
from ce_finish import measures, token_summary, transitions
from cf_language import expanded_parse
from cg_data import ROOT, TARGETS
from cg_eval import ARMS, RESULT_FILES, check_frozen
from cg_language import parse_task


NAMES = {
    "full_cycle": "Полный цикл",
    "previous_short": "Прежний короткий путь",
    "autonomous": "Три новых правила, автономно",
    "awaiting_confirmation": "Ожидание подтверждения",
    "with_confirmation": "С имитацией подтверждения",
}
PANELS = {"steps": "Явные цепочки", "structured": "Формальная грамматика", "freeform": "Свободный русский",
          "repeat": "Повтор операции", "replace_sign": "Замена на знак", "absolute": "Взятие по модулю"}


def summarize_panel(records, goals, panel):
    chosen = [row for row in records if goals[row["task_id"]]["wording_cohort"] == panel]
    return measures(chosen)


def coverage(goals, parser):
    counts = {panel: Counter() for panel in PANELS}
    for goal in goals.values():
        row = counts[goal["wording_cohort"]]
        row["tasks"] += 1
        spec = parser(goal["task"], goal["spec"]["angle"])
        if spec is not None:
            row["parsed"] += 1
            row["matches_reference_on_audit"] += equivalent(spec, goal["spec"], goal["audit_inputs"])["tested_equal"]
    return {panel: dict(value) for panel, value in counts.items()}


def confirmation_summary(waiting, assisted, goals):
    waiting_by_id = {row["id"]: row for row in waiting}
    counts = Counter()
    example = None
    for row in assisted:
        pending = waiting_by_id[row["id"]]
        if "formula_preview" not in pending:
            continue
        goal = goals[row["task_id"]]
        initial = goal["reference_body"] if row["initially_correct"] else goal["bad_body"]
        assert pending["body"] == initial and not pending["finished"]
        assert pending["formula_preview"] == row["formula_preview"]
        counts["requested"] += 1
        if row["confirmation"] is False:
            assert row["body"] == initial and not row["finished"]
            counts["rejected"] += 1
            continue
        assert row["confirmation"] is True
        counts["accepted"] += 1
        counts["accepted_completed"] += row["pass"]
        counts["accepted_repairs"] += row["pass"] and not row["initially_correct"]
        counts["accepted_false_DONE"] += row["finished"] and not row["program_correct"]
        counts["accepted_corruption"] += row["initially_correct"] and not row["program_correct"]
        counts["one_call_completed"] += row["pass"] and row["route"] in ("kept_program", "compiled_program")
        counts["approved_full_cycle"] += row["route"] == "confirmed_full_cycle"
        if example is None and row["route"] == "compiled_program" and row["pass"]:
            example = {"task": goal["task"], "preview": pending["formula_preview"]}
    assert counts["requested"] == counts["accepted"] + counts["rejected"]
    counts["distinct_tasks"] = len({row["task_id"] for row in waiting if "formula_preview" in row})
    return dict(counts), example


def report(result):
    destination = ROOT / "SPEC_FORMULA_CONFIRMATION_RESULTS.md"
    confirm = result["confirmation"]
    lines = [
        "# Подтверждение формулы и три правила разбора",
        "",
        "Новый закрытый набор состоит из 256 задач и 512 эпизодов со стартовой правильной или ошибочной программой. В набор вошли 160 свободных условий, 48 обычных структурированных заданий и по 16 новых задач на повтор операции, замену на знак и модуль. Формулы, условия, входы и варианты оценки зафиксированы до запусков Q4.",
        "",
        "Автономная ветка использует прежний короткий путь и три дополнительных правила. В ветке с подтверждением для неподдержанных запросов упряжь показывает точную формулу, угловой режим и регистр назначения. До ответа она сохраняет исходную программу. Имитатор пользователя сверяет показанную формулу на 32 контрольных входах и передаёт упряжи один булев ответ. После согласия упряжь проверяет исходную программу или скомпилированный кандидат на 18 рабочих входах. При необходимости полная отладка продолжает работу с подтверждённой формулой.",
        "",
        "| Вариант | Завершено / 512 | Исправлено / 256 | Ложные `DONE` | Порча кода | Входные токены | Выходные токены |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for arm in ARMS:
        row, tokens = result["measures"][arm], result["tokens"][arm]
        lines.append(f"| {NAMES[arm]} | {row['completed']} | {row['repairs']} | {row['accepted_false_DONE']} | {row['corruption']} | {tokens['processed']['mean']:.1f} | {tokens['generated']['mean']:.1f} |")
    lines += [
        "",
        "Токены приведены в среднем на эпизод с учётом первого перевода условия. Строка ожидания показывает результат до ответа пользователя. При возврате к обычному циклу учитывается его фактическая траектория на тех же входах.",
        "",
        f"Имитатору показали {confirm['requested']} предложений на {confirm['distinct_tasks']} задачах. Он подтвердил {confirm['accepted']} и отклонил {confirm['rejected']}. После подтверждения правильно завершено {confirm.get('accepted_completed', 0)} эпизодов и исправлено {confirm.get('accepted_repairs', 0)} программ. За один вызов сети завершено {confirm.get('one_call_completed', 0)} из этих эпизодов. С подтверждённой формулой в полный цикл вернулось {confirm.get('approved_full_cycle', 0)} эпизодов.",
        "",
        "| Языковая группа | Задач | Прежний разбор | Новый разбор | Совпали с эталоном на итоговых входах |",
        "|---|---:|---:|---:|---:|",
    ]
    for panel, label in PANELS.items():
        old = result["parser"]["previous"][panel]
        new = result["parser"]["new"][panel]
        lines.append(f"| {label} | {new['tasks']} | {old.get('parsed', 0)} | {new.get('parsed', 0)} | {new.get('matches_reference_on_audit', 0)} |")
    lines += ["", "| Переход | Сохранено прежних исправлений | Добавлено | Потеряно |",
              "|---|---:|---:|---:|"]
    for name, table in result["comparisons"].items():
        before, after = name.split(":")
        repair = table["transitions"]["repairs"]
        lines.append(f"| {NAMES[before]} → {NAMES[after]} | {repair['kept']} | {len(repair['gained'])} | {len(repair['lost'])} |")
    if result["example"]:
        example = result["example"]
        lines += ["", "Пример запроса с подтверждением", "", f"> {example['task']}", "",
                  "```text", example["preview"], "```"]
    native = result["native"]
    lines += ["", f"Обновлений весов было 0. CPU и C++ совпали в {native['matched']} из {native['checked']} выбранных потоков токенов. Точность ответа человека в этом эксперименте задаёт имитатор. Прогон проведён на компьютере с эмулятором МК-61.", ""]
    destination.write_text("\n".join(lines))
    return destination


def main():
    check_frozen()
    install()
    complete = read(ROOT / "complete.json")
    assert complete["complete"] and complete["weights_verified"] and complete["optimizer_updates"] == 0
    goals = {goal["id"]: goal for goal in rows(ROOT / "closed.jsonl")}
    full = read(ROOT / RESULT_FILES["full_cycle"])
    initial = {row["id"]: row["generation"] for row in full["primary"]}
    records = {arm: read(ROOT / RESULT_FILES[arm])["records"] for arm in ARMS}
    reference_ids = [row["id"] for row in records["full_cycle"]]
    assert len(reference_ids) == len(set(reference_ids)) == 512
    for data in records.values():
        assert [row["id"] for row in data] == reference_ids
    confirm, example = confirmation_summary(records["awaiting_confirmation"], records["with_confirmation"], goals)
    status_pairs = [("full_cycle", "autonomous"), ("previous_short", "autonomous"),
                    ("autonomous", "with_confirmation"), ("previous_short", "with_confirmation")]
    result = {
        "complete": True,
        "tasks": len(goals),
        "optimizer_updates": 0,
        "measures": {arm: measures(data) for arm, data in records.items()},
        "tokens": {arm: token_summary(data, initial) for arm, data in records.items()},
        "parser": {"previous": coverage(goals, expanded_parse), "new": coverage(goals, parse_task)},
        "panels": {arm: {panel: summarize_panel(data, goals, panel) for panel in PANELS} for arm, data in records.items()},
        "comparisons": {f"{a}:{b}": {"transitions": transitions(records[a], records[b]),
                                      "paired_intervals": paired(records[a], records[b])} for a, b in status_pairs},
        "confirmation": confirm,
        "example": example,
        "native": read(ROOT / "native-verification.json"),
    }
    path = report(result)
    result.update(report=str(path), report_sha256=sha(path))
    write(ROOT / "comparison.json", result)
    print({"complete": True, "report": str(path), "measures": result["measures"], "confirmation": confirm}, flush=True)


if __name__ == "__main__":
    main()
