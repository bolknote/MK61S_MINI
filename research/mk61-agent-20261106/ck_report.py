"""Score parent and selected training checkpoint on paired Q4 evaluations."""

import fcntl
from pathlib import Path

from ay_common import read, sha, write
from br_finish import paired
from ce_finish import transitions
from ck_data import ROOT
from ck_train import REPO, TARGET_SECONDS


def compare(split, step):
    locations = [ROOT / "eval" / f"{split}-{index:06}" for index in (0, step)]
    receipts = [read(p / "complete.json") for p in locations]
    assert all(f["weights_verified"] for f in receipts)
    for key in ("dataset_sha256", "actor_sha256"):
        assert receipts[0]["inputs"][key] == receipts[1]["inputs"][key]
    for location, receipt in zip(locations, receipts, strict=True):
        for name in ("full", "metrics", "assisted"):
            assert sha(location / (name + ".json")) == receipt[name + "_sha256"]
    counts = [read(p / "metrics.json") for p in locations]
    base_first, new_first = (read(p / "full.json")["primary"] for p in locations)
    assert [r["id"] for r in base_first] == [r["id"] for r in new_first]
    result = {"parent": counts[0], "candidate": counts[1], "first_changes": {
        "gained": [b["id"] for a, b in zip(base_first, new_first) if b["program_correct"] and not a["program_correct"]],
        "lost": [a["id"] for a, b in zip(base_first, new_first) if a["program_correct"] and not b["program_correct"]],
    }}
    for mode in ("full", "assisted"):
        a, b = (read(p / (mode + ".json"))["records"] for p in locations)
        result[mode + "_changes"] = transitions(a, b)
        result[mode + "_paired"] = paired(a, b)
    return result


def draw(results):
    training, selector, course = (results[key] for key in ("training", "selection", "course"))
    old, new = (results["closed"][key] for key in ("parent", "candidate"))
    seconds = training["update_elapsed_seconds"]
    a, b = (x["assisted"] for x in (old, new))
    rows = [
        ("Первые программы /256", old["first"]["correct"], new["first"]["correct"]),
        ("Первые программы на новых композициях /160", old["first"]["composition_correct"], new["first"]["composition_correct"]),
        ("Обе стороны пары верны /48", old["first"]["pairs_both_correct"], new["first"]["pairs_both_correct"]),
        ("Запросы подтверждения SPEC /512", old["confirmations"], new["confirmations"]),
        ("Уточнения с вариантами после отказа /512", old["clarifications"], new["clarifications"]),
        ("Остановки на расхождении с независимым разбором /512", old["blocked_known_parse_disagreement_or_check"], new["blocked_known_parse_disagreement_or_check"]),
        ("Завершено без ответа пользователя /512", old["completed_without_user"], new["completed_without_user"]),
        ("Завершено с проверкой SPEC /512", a["completed"], b["completed"]),
        ("Исправлено с проверкой SPEC /256", a["repairs"], b["repairs"]),
        ("Исправлено в полном цикле /256", old["full_cycle"]["repairs"], new["full_cycle"]["repairs"]),
        ("Принятые ложные DONE с проверкой SPEC", a["accepted_false_DONE"], b["accepted_false_DONE"]),
        ("Порча исходно правильного кода с проверкой SPEC", a["corruption"], b["corruption"]),
    ]
    lines = ["# Kon-Tiki 3M на парных условиях и новых композициях", "",
             f"Переводчик прошёл {training['optimizer_updates']} обновлений на NVIDIA B200 за {seconds / 60:.2f} минуты шагов обучения. В каждом проходе использован Q4. Контрольные снимки сохранены после 20, 40 и 60 минут. Для закрытого теста заранее выбран кандидат с шага {selector['candidate_step']} по результатам development и банка исправлений.", "",
             f"В курсе {course['train']} новых условий, в том числе {course['pairs']} пар и 256 композиций из 64 семейств. DeepSeek подготовил и вслепую проверил {course['sources'].get('deepseek_blind_reviewed', 0)} учебных формулировок. В каждом обновлении использованы обе стороны шести пар, восемь композиций и 12 прежних примеров. Банк повтора содержит {course['replay']} условий. Эталонные цели получены из деревьев операций и проверены на ROM.", "",
             "Закрытый тест содержит 256 русских условий, включая 160 задач из 32 отложенных семейств и 48 пар. У каждой задачи проверены верный и ошибочный старт. DeepSeek участвовал только в подготовке учебных формулировок. У обеих моделей тот же исполнитель и окно 1024. Подтверждение и выбор варианта имитировались отдельным проверяющим по отложенным входам.", "",
             "| Метрика | Текущая Kon-Tiki Q4 | Дообученный переводчик Q4 |", "|---|---:|---:|"]
    lines.extend(f"| {name} | {previous} | {candidate} |" for name, previous, candidate in rows)
    lines += ["", "| Проверка исправлений | Сохранено | Новых | Потеряно |", "|---|---:|---:|---:|"]
    for split, mode, label in (("closed", "assisted", "Новые задачи, проверка SPEC"), ("closed", "full", "Новые задачи, полный цикл"),
                               ("retention", "full", "48 прежних успешных исправлений, полный цикл")):
        change = results[split][mode + "_changes"]["repairs"]
        lines.append(f"| {label} | {change['kept']} | {len(change['gained'])} | {len(change['lost'])} |")
    delta = results["closed"]["first_changes"]
    lines += ["", f"По первому ответу добавлено {len(delta['gained'])} решений, потеряно {len(delta['lost'])}.", "",
              "Парные изменения и хэши исходных результатов сохранены в `comparison.json`. Проверка Q4 выполнена на компьютере с эмулятором МК-61.", ""]
    return "\n".join(lines)


def ledger(result, report):
    path = REPO / "research/mk61-agent-20261106/work-state.json"
    with (ROOT / "ledger.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = read(path)
        field = "latest_kon_tiki_paired_composition_training"
        prior = state.get(field, {})
        if prior.get("directory") != str(ROOT) or not prior.get("ledger_accounted"):
            state["completed_training_runs"] += 1
            state["total_accounted_optimizer_updates_lower_bound"] += result["training"]["optimizer_updates"]
        state[field] = {"directory": str(ROOT), "complete": True, "ledger_accounted": True, "phase": "complete",
                        "optimizer_updates": result["training"]["optimizer_updates"], "report": str(report),
                        "candidate_step": result["selection"]["candidate_step"]}
        write(path, state)


def main():
    training = read(ROOT / "training.json")
    assert training["Q4_every_forward"] and training["update_elapsed_seconds"] >= TARGET_SECONDS
    selection = read(ROOT / "preselected.json")
    assert not selection["closed_used_for_selection"]
    candidate = selection["candidate_step"]
    result = {"complete": True, "training": training, "selection": selection, "course": read(ROOT / "course.json"),
              **{split: compare(split, candidate) for split in ("closed", "retention", "development")}}
    report = ROOT / "KON_TIKI_PAIRED_COMPOSITIONS_RESULTS.md"
    report.write_text(draw(result))
    result.update(report=str(report), report_sha256=sha(report))
    write(ROOT / "comparison.json", result)
    ledger(result, report)
    print(report, flush=True)


if __name__ == "__main__":
    main()
