"""New paired arithmetic tasks for formula confirmation and three language rules."""

import argparse
import random
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from itertools import product
from unittest.mock import patch

import ce_data
import cf_data
from ay_common import read, save_rows, sha, write
from be_language import paths3, question
from bh_common import signature
from full_isa_vm import build


ROOT = cf_data.ROOT.parent / "spec-formula-confirmation-v1"
LITERALS = ["0.81273", "1.31273", "4.81273", "37.31273", "-0.81273"]
QUOTAS = {"steps": (15, 3), "structured": (15, 3), "freeform": (100, 20)}
TARGETS = ("repeat", "replace_sign", "absolute")
SEED = 261114437


def head(clauses):
    return "Сначала " + ", затем ".join(clauses)


def targeted_task(goal, index):
    spec = goal["spec"]
    expr = spec["X"]
    group = goal["wording_cohort"]
    if group == "repeat":
        op = ce_data.NOUNS[expr[0]]
        repeated = (f"дважды подряд примените {op}", f"два раза примени {op}",
                    f"примени {op} дважды подряд")[index % 3]
        prompt = head(ce_data.step_clauses(expr[1][1])) + ", затем " + repeated
    elif group == "replace_sign":
        suffix = ("полученный результат замени его знаком", "замени результат его знаком",
                  "замени полученное значение его знаком")[index % 3]
        prompt = head(ce_data.step_clauses(expr[1])) + ", а затем " + suffix
    else:
        _, middle, outer = ce_data.step_clauses(expr)
        atom = expr[1][1][1]
        source = f"содержимое {atom}" if isinstance(atom, str) else f"число {atom['constant']}"
        start = (f"Взяв {source} по модулю", f"Возьми {source} по модулю",
                 f"Вычисли {source} по модулю")[index % 3]
        prompt = f"{start}, затем {middle}, затем {outer}"
    if spec["writes"]:
        return prompt + ". Запиши ответ в " + next(iter(spec["writes"])) + "."
    return prompt + ("; какой результат?" if index % 4 == 0 else ".")


def targeted_rows(pool, rng, signatures, old_triples):
    ops = sorted(set(ce_data.NOUNS) | {"neg"})
    forms = {
        "repeat": [(op, op, inner) for op in ce_data.NOUNS for inner in ops if op != inner],
        "replace_sign": [("sign", middle, inner) for middle in ops for inner in ops if middle != inner],
        "absolute": [(outer, middle, "abs") for outer in ops for middle in ops if middle != outer and middle != "abs"],
    }
    all_rows = []
    for group, triples in forms.items():
        rng.shuffle(triples)
        selected = []
        for batch in range(0, len(triples), 16):
            jobs = []
            for i, (outer, middle, inner) in enumerate(triples[batch:batch + 16], batch):
                leaf = f"R{rng.randrange(15):X}" if i % 4 else {"constant": rng.choice(LITERALS)}
                expr = [outer, [middle, [inner, leaf]]]
                job = ce_data.item(expr, f"cg:{group}:{i:03}", "composition", rng, signatures, old_triples)
                if job is not None:
                    jobs.append(job)
            selected.extend(goal for goal in pool.map(ce_data.worker, jobs) if goal is not None)
            if len(selected) >= 16:
                break
        assert len(selected) >= 16, group
        for index, goal in enumerate(selected[:16]):
            goal["wording_cohort"] = group
            all_rows.append(ce_data.reword(goal, targeted_task(goal, index), "authored_targeted"))
            old_triples.update(paths3(goal["spec"]["X"]))
        print({"cohort": group, "tasks_ready": 16}, flush=True)
    return all_rows


def build_asts():
    ROOT.mkdir(parents=True, exist_ok=True)
    path = ROOT / "closed-asts.jsonl"
    receipt = ROOT / "ast-frozen.json"
    if receipt.exists():
        assert sha(path) == read(receipt)["sha256"]
        return
    build()
    rng = random.Random(SEED)
    goals = []
    with patch.object(ce_data, "ROOT", ROOT), patch.object(ce_data, "LITERALS", LITERALS):
        signatures, occupied, prior_files = ce_data.existing_goals()
        ops = sorted(set(ce_data.NOUNS) | {"neg"})
        available = [t for t in product(ops, repeat=3) if len(set(t)) >= 2 and t not in occupied]
        rng.shuffle(available)
        with ProcessPoolExecutor(max_workers=6) as pool:
            for cohort, (compositions, simple) in QUOTAS.items():
                group, held = ce_data.composition_rows(pool, rng, f"cg:{cohort}", compositions, available, signatures, occupied)
                occupied.update(held)
                group += ce_data.simple_rows(pool, rng, cohort, simple, signatures, occupied)
                for index, goal in enumerate(group):
                    goal["id"] = goal["id"].replace("ce:", "cg:", 1)
                    goal["wording_cohort"] = cohort
                    if cohort == "steps":
                        goal = ce_data.reword(goal, ce_data.step_question(goal["spec"], index), "authored_steps")
                    elif cohort == "structured":
                        text = question(goal["spec"], ("bracket", "chain", "named")[index % 3], goal["id"])
                        goal = ce_data.reword(goal, text, "explicit_grammar")
                    goals.append(goal)
                print({"cohort": cohort, "tasks_ready": len(group)}, flush=True)
            goals += targeted_rows(pool, rng, signatures, occupied)
    assert len(goals) == len({signature(g["spec"]) for g in goals}) == 256
    save_rows(path, goals)
    write(receipt, {"seed": SEED, "sha256": sha(path), "new_literals": LITERALS,
                    "prior_goal_files_checked": prior_files,
                    "counts": dict(Counter(g["wording_cohort"] for g in goals))})


def build_wordings():
    with patch.object(cf_data, "ROOT", ROOT):
        # Use the same eight-request worker pool and blind review as the last panel.
        cf_data.build_wordings()


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("stage", choices=("asts", "wording"))
    if cli.parse_args().stage == "asts":
        build_asts()
    else:
        build_wordings()
