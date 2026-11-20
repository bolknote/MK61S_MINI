"""Report the paired results of formula choices and an ordinary model retry."""

from collections import Counter
import json
from statistics import mean

from ay_common import read, rows, sha, write
from br_finish import paired
from ce_finish import measures, token_summary, transitions
from ci_data import ROOT
from ci_eval import ARMS, RESULT_FILES, check_frozen


LABELS = {
    "full_cycle": "Полный цикл",
    "prior_confirmation": "Прежнее подтверждение",
    "canonical_confirmation": "С учётом двух записей степени десяти",
    "ordinary_retry": "Обычный повтор после отказа",
    "clarification": "Выбор одной правки после отказа",
}
COMPARISONS = (
    ("prior_confirmation", "canonical_confirmation"),
    ("canonical_confirmation", "ordinary_retry"),
    ("canonical_confirmation", "clarification"),
    ("ordinary_retry", "clarification"),
)


def initial_body(goal, episode):
    return goal["reference_body"] if episode["initially_correct"] else goal["bad_body"]


def responses(arm, baseline, result, attempts, goals):
    counts = Counter()
    tasks = set()
    for before, after in zip(baseline, result):
        if before.get("confirmation") is not False:
            assert before == after
            continue
        task = after["task_id"]
        counts["refusals"] += 1
        assert task in attempts
        if arm == "clarification":
            events = [h for h in after["history"] if h["kind"] == "targeted_clarification"]
            assert len(events) == 1
            question = events[0]["asked"]
            accepted = bool(events[0]["selected"])
            assert not any("generation" in h for h in after["history"][len(before["history"]):])
            if accepted:
                picked = attempts[task]["options"][events[0]["selected"] - 1]
                if after["finished"]:
                    assert after["declared_spec"] == json.loads(picked["preview"]["serialized_spec"])
        else:
            events = [h for h in after["history"] if h["kind"] == "retry_translation"]
            assert len(events) == 1
            question = after["retry_preview"] is not None
            accepted = after["retry_confirmation"] is True
        if not accepted:
            assert not after["finished"] and after["body"] == initial_body(goals[task], after)
        counts["additional_questions"] += question
        counts["selected"] += accepted
        counts["completed"] += after["pass"]
        counts["repairs"] += after["pass"] and not after["initially_correct"]
        counts["failed_after_selection"] += accepted and not after["pass"]
        if after["pass"]:
            tasks.add(task)
    counts["refused_tasks"] = len(attempts)
    counts["recovered_tasks"] = len(tasks)
    if arm == "clarification":
        questions = [a for a in attempts.values() if a["question"]]
        counts["mean_options"] = mean(len(a["options"]) for a in questions) if questions else 0
    return dict(counts)


def alias_changes(before, after, goals):
    saved = []
    for previous, current in zip(before, after):
        if previous == current:
            continue
        goal = goals[current["task_id"]]
        assert current["body"] == initial_body(goal, current) and current["route"] == "kept_program"
        saved.append(current["id"])
    return {"preserved_at_entry": len(saved), "episodes": saved,
            "pow10_control_episodes": sum(goals[identity.rsplit(":", 1)[0]]["wording_cohort"] == "pow10" for identity in saved),
            "requests_avoided": sum(before_row["route"] == "needs_confirmation" and after_row["finished"]
                                    for before_row, after_row in zip(before, after))}


def example_for(choices, goals):
    for row in choices["records"]:
        if row["pass"] and row.get("clarification_choice"):
            attempt = choices["attempts"][row["task_id"]]
            return {"task": goals[row["task_id"]]["task"], "question": attempt["question"], "selected": attempt["selected"]}
    return None


def render(result):
    lines = [
        "# Уточнение одной правки к формуле",
        "",
        "На новом закрытом наборе Q4 было 256 задач и 512 эпизодов. Каждую задачу проверили с верной и ошибочной программой. Из них 160 задач имеют свободные русские формулировки и 32 проверяют запись степени десяти. Рабочие модели и окно 1024 взяты из прежнего прогона.",
        "",
        "После отказа упряжь строит до трёх вариантов с одной правкой. Она выбирает кандидатов по словам, числам и регистрам в тексте. Для имитации ответа отдельный проверяющий возвращает номер подходящего варианта или вариант «ни один». Упряжь проверяет исходную программу или компиляцию выбранной формулы на 18 рабочих входах перед завершением. Проверяющий сравнивает формулы на 32 отложенных входах.",
        "",
        "| Вариант | Завершено / 512 | Исправлено / 256 | Ложные `DONE` | Порча кода | Обработанные входные токены | Выходные токены |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for arm in ARMS:
        m, t = result["measures"][arm], result["tokens"][arm]
        lines.append(f"| {LABELS[arm]} | {m['completed']} | {m['repairs']} | {m['accepted_false_DONE']} | {m['corruption']} | {t['processed']['mean']:.2f} | {t['generated']['mean']:.2f} |")
    lines += ["", "Расход токенов приведён в среднем на эпизод. В него входит первый перевод. Вопрос с вариантами строится программно.", "",
              "| Вариант | Задач с отказом | Дополнительных вопросов на 512 эпизодов | Задач восстановлено | Эпизодов восстановлено | Дополнительных исправлений |",
              "|---|---:|---:|---:|---:|---:|"]
    for arm in ("ordinary_retry", "clarification"):
        r = result["responses"][arm]
        lines.append(f"| {LABELS[arm]} | {r['refused_tasks']} | {r['additional_questions']} | {r['recovered_tasks']} | {r['completed']} | {r['repairs']} |")
    p = result["power_alias"]
    lines += ["", f"Проверка `pow10(x)` и `10^x` сохранила исходный код в {p['preserved_at_entry']} эпизодах, где прежний короткий путь его не принял. {p['pow10_control_episodes']} таких эпизодов пришлись на контрольную группу степени десяти. Уточнений при известном расхождении структуры стало меньше на {p['requests_avoided']}.", "",
              "| Сравнение | Исходных исправлений сохранено | Добавлено | Потеряно |",
              "|---|---:|---:|---:|"]
    for a, b in COMPARISONS:
        r = result["comparisons"][f"{a}:{b}"]["transitions"]["repairs"]
        lines.append(f"| {LABELS[a]} → {LABELS[b]} | {r['kept']} | {len(r['gained'])} | {len(r['lost'])} |")
    if result["example"]:
        case = result["example"]
        lines += ["", "Пример уточнения", "", f"> {case['task']}", "", "```text", case["question"], "```",
                  f"Проверяющий выбрал вариант {case['selected']}."]
    native = result["native"]
    lines += ["", f"Обновлений весов 0. CPU и C++ совпали на {native['matched'] + native['retry_matched']} из {native['checked'] + native['retry_checked']} проверенных потоков. Прогон выполнен на компьютере с эмулятором МК-61. Выбор варианта измерялся с имитатором пользователя и конечным набором проверочных входов.", ""]
    path = ROOT / "SPEC_FORMULA_CLARIFICATION_RESULTS.md"
    path.write_text("\n".join(lines))
    return path


def main():
    check_frozen()
    proof = read(ROOT / "complete.json")
    assert proof["complete"] and proof["optimizer_updates"] == 0 and proof["weights_verified"]
    goals = {goal["id"]: goal for goal in rows(ROOT / "closed.jsonl")}
    data = {arm: read(ROOT / RESULT_FILES[arm]) for arm in ARMS}
    records = {arm: value["records"] for arm, value in data.items()}
    initial = {row["id"]: row["generation"] for row in data["full_cycle"]["primary"]}
    ids = [row["id"] for row in records["full_cycle"]]
    assert len(ids) == len(set(ids)) == 512
    assert all([row["id"] for row in values] == ids for values in records.values())
    baseline = records["canonical_confirmation"]
    result = {
        "complete": True, "tasks": len(goals), "optimizer_updates": 0,
        "measures": {arm: measures(values) for arm, values in records.items()},
        "tokens": {arm: token_summary(values, initial) for arm, values in records.items()},
        "power_alias": alias_changes(records["prior_confirmation"], baseline, goals),
        "comparisons": {f"{a}:{b}": {"transitions": transitions(records[a], records[b]),
                                      "paired": paired(records[a], records[b])} for a, b in COMPARISONS},
        "responses": {arm: responses(arm, baseline, records[arm], data[arm]["attempts"], goals)
                      for arm in ("ordinary_retry", "clarification")},
        "native": read(ROOT / "native-verification.json"),
        "example": example_for(data["clarification"], goals),
    }
    path = render(result)
    result.update(report=str(path), report_sha256=sha(path))
    write(ROOT / "comparison.json", result)
    print({"complete": True, "report": str(path), "measures": result["measures"],
           "power_alias": result["power_alias"], "responses": result["responses"]}, flush=True)


if __name__ == "__main__":
    main()
