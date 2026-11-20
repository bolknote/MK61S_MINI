"""Create the three-hour continuation report from completed Q4 trajectories."""

from unittest.mock import patch

import ck_report
from ay_common import read, sha, write
from cl_data import ROOT
from cl_eval import PARENT_STEP, evaluation_folder, repair_ids


def make_report():
    policy = read(ROOT / "policy.json")
    training = read(ROOT / "training.json")
    selection = read(ROOT / "preselected.json")
    assert training["update_elapsed_seconds"] >= policy["seconds"] and training["Q4_every_forward"]
    assert not selection["selection_uses_closed_results"]
    steps = selection["closed_steps"]
    assert steps[:2] == [0, PARENT_STEP]
    metrics, transitions, recovery = {}, {}, {}
    for step in steps:
        folder = evaluation_folder("closed", step)
        complete = read(folder / "complete.json")
        assert complete["inputs"]["step"] == step and complete["weights_verified"]
        for name in ("metrics", "full", "assisted"):
            assert sha(folder / (name + ".json")) == complete[name + "_sha256"]
        metrics[str(step)] = read(folder / "metrics.json")
        recovery[str(step)] = sorted(repair_ids(step))
        if step != 0:
            with patch.object(ck_report, "ROOT", ROOT):
                transitions[str(step)] = ck_report.compare("closed", step)
    from ce_finish import transitions as outcome_transitions
    parent_comparison = {}
    for step in steps[2:]:
        a, b = (evaluation_folder("closed", i) for i in (PARENT_STEP, step))
        first_a, first_b = (read(p / "full.json")["primary"] for p in (a, b))
        assert [r["id"] for r in first_a] == [r["id"] for r in first_b]
        first = {"gained": [y["id"] for x, y in zip(first_a, first_b) if y["program_correct"] and not x["program_correct"]],
                 "lost": [x["id"] for x, y in zip(first_a, first_b) if x["program_correct"] and not y["program_correct"]]}
        parent_comparison[str(step)] = {"first": first, **{
            mode: outcome_transitions(read(a / (mode + ".json"))["records"], read(b / (mode + ".json"))["records"])
            for mode in ("full", "assisted")}}
    labels = {0: "До первого обучения", PARENT_STEP: "Часовой родитель"}
    labels.update({step: f"Шаг {step}" for step in steps[2:]})
    lines = ["# Kon-Tiki 3M после трёхчасового дообучения", "",
             f"Выполнено {training['optimizer_updates']} обновлений в Q4 на B200 за {training['update_elapsed_seconds']/60:.2f} минуты. Продолжено обучение переводчика из часового снимка. В курсе три разобранных исправления, {policy['previous_composition_errors']} известных ошибок и {policy['DeepSeek_variants']} проверенных переформулировок DeepSeek.", "",
             "Закрытый тест содержит 256 новых задач, включая 160 композиций и 48 пар. На каждом условии проверены правильный и ошибочный старты. Снимок выбирался на отдельной валидации. Упряжь и действия исполнителя одинаковы. Ответы пользователя на запросы SPEC имитировались через отложенные входы эмулятора.", "",
             "| Метрика | " + " | ".join(labels[step] for step in steps) + " |",
             "|---|" + "---:|" * len(steps)]
    for title, value in (
        ("Первая программа /256", lambda m: m["first"]["correct"]),
        ("Новые композиции /160", lambda m: m["first"]["composition_correct"]),
        ("Обе стороны пары /48", lambda m: m["first"]["pairs_both_correct"]),
        ("Подтверждения /512", lambda m: m["confirmations"]),
        ("Уточнения после отказа /512", lambda m: m["clarifications"]),
        ("Завершения с проверкой SPEC /512", lambda m: m["assisted"]["completed"]),
        ("Исправлено с проверкой SPEC /256", lambda m: m["assisted"]["repairs"]),
        ("Исправлено в полном цикле /256", lambda m: m["full_cycle"]["repairs"]),
        ("Ложные DONE в полном цикле", lambda m: m["full_cycle"]["accepted_false_DONE"]),
        ("Порча кода в полном цикле", lambda m: m["full_cycle"]["corruption"]),
        ("Ложные DONE с проверкой SPEC", lambda m: m["assisted"]["accepted_false_DONE"]),
        ("Порча кода с проверкой SPEC", lambda m: m["assisted"]["corruption"]),
    ):
        lines.append("| " + " | ".join([title, *(str(value(metrics[str(step)])) for step in steps)]) + " |")
    targets = set(selection["targets"])
    lines += ["", "| Снимок | Известные три исправления /3 | Прежние исправления часового снимка |",
              "|---|---:|---:|"]
    for step in steps:
        ids = set(recovery[str(step)])
        keep = set(selection["parent_repairs_ids"]) - targets
        lines.append(f"| {labels[step]} | {len(ids & targets)} | {len(ids & keep)}/{len(keep)} |")
    lines += ["", "Три целевых случая входили в курс. Их результат показывает восстановление конкретных исправлений. Перенос измерен на закрытом тесте.", ""]
    report = ROOT / "KON_TIKI_COMPOSITION_RECOVERY_RESULTS.md"
    report.write_text("\n".join(lines))
    output = {"complete": True, "policy": policy, "training": training, "selection": selection, "metrics": metrics,
              "recovery": recovery, "vs_original": transitions, "vs_hour": parent_comparison,
              "report": report.name, "report_sha256": sha(report)}
    write(ROOT / "comparison.json", output)
    return output


if __name__ == "__main__":
    make_report()
