"""Report recovery after refusal and the cost of the extra model call."""

from collections import Counter

from ay_common import read, rows, sha, write
from br_finish import paired
from ce_finish import measures, token_summary, transitions
from ch_data import ROOT
from ch_eval import ARMS, RESULT_FILES, check_frozen


LABELS = {
    "full_cycle": "Полный цикл",
    "autonomous": "Автономно",
    "one_confirmation": "Одно подтверждение",
    "ordinary_retry": "Повторный разбор",
    "refusal_retry": "Повтор после явного отказа",
}
RETRIES = ("ordinary_retry", "refusal_retry")


def retry_stats(arm, base, data, initial, goals):
    refused = {row["id"]: row for row in base if row.get("confirmation") is False}
    recovered = []
    groups = Counter()
    subset = []
    for before, after in zip(base, data["records"]):
        assert before["id"] == after["id"]
        if before["id"] not in refused:
            assert before == after
            continue
        goal = goals[after["task_id"]]
        original = goal["reference_body"] if after["initially_correct"] else goal["bad_body"]
        assert sum(event["kind"] == "retry_translation" for event in after["history"]) == 1
        if after["retry_confirmation"] is not True:
            assert after["body"] == original and not after["finished"]
        groups[after["retry_status"]] += 1
        subset.append(after)
        if after["pass"]:
            recovered.append({"id": after["id"], "task_id": after["task_id"], "task": goal["task"],
                              "first": before["formula_preview"], "second": after["retry_preview"]})
    assert len(data["attempts"]) == len({r["task_id"] for r in refused.values()})
    return {
        "arm": arm,
        "episodes": len(refused),
        "tasks": len(data["attempts"]),
        "offered_tasks": sum(value["offered"] for value in data["attempts"].values()),
        "offered_episodes": sum(r["retry_preview"] is not None for r in subset),
        "accepted_tasks": len({r["task_id"] for r in subset if r["retry_confirmation"] is True}),
        "recovered_tasks": len({row["task_id"] for row in recovered}),
        "recovered_episodes": len(recovered),
        "recovered_repairs": sum(r["pass"] and not r["initially_correct"] for r in subset),
        "accepted_false_DONE": sum(r["finished"] and not r["program_correct"] for r in subset),
        "true_start_corruption": sum(r["initially_correct"] and not r["program_correct"] for r in subset),
        "stop_reasons": dict(groups),
        "tokens_for_refused": token_summary(subset, initial) if subset else None,
        "retry_input_mean": (sum(x["generation"]["input_tokens"] for x in data["attempts"].values()) / len(data["attempts"])
                             if data["attempts"] else 0),
        "retry_output_mean": (sum(len(x["generation"]["generated_token_ids"]) for x in data["attempts"].values()) / len(data["attempts"])
                              if data["attempts"] else 0),
        "recovered": recovered,
    }


def render(result):
    lines = [
        "# Повторный перевод после отказа от формулы",
        "",
        "В новом закрытом наборе 256 задач и 512 эпизодов с правильной или ошибочной стартовой программой. На всех ветках используются прежние модели Q4 и окно 1024. Первые предложения и ответы на них совпадают. После отказа дополнительный перевод выполняется один раз с тем же условием, угловым режимом и константами. Текущая программа, исправленная формула и результаты итоговых проверок в запрос не входят.",
        "",
        "Сравниваются штатный запрос повторного разбора и запрос с сообщением об отказе. Повтор той же формулы прекращает попытку. Новая формула показывается целиком. Ответ «да» имитируется сравнением с эталоном на 32 проверочных входах. На запись влияет это подтверждение и отдельная проверка программы на 18 рабочих входах.",
        "",
        "| Вариант | Завершено / 512 | Исправлено / 256 | Ложные `DONE` | Порча | Входные токены | Выходные токены |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for arm in ARMS:
        m, t = result["measures"][arm], result["tokens"][arm]
        lines.append(f"| {LABELS[arm]} | {m['completed']} | {m['repairs']} | {m['accepted_false_DONE']} | {m['corruption']} | {t['processed']['mean']:.2f} | {t['generated']['mean']:.2f} |")
    lines += ["", "Токены указаны в среднем на эпизод и включают первоначальный перевод.", "",
              "| Повторный запрос | Задач с отказом | Новых формул | Задач восстановлено | Эпизодов восстановлено | Исправлений добавлено | Токены самого повтора, вход / выход |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for arm in RETRIES:
        r = result["retries"][arm]
        lines.append(f"| {LABELS[arm]} | {r['tasks']} | {r['offered_tasks']} | {r['recovered_tasks']} | {r['recovered_episodes']} | {r['recovered_repairs']} | {r['retry_input_mean']:.1f} / {r['retry_output_mean']:.1f} |")
    lines.append("")
    for arm in RETRIES:
        r = result["retries"][arm]
        saved = result["comparisons"][arm]["transitions"]["repairs"]
        lines.append(f"{LABELS[arm]}. Сохранено {saved['kept']} исправлений ветки с одним подтверждением, потеряно {len(saved['lost'])}. Ответы на второе предложение и причины пропуска собраны в журнале.")
    if result["example"]:
        example = result["example"]
        lines += ["", "Пример восстановленной задачи", "", f"> {example['task']}", "",
                  f"Первое предложение `{example['first'].splitlines()[0]}`. Второе предложение `{example['second'].splitlines()[0]}`."]
    p = result["native"]
    lines += ["", f"CPU и C++ совпали на {p['matched']} из {p['checked']} основных потоков и на {p['retry_matched']} из {p['retry_checked']} повторных. Обновлений весов 0. Ответы пользователя имитированы на компьютере, поэтому результаты характеризуют прохождение сценария при точном подтверждении формулы.", ""]
    path = ROOT / "SPEC_FORMULA_RETRY_RESULTS.md"
    path.write_text("\n".join(lines))
    return path


def main():
    check_frozen()
    completed = read(ROOT / "complete.json")
    assert completed["complete"] and completed["weights_verified"] and completed["optimizer_updates"] == 0
    goals = {row["id"]: row for row in rows(ROOT / "closed.jsonl")}
    data = {arm: read(ROOT / RESULT_FILES[arm]) for arm in ARMS}
    records = {arm: value["records"] for arm, value in data.items()}
    initial = {row["id"]: row["generation"] for row in data["full_cycle"]["primary"]}
    ids = [row["id"] for row in records["one_confirmation"]]
    assert len(ids) == len(set(ids)) == 512
    assert all([row["id"] for row in values] == ids for values in records.values())
    retries = {arm: retry_stats(arm, records["one_confirmation"], data[arm], initial, goals) for arm in RETRIES}
    all_examples = [row for arm in RETRIES for row in retries[arm]["recovered"]]
    result = {"complete": True, "tasks": len(goals), "optimizer_updates": 0,
              "measures": {arm: measures(values) for arm, values in records.items()},
              "tokens": {arm: token_summary(values, initial) for arm, values in records.items()},
              "retries": retries,
              "comparisons": {arm: {"transitions": transitions(records["one_confirmation"], records[arm]),
                                    "paired": paired(records["one_confirmation"], records[arm])} for arm in RETRIES},
              "native": read(ROOT / "native-verification.json"), "example": next(iter(all_examples), None)}
    path = render(result)
    result.update(report=str(path), report_sha256=sha(path))
    write(ROOT / "comparison.json", result)
    print({"complete": True, "report": str(path), "measures": result["measures"],
           "retries": {arm: {k: v for k, v in value.items() if k != "recovered"} for arm, value in retries.items()}}, flush=True)


if __name__ == "__main__":
    main()
