"""Score the sealed paired Q4 run and report its token and outcome changes."""

from collections import Counter
from statistics import mean, median

from ay_common import read, rows, sha, write
from br_finish import paired
from ce_data import HERE, ROOT
from ce_eval import check_frozen
from ce_short_path import parse_task, spec_key


def token_counts(row, initial):
    generations = [initial, *(h["generation"] for h in row["history"] if "generation" in h)]
    return {
        "requests": len(generations),
        "submitted": sum(g["input_tokens"] for g in generations),
        "processed": sum(g["input_tokens"] for g in generations if "cache" in g),
        "generated": sum(len(g["generated_token_ids"]) for g in generations),
        "max_KV": max((g.get("cache", {}).get("tokens", 0) for g in generations), default=0),
    }


def token_summary(records, initial):
    values = [token_counts(row, initial[row["task_id"]]) for row in records]
    return {name: {"total": sum(value[name] for value in values),
                   "mean": mean(value[name] for value in values),
                   "median": median(value[name] for value in values),
                   "max": max(value[name] for value in values)} for name in values[0]}


def transitions(old, new):
    def ids(predicate, table):
        return {row["id"] for row in table if predicate(row)}

    def changes(predicate):
        baseline, candidate = ids(predicate, old), ids(predicate, new)
        return {"kept": len(baseline & candidate), "lost": sorted(baseline - candidate), "gained": sorted(candidate - baseline)}

    return {
        "repairs": changes(lambda r: r["pass"] and not r["initially_correct"]),
        "correct_starts": changes(lambda r: r["pass"] and r["initially_correct"]),
        "accepted_false_DONE": changes(lambda r: r["finished"] and not r["program_correct"]),
        "corruption": changes(lambda r: r["initially_correct"] and not r["program_correct"]),
    }


def measures(records):
    return {
        "episodes": len(records),
        "completed": sum(r["pass"] for r in records),
        "repairs": sum(r["pass"] and not r["initially_correct"] for r in records),
        "correct_starts_completed": sum(r["pass"] and r["initially_correct"] for r in records),
        "accepted_false_DONE": sum(r["finished"] and not r["program_correct"] for r in records),
        "false_DONE_claims": sum(r["false_DONE_claims"] for r in records),
        "corruption": sum(r["initially_correct"] and not r["program_correct"] for r in records),
        "overflows": sum(any(h.get("generation", {}).get("codec_error") == "context_overflow" for h in r["history"]) for r in records),
        "refusals": sum(r["abstained"] for r in records),
    }


def parser_stats(goals, primary, result):
    initial = {row["id"]: row["declared_spec"] for row in primary}
    counts = {}
    for goal in goals:
        group = counts.setdefault(goal["wording_cohort"], Counter())
        group["tasks"] += 1
        parse = parse_task(goal["task"], goal["spec"]["angle"])
        if parse is None:
            continue
        group["parsed"] += 1
        group["correct_structure"] += spec_key(parse) == spec_key(goal["spec"])
        model = initial[goal["id"]]
        group["agreed_with_model"] += model is not None and spec_key(parse) == spec_key(model)
    cohort = {g["id"]: g["wording_cohort"] for g in goals}
    for row in result:
        group = counts[cohort[row["task_id"]]]
        group["accepted_short"] += row["route"] != "full_cycle"
        group["false_short"] += row["route"] != "full_cycle" and not row["pass"]
    return {name: dict(count) for name, count in counts.items()}


def write_report(result):
    old, new = result["full_cycle"], result["short_path"]
    before, after = result["tokens"]["full_cycle"], result["tokens"]["short_path"]
    repairs = result["transitions"]["repairs"]
    selected = result["fast_only"]
    lines = [
        "# Короткий путь с независимой проверкой SPEC",
        "",
        "В новом закрытом тесте было 256 задач и 512 эпизодов. Каждую задачу проверили с правильной и ошибочной стартовой программой. Использовали рабочий исполнитель и переводчик BU1500 с теми же Q4 пакетами, окном 1024 и FP32 KV. Обновлений весов было 0.",
        "",
        "Короткий путь сопоставляет независимый разбор всего текста и SPEC модели по дереву операций, аргументам, режиму углов и записям в память. При совпадении упряжь сохраняет подходящий код или компилирует SPEC, прогоняет программу на двух открытых и 16 проверочных входах и завершает задачу. В остальных случаях используется полный цикл с прежними входами. Для итоговой оценки используются 32 отдельных входа на задачу.",
        "",
        "| Метрика | Полный цикл | Короткий путь с возвратом к полному |",
        "|---|---:|---:|",
    ]
    for key, label in (("completed", "Правильные завершения / 512"), ("repairs", "Исправления / 256"),
                       ("correct_starts_completed", "Завершения с правильным стартом / 256"),
                       ("accepted_false_DONE", "Принятые ложные DONE"), ("false_DONE_claims", "Ложные заявки DONE сети"),
                       ("corruption", "Итоговая порча правильного кода / 256"), ("overflows", "Эпизоды с переполнением")):
        lines.append(f"| {label} | {old[key]} | {new[key]} |")
    lines += [
        "",
        f"Из {old['repairs']} исправлений полного цикла сохранены {repairs['kept']}, потеряны {len(repairs['lost'])}. Новых исправлений {len(repairs['gained'])}.",
        f"Короткий путь завершил {selected['episodes']} эпизодов, из них {selected['correct_starts_completed']} с сохранением кода и {selected['repairs']} с исправлением. Ложных принятых завершений на этом пути {selected['accepted_false_DONE']}.",
        "",
        "| Токены и вызовы на эпизод | Полный цикл | Короткий путь с возвратом к полному |",
        "|---|---:|---:|",
    ]
    for key, label in (("requests", "Запросы к модели"), ("submitted", "Входные токены в отправленных запросах"),
                       ("processed", "Входные токены в обработанных запросах"), ("generated", "Выходные токены")):
        lines.append(f"| {label}, среднее | {before[key]['mean']:.2f} | {after[key]['mean']:.2f} |")
    lines += [
        "",
        "Первый перевод учитывается в каждом из двух стартов. В сумме отправленных токенов учтены запросы, отклонённые по длине. Обработанные токены учитывают вызовы, которые дошли до вычислений. Выход считается по журналу токенов действия и тела. Служебный конец тела в это число не входит. Для возврата к полному циклу повторно используется его фактическая детерминированная траектория с теми же входами.",
        "",
        "| Тип формулировки | Задач | Независимый разбор | Совпадение с моделью | Коротких завершений | Из них ложных |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    names = {"steps": "Явная цепочка", "structured": "Явная грамматика", "freeform": "Свободный русский"}
    for name, count in result["parser"].items():
        lines.append(f"| {names[name]} | {count['tasks']} | {count.get('parsed', 0)} | {count.get('agreed_with_model', 0)} | {count['accepted_short']} | {count['false_short']} |")
    lines += [
        "",
        f"Распределение источников условий: {result['wording_sources']}.",
        "Формулировки явных цепочек и грамматики заданы для измерения покрытия поддерживаемого синтаксиса. Покрытие всего смешанного набора зависит от долей этих групп. Формулы ограничены прямолинейной арифметикой и записью результата в один регистр.",
        "",
        "| Парное изменение, п.п. | Оценка | 95% интервал по задачам |",
        "|---|---:|---:|",
    ]
    for key, label in (("completion", "Завершения"), ("repairs", "Исправления"),
                       ("accepted_false_DONE", "Принятые ложные DONE"), ("corruption", "Итоговая порча")):
        value = result["paired_intervals"][key]
        lo, hi = value["CI95_task_bootstrap"]
        lines.append(f"| {label} | {value['delta_percentage_points']:+.2f} | [{lo:+.2f}, {hi:+.2f}] |")
    lines += [
        "",
        f"На компьютере сравнили {result['native']['checked']} потоков токенов CPU и C++. Совпали {result['native']['matched']}. Числа в отчёте относятся к прогону CPU и эмулятору МК-61.",
        "",
    ]
    report = HERE / "SPEC_SHORT_PATH_RESULTS.md"
    report.write_text("\n".join(lines))
    return report


def main():
    check_frozen()
    complete = read(ROOT / "complete.json")
    assert complete["complete"] and complete["optimizer_updates"] == 0 and complete["weights_verified"]
    goals = rows(ROOT / "closed.jsonl")
    full = read(ROOT / "full-cycle.json")
    old, new = full["records"], read(ROOT / "short-path.json")["records"]
    assert [r["id"] for r in old] == [r["id"] for r in new]
    assert len(old) == len(new) == 2 * len(goals) == 512
    initial = {r["id"]: r["generation"] for r in full["primary"]}
    fast = [r for r in new if r["route"] != "full_cycle"]
    short_ids = {r["id"] for r in fast}
    for a, b in zip(old, new):
        if b["route"] == "full_cycle":
            assert all(b[k] == a[k] for k in a)
    result = {
        "complete": True,
        "tasks": len(goals),
        "optimizer_updates": 0,
        "full_cycle": measures(old),
        "short_path": measures(new),
        "fast_only": measures(fast),
        "transitions": transitions(old, new),
        "tokens": {"full_cycle": token_summary(old, initial), "short_path": token_summary(new, initial),
                   "fast_only": token_summary(fast, initial),
                   "matched_full_for_fast": token_summary([r for r in old if r["id"] in short_ids], initial)},
        "fallback_reasons": dict(Counter(r["fallback_reason"] for r in new if r["route"] == "full_cycle")),
        "parser": parser_stats(goals, full["primary"], new),
        "wording_sources": dict(Counter(g["wording_source"] for g in goals)),
        "paired_intervals": paired(old, new),
        "native": read(ROOT / "native-verification.json"),
        "closed_sha256": sha(ROOT / "closed.jsonl"),
    }
    report = write_report(result)
    result["report"] = str(report)
    result["report_sha256"] = sha(report)
    write(ROOT / "comparison.json", result)
    state_path = HERE / "work-state.json"
    state = read(state_path)
    state["latest_short_path_comparison"] = {"complete": True, "optimizer_updates": 0, "report": str(report),
                                             "full_cycle": result["full_cycle"], "short_path": result["short_path"]}
    if state.get("active_experiment") in (None, "spec-short-path-v1"):
        state.update(active_experiment=None, all_own_jobs_complete=True, phase="short_path_comparison_complete")
    write(state_path, state)
    print({"complete": True, "report": str(report), "full_cycle": result["full_cycle"],
           "short_path": result["short_path"], "fast_only": result["fast_only"]}, flush=True)


if __name__ == "__main__":
    main()
