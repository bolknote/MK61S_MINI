"""Report the paired effects of broader parsing and parser priority."""

from collections import Counter

from ar_spec import equivalent
from ay_common import read, rows, sha, write
from bl_spec import install
from br_finish import paired
from ce_finish import measures, token_summary, transitions
from ce_short_path import spec_key
from cf_data import ROOT
from cf_eval import ARMS, check_frozen


LABELS = {
    "full_cycle": "Полный цикл",
    "strict_agreement": "Прежний короткий путь",
    "strict_priority": "Приоритет строгого парсера",
    "expanded_agreement": "Расширенный парсер с согласием модели",
    "expanded_priority": "Расширенный парсер с приоритетом",
}
GROUPS = {"steps": "Явные цепочки", "structured": "Явная грамматика", "freeform": "Свободный русский"}
CHANGES = (
    ("strict_agreement", "strict_priority"),
    ("strict_agreement", "expanded_agreement"),
    ("strict_priority", "expanded_priority"),
    ("expanded_agreement", "expanded_priority"),
    ("strict_agreement", "expanded_priority"),
    ("full_cycle", "expanded_priority"),
)


def parse_coverage(goals, records):
    by_task = {row["task_id"]: row["independent_parse"] for row in records}
    counts = {group: Counter() for group in GROUPS}
    for task_id, spec in by_task.items():
        goal = goals[task_id]
        c = counts[goal["wording_cohort"]]
        c["tasks"] += 1
        c["parsed"] += spec is not None
        if spec is None:
            continue
        c["same_tree"] += spec_key(spec) == spec_key(goal["spec"])
        c["passes_intent_audit"] += equivalent(spec, goal["spec"], goal["audit_inputs"])["tested_equal"]
    return {group: dict(values) for group, values in counts.items()}


def route_stats(records):
    short = [row for row in records if row.get("route") in ("kept_program", "compiled_program")]
    fallback = [row for row in records if row.get("route") == "full_cycle"]
    return {
        "short_tasks": len({row["task_id"] for row in short}),
        "short_episodes": len(short),
        "short_correct": sum(row["pass"] for row in short),
        "short_false_DONE": sum(not row["pass"] for row in short),
        "disagreements_resolved": sum(not row["initial_agreement"] for row in short),
        "fallback_reasons": dict(Counter(row["fallback_reason"] for row in fallback)),
        "confirmation_needed": sum(row.get("route") == "needs_confirmation" for row in records),
    }


def report(result):
    destination = ROOT / "SPEC_SHORT_PATH_AUTHORITY_RESULTS.md"
    lines = [
        "# Приоритет независимой SPEC и расширение русского разбора",
        "",
        "На новом закрытом наборе было 256 задач. Для каждой проверили правильную и ошибочную стартовые программы. DeepSeek составил 160 свободных условий, которые прошли два слепых обратных разбора. Остальные 96 условий проверяют явные цепочки и структурированную грамматику. Выражения, константы и состав групп зафиксировали до прогона Q4.",
        "",
        "Сравнение использует те же Q4 веса исполнителя и переводчика BU1500, окно 1024 и FP32 KV. Первоначальный перевод засчитан в каждом эпизоде. Короткий путь сохраняет проверенный код или проверяет скомпилированный кандидат на 18 входах до замены. Отдельные 32 входа с эталоном служат для подсчёта ошибок. При возврате к полному циклу используется его фактическая траектория с теми же входами.",
        "",
        "| Вариант | Завершено / 512 | Исправлено / 256 | Ложные `DONE` | Порча кода | Обработано входных токенов | Выходных токенов |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for arm, label in LABELS.items():
        row, tok = result["measures"][arm], result["tokens"][arm]
        lines.append(f"| {label} | {row['completed']} | {row['repairs']} | {row['accepted_false_DONE']} | {row['corruption']} | {tok['processed']['mean']:.1f} | {tok['generated']['mean']:.1f} |")
    lines += [
        "",
        "Токены указаны в среднем на эпизод. Вход учитывает фактически обработанные запросы, а выход берётся из журнала с тем же соглашением о служебных токенах, что в предыдущем тесте. Принятый `DONE` считается ложным, если код провалил итоговую проверку. Порча измеряет итоговый код на стартах с верной программой.",
        "",
        "| Вариант | Коротких эпизодов | Из них ложных | Расхождений разрешено | Нужны уточнения | Ложные заявки `DONE` сети |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for arm in ARMS:
        row = result["routes"][arm]
        claims = result["measures"][arm]["false_DONE_claims"]
        lines.append(f"| {LABELS[arm]} | {row['short_episodes']} | {row['short_false_DONE']} | {row['disagreements_resolved']} | {row['confirmation_needed']} | {claims} |")
    lines += [
        "",
        "| Разбор текста | Формулировки | Задач | Разобрано | Совпали на итоговых входах |",
        "|---|---|---:|---:|---:|",
    ]
    for parser, groups in result["parser_coverage"].items():
        for group, values in groups.items():
            lines.append(f"| {parser} | {GROUPS[group]} | {values['tasks']} | {values['parsed']} | {values['passes_intent_audit']} |")
    lines += [
        "",
        "| Вариант на свободном русском | Завершено / 320 | Исправлено / 160 | Коротких эпизодов | Ложные `DONE` | Порча кода |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for arm, label in LABELS.items():
        row = result["freeform"][arm]
        lines.append(f"| {label} | {row['completed']} | {row['repairs']} | {row['short_episodes']} | {row['accepted_false_DONE']} | {row['corruption']} |")
    lines += [
        "",
        "| Изменение | Сохранено исправлений | Добавлено | Потеряно | Изменение завершений, п.п. | 95% интервал, п.п. |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for before, after in CHANGES:
        comparison = result["comparisons"][f"{before}:{after}"]
        repair = comparison["transitions"]["repairs"]
        delta = comparison["paired"]["completion"]
        lo, hi = delta["CI95_task_bootstrap"]
        lines.append(f"| {LABELS[before]} → {LABELS[after]} | {repair['kept']} | {len(repair['gained'])} | {len(repair['lost'])} | {delta['delta_percentage_points']:+.2f} | [{lo:+.2f}, {hi:+.2f}] |")
    coverage = result["parser_coverage"]["Расширенный"]["freeform"]
    parity = result["native"]
    lines += [
        "",
        f"Расширенный парсер разобрал {coverage['parsed']} из {coverage['tasks']} свободных условий. Совпадение формул здесь означает проверку на конечном наборе входов. Тест охватывает вычисления без переходов с сохранением результата максимум в один регистр.",
        f"Обновлений весов было 0. На компьютере совпало {parity['matched']} из {parity['checked']} проверенных потоков токенов CPU и C++. Короткий путь исполнялся в исследовательской упряжи с эмулятором МК-61.",
        "",
    ]
    destination.write_text("\n".join(lines))
    return destination


def main():
    check_frozen()
    install()
    complete = read(ROOT / "complete.json")
    assert complete["complete"] and complete["weights_verified"] and complete["optimizer_updates"] == 0
    goals = {goal["id"]: goal for goal in rows(ROOT / "closed.jsonl")}
    full = read(ROOT / "full-cycle.json")
    initial = {row["id"]: row["generation"] for row in full["primary"]}
    records = {"full_cycle": full["records"]}
    for arm in ARMS:
        records[arm] = read(ROOT / f"{arm}.json")["records"]
        assert [row["id"] for row in records[arm]] == [row["id"] for row in full["records"]]
        for baseline, row in zip(full["records"], records[arm]):
            if row["route"] == "full_cycle":
                assert all(row[key] == value for key, value in baseline.items())

    free = {arm: [row for row in values if goals[row["task_id"]]["wording_cohort"] == "freeform"] for arm, values in records.items()}
    result = {
        "complete": True,
        "tasks": len(goals),
        "optimizer_updates": 0,
        "measures": {arm: measures(values) for arm, values in records.items()},
        "tokens": {arm: token_summary(values, initial) for arm, values in records.items()},
        "routes": {arm: route_stats(values) for arm, values in records.items()},
        "freeform": {arm: {**measures(values), **route_stats(values)} for arm, values in free.items()},
        "parser_coverage": {"Строгий": parse_coverage(goals, records["strict_priority"]),
                            "Расширенный": parse_coverage(goals, records["expanded_priority"])},
        "comparisons": {f"{a}:{b}": {"transitions": transitions(records[a], records[b]), "paired": paired(records[a], records[b])}
                        for a, b in CHANGES},
        "native": read(ROOT / "native-verification.json"),
        "wording_sources": read(ROOT / "wording-frozen.json")["wording_sources"],
        "closed_sha256": sha(ROOT / "closed.jsonl"),
    }
    assert all(row["episodes"] == 512 for row in result["measures"].values())
    path = report(result)
    result.update(report=str(path), report_sha256=sha(path))
    write(ROOT / "comparison.json", result)
    print({"complete": True, "report": str(path), "measures": result["measures"], "routes": result["routes"]}, flush=True)


if __name__ == "__main__":
    main()
