"""Arithmetic and executor counterexamples for the twelve-hour Kon-Tiki run."""

from concurrent.futures import ProcessPoolExecutor
from collections import Counter
from decimal import Decimal
from itertools import islice, permutations
import json
import random

from ay_common import read, rows, save_rows, sha, write
from be_language import paths3, question
from bh_common import signature
from bs_data import worker
from ce_data import reword
from ce_wording import editorial_question
from cn_data import PREVIOUS, ROOT as PARENT
from co_data import OPS, RELATED, ROOT as LAST
from full_isa_protocol import REGISTERS
from ha_protocol import canonical


ROOT = LAST.with_name("kon-tiki-executor-twelve-hour-v1")
SEED = 2611141200
SIZES = {"power-train": 192, "composition-train": 288, "validation": 64, "closed": 128}


def key(expr):
    return json.dumps(expr, ensure_ascii=False, separators=(",", ":"))


def wording(goal, layout):
    spec = goal["spec"]
    expression = spec["X"]
    if goal["family"] != "power" or layout % 8 == 7:
        return (editorial_question(spec, layout) if layout % 2 or goal["family"] == "power"
                else question(spec, ("bracket", "chain", "named")[layout % 3], goal["id"]))
    left, right = ({"constant": "10"}, expression[1]) if expression[0] == "pow10" else expression[1:]
    base, power = (value if isinstance(value, str) else value["constant"] for value in (left, right))
    variants = (
        f"Вычисли степень с основанием {base} и показателем {power}.",
        f"Возведи {base} в степень {power}.",
        f"Показатель степени равен {power}, основание равно {base}. Вычисли степень.",
        f"Найди степень. Основание равно {base}, показатель равен {power}.",
        f"Что получится, если возвести {base} в степень {power}?",
        f"Основание степени — {base}, показатель — {power}. Какой получится результат?",
        f"Найди, чему равна степень с показателем {power} и основанием {base}.",
    )
    text = variants[layout % len(variants)]
    if spec["writes"]:
        text += f" Запиши ответ в {next(iter(spec['writes']))}."
    return text


def fixture(item):
    spec, ident, split, family, seed, style, held = item
    goal = worker((spec, ident, "train" if split.endswith("train") else "closed", family,
                   seed, "bracket", ("argument", "operation", "order")[style % 3], held))
    if goal is not None:
        try:
            return reword(goal, wording(goal, style), "cp_authored")
        except (ArithmeticError, ValueError):
            return None


def power_pairs(rng, split, count):
    start = {"power-train": 10000, "validation": 22000, "closed": 33000}[split]
    digits = rng.sample(range(start, start + 9400), count)
    for index, digit in enumerate(digits):
        base = Decimal("2") + Decimal(digit) / 100000
        other = Decimal("1") + Decimal(digit) / 100000
        left, right = {"constant": canonical(base)}, {"constant": "10" if index % 3 else canonical(other)}
        if index % 3 != 0:
            a, b = ["pow", left, right], ["pow10", left]
        else:
            a, b = ["pow", left, right], ["pow", right, left]
        store = rng.choice(REGISTERS) if index % 7 else None
        angle = rng.choice(("RAD", "DEG", "GRAD"))
        style = index % 8 if split == "power-train" else (index + 11) % 23
        yield (a, b), store, angle, style


def composition_jobs(rng, split, count, held_rules):
    start = {"composition-train": 59000, "validation": 73000, "closed": 90000}[split]
    permitted = [p for p in held_rules if p[1] not in ("reciprocal", "ln") and p[2] not in ("ln", "sqrt")]
    for index in range(count):
        leaf = rng.choice(REGISTERS)
        value = {"constant": canonical(Decimal("0.5") + Decimal(start + index) / 100000)}
        outer, middle, inner = rng.choice(permitted)
        if index % 4 == 0 and split == "composition-train":
            # Same families as the refusals, with different registers/literals.
            outer, middle, inner = rng.choice(RELATED[:2] + RELATED[3:])
        expr = [outer, [middle, [inner, leaf]]]
        if index % 3 == 0:
            expr = [rng.choice(("+", "-", "*")), expr, value]
        yield (expr,), (rng.choice(REGISTERS) if index % 5 else None), rng.choice(("RAD", "DEG", "GRAD")), index % 31


def generate():
    ROOT.mkdir(exist_ok=True)
    manifest = ROOT / "data-frozen.json"
    if manifest.exists():
        old = read(manifest)
        assert all(sha(ROOT / n) == h for n, h in old["files"].items())
        return
    rng = random.Random(SEED)
    source = [LAST / f"{split}.jsonl" for split in ("train", "validation", "closed")]
    source += [PARENT / "fresh.jsonl", *(PREVIOUS / f"{split}.jsonl" for split in ("recovery", "closed", "development"))]
    old = [g for path in source for g in rows(path)]
    reserved = {key(g["spec"]["X"]) for g in old}
    seen = {signature(g["spec"]) for g in old}
    # Reserve distinct primary operation triples. Broad review examples retain
    # the familiar failure families as well as these disjoint compositions.
    occupied = set().union(*(paths3(g["spec"]["X"]) for g in old))
    triples = [t for t in permutations(OPS, 3) if t not in occupied]
    rng.shuffle(triples)
    held = {"composition-train": triples[:42], "validation": triples[42:76], "closed": triples[76:126]}
    volume = {}
    with ProcessPoolExecutor(max_workers=6) as pool:
        for split, target in SIZES.items():
            power_count = target if split == "power-train" else 0 if split == "composition-train" else target // 2
            intents = list(power_pairs(rng, split, power_count // 2 * 3)) if power_count else []
            if target > power_count:
                intents += list(composition_jobs(rng, split, (target - power_count) * 5, held[split]))
            result = []
            finished = Counter()
            candidates = iter(enumerate(intents))
            blocked = [t for s, v in held.items() if s != split for t in v]
            for batch in iter(lambda: list(islice(candidates, 48)), []):
                tasks, identities = [], []
                for index, (expressions, store, angle, style) in batch:
                    family = "power" if len(expressions) == 2 else "composition"
                    needed = power_count if family == "power" else target - power_count
                    if finished[family] >= needed or any(key(expr) in reserved for expr in expressions):
                        continue
                    if any(paths3(expr).intersection(blocked) for expr in expressions):
                        continue
                    pair = []
                    for side, expr in enumerate(expressions):
                        spec = {"X": expr, "angle": angle, "writes": {store: expr} if store else {}}
                        if signature(spec) in seen:
                            break
                        ident = f"cp:{split}:{index:04}:{side}"
                        pair.append((spec, ident, split, family, rng.randrange(2**30), style, blocked))
                    if len(pair) == len(expressions):
                        tasks.extend(pair)
                        identities.append((len(pair), f"cp:{split}:{index:04}"))
                generated = iter(pool.map(fixture, tasks, chunksize=2))
                for n, identity in identities:
                    group = [next(generated) for _ in range(n)]
                    if None in group:
                        continue
                    family = group[0]["family"]
                    needed = power_count if family == "power" else target - power_count
                    keys = {key(row["spec"]["X"]) for row in group}
                    if keys & reserved or finished[family] >= needed:
                        continue
                    reserved.update(keys)
                    seen.update(signature(row["spec"]) for row in group)
                    if n == 2:
                        for row in group:
                            row["pair_id"] = identity
                    result.extend(group)
                    finished[family] += n
                if len(result) == target:
                    break
            assert len(result) == target, (split, target, finished)
            save_rows(ROOT / f"{split}.jsonl", result)
            volume[split] = finished
            print(split, finished, flush=True)
    files = {f"{split}.jsonl": sha(ROOT / f"{split}.jsonl") for split in SIZES}
    write(manifest, {"seed": SEED, "files": files, "counts": volume, "held_primary_triples": held})


if __name__ == "__main__":
    generate()
