"""Build a new paired test set before any model generations are inspected."""

import json
import random
import re
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from itertools import product
from pathlib import Path

from ay_codec import compile_spec, encode
from ay_common import read, rows, save_rows, sha, write
from az_data import numbers, tree
from az_teacher import pool_for
from be_language import paths3, question
from bh_common import signature
from bs_data import worker
from bu_data import known
from full_isa_math import BINARY, UNARY
from full_isa_vm import build
from ha_protocol import assemble


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
ROOT = REPO / ".build/mk61-agent-20261106/spec-short-path-v1"
SEED = 261113601
LITERALS = ["0.68437", "2.18437", "4.68437", "57.18437", "-0.68437"]
QUOTAS = {"steps": (40, 8), "structured": (40, 8), "freeform": (80, 16)}
NOUNS = {
    "abs": "модуль", "asin": "арксинус", "acos": "арккосинус", "atan": "арктангенс",
    "sin": "синус", "cos": "косинус", "tan": "тангенс", "sqrt": "квадратный корень",
    "square": "квадрат", "ln": "натуральный логарифм", "log10": "десятичный логарифм",
    "exp": "экспоненту", "reciprocal": "обратную величину", "sign": "знак",
}
FOLLOW = {"+": "прибавь", "-": "вычти", "*": "умножь на", "/": "раздели на", "pow": "возведи в степень"}


def existing_goals():
    signatures, triples = known()
    old_numbers = set()
    files = set()
    for path in ROOT.parent.glob("**/*.jsonl"):
        if ROOT in path.parents or path.stat().st_size > 100_000_000:
            continue
        if not re.match(r"(?:train|development|closed|retention|retired|replay|anchors|regressions|composition-regression|hard|wording|new_ast|inputs)(?:[-.]|$)", path.name):
            continue
        files.add(path)
    for path in sorted(files):
        with path.open() as stream:
            for line in stream:
                if not line.strip():
                    continue
                row = json.loads(line)
                for key in ("spec", "goal_spec", "bad_spec"):
                    spec = row.get(key)
                    if not isinstance(spec, dict) or "X" not in spec or "angle" not in spec:
                        continue
                    signatures.add(signature(spec))
                    triples.update(paths3(spec["X"]))
                    old_numbers.update(numbers(spec["X"]))
    assert not (old_numbers & {n.lstrip("-") for n in LITERALS})
    return signatures, triples, len(files)


def make_spec(expr, rng):
    writes = {f"R{rng.randrange(15):X}": expr} if rng.random() < 0.30 else {}
    return {"X": expr, "writes": writes, "angle": rng.choice(["RAD", "DEG", "GRAD"])}


def item(expr, identity, family, rng, signatures, old_triples, held=()):
    spec = make_spec(expr, rng)
    key = signature(spec)
    if key in signatures or paths3(expr) & old_triples:
        return None
    signatures.add(key)
    return (spec, identity, "closed", family, rng.randrange(2**31), "bracket",
            rng.choice(["operation", "argument", "order"]), held)


def composition_rows(pool, rng, prefix, count, available, signatures, old_triples):
    output = []
    used = []
    while len(output) < count:
        if not available:
            raise RuntimeError("Not enough unused composition families")
        outer, middle, inner = triple = available.pop()
        jobs = []
        for i in range(24):
            expr = [outer, [middle, [inner, f"R{rng.randrange(15):X}"]]]
            if i % 2:
                expr = [rng.choice(["+", "-", "*"]), expr, {"constant": rng.choice(LITERALS)}]
            job = item(expr, f"{prefix}:composition:{len(used):02}:{i:02}", "composition", rng, signatures, old_triples)
            if job is not None:
                jobs.append(job)
        candidates = [row for row in pool.map(worker, jobs) if row is not None]
        if len(candidates) >= 5:
            output.extend(candidates[:5])
            used.append(triple)
    return output, used


def simple_expression(family, cohort, rng):
    reg = f"R{rng.randrange(15):X}"
    literal = {"constant": rng.choice(LITERALS)}
    if family == "unary":
        ops = list(NOUNS) + ["neg"] if cohort == "steps" else list(UNARY)
        return [rng.choice(ops), reg]
    if family == "binary":
        operands = [reg, literal]
        if rng.random() < 0.25:
            operands.reverse()
        return [rng.choice(list(BINARY)), *operands]
    if cohort != "steps":
        return tree(rng, LITERALS, True, 0, 2)
    if rng.random() < 0.5:
        return [rng.choice(list(NOUNS) + ["neg"]), literal]
    return [rng.choice(list(BINARY)), literal, {"constant": rng.choice(LITERALS)}]


def simple_rows(pool, rng, cohort, count, signatures, old_triples):
    output = []
    for family in ("unary", "binary", "constant"):
        found = []
        for batch in range(50):
            jobs = []
            for i in range(16):
                expr = simple_expression(family, cohort, rng)
                job = item(expr, f"ce:{cohort}:{family}:{batch:02}:{i:02}", family, rng, signatures, old_triples)
                if job is not None:
                    jobs.append(job)
            found.extend(row for row in pool.map(worker, jobs) if row is not None)
            if len(found) >= count:
                break
        if len(found) < count:
            raise RuntimeError((cohort, family, len(found), count))
        output.extend(found[:count])
    return output


def atom(expr):
    return expr if isinstance(expr, str) else expr["constant"]


def step_clauses(expr):
    op, left, *rest = expr
    if not rest:
        if isinstance(left, list):
            tail = "смени знак" if op == "neg" else f"найди {NOUNS[op]} полученного значения"
            return [*step_clauses(left), tail]
        if op == "neg":
            return [f"возьми {atom(left)} с противоположным знаком"]
        return [f"вычисли {NOUNS[op]} от {atom(left)}"]
    right = rest[0]
    if isinstance(left, list):
        return [*step_clauses(left), f"{FOLLOW[op]} {atom(right)}"]
    a, b = atom(left), atom(right)
    text = {"+": f"прибавь {b} к {a}", "-": f"из {a} вычти {b}", "*": f"умножь {a} на {b}",
            "/": f"раздели {a} на {b}", "pow": f"возведи {a} в степень {b}"}
    return [text[op]]


def step_question(spec, index):
    clauses = step_clauses(spec["X"])
    if len(clauses) > 1:
        clauses[0] = "сначала " + clauses[0]
        connector = (", затем ", ", потом ", ". После этого ")[index % 3]
        text = connector.join(clauses)
    else:
        text = clauses[0]
    text = text[0].upper() + text[1:]
    if spec["writes"]:
        text += ", и запиши результат в " + next(iter(spec["writes"]))
    elif index % 4 == 0:
        text += ". Результат оставь в X"
    return text + "."


def reword(goal, text, source):
    pool = pool_for(text)
    result = {**goal, "task": text, "pool": pool, "wording_source": source}
    for spec_key, body_key, packet_key in (("spec", "reference_body", "spec_body"), ("bad_spec", "bad_body", "bad_spec_body")):
        spec = goal[spec_key]
        result[body_key] = compile_spec(spec, pool)
        result[packet_key] = encode(spec, pool)
        if assemble(result[body_key], pool, "asm") != assemble(goal[body_key], goal["pool"], "asm"):
            raise ValueError("Rewording changed ROM bytes")
    return result


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    if (ROOT / "ast-frozen.json").exists():
        assert sha(ROOT / "closed-asts.jsonl") == read(ROOT / "ast-frozen.json")["sha256"]
        return
    build()
    signatures, old_triples, source_count = existing_goals()
    rng = random.Random(SEED)
    ops = sorted(set(NOUNS) | {"neg"})
    available = [t for t in product(ops, repeat=3) if len(set(t)) >= 2 and t not in old_triples]
    rng.shuffle(available)
    goals = []
    held = {}
    with ProcessPoolExecutor(max_workers=6) as pool:
        for cohort, (compositions, simple) in QUOTAS.items():
            rows_, held[cohort] = composition_rows(pool, rng, f"ce:{cohort}", compositions, available, signatures, old_triples)
            rows_ += simple_rows(pool, rng, cohort, simple, signatures, old_triples)
            for i, row in enumerate(rows_):
                row["wording_cohort"] = cohort
                if cohort == "steps":
                    row = reword(row, step_question(row["spec"], i), "authored_steps")
                if cohort == "structured":
                    text = question(row["spec"], ("bracket", "chain", "named")[i % 3], row["id"])
                    row = reword(row, text, "explicit_grammar")
                goals.append(row)
            print({"cohort": cohort, "tasks_ready": len(rows_), "total_ready": len(goals)}, flush=True)
    assert len(goals) == len({signature(g["spec"]) for g in goals}) == 256
    save_rows(ROOT / "closed-asts.jsonl", goals)
    write(ROOT / "ast-frozen.json", {"seed": SEED, "sha256": sha(ROOT / "closed-asts.jsonl"), "counts": dict(Counter(g["wording_cohort"] for g in goals)),
                                      "prior_goal_files_checked": source_count, "held_compositions": held, "new_literals": LITERALS})


if __name__ == "__main__":
    main()
