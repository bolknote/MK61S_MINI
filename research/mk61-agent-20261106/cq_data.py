"""Freeze new paired power tasks and unseen compositions for the harness comparison."""

from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from decimal import Decimal
from itertools import islice, permutations
import random

from ay_common import read, rows, save_rows, sha, write
from be_language import paths3
from bh_common import signature
from cn_data import intent, training_goals
from co_data import OPS, ROOT as EXECUTOR_REFUSALS
from cp_data import PARENT, PREVIOUS, ROOT as LONG_RUN, fixture, key
from full_isa_protocol import REGISTERS
from ha_protocol import canonical


ROOT = LONG_RUN.with_name("kon-tiki-independent-spec-v1")
SEED = 261115093
POWER_PAIRS = 32
COMPOSITIONS = 64


def previous_tasks():
    roots = ((LONG_RUN, ("power-train", "composition-train", "validation", "closed")),
             (EXECUTOR_REFUSALS, ("train", "validation", "closed")),
             (PARENT, ("fresh",)),
             (PREVIOUS, ("development", "closed", "recovery")))
    return [*training_goals(), *(g for folder, splits in roots for split in splits
                                  for g in rows(folder / f"{split}.jsonl"))]


def power_groups(rng):
    for i in range(POWER_PAIRS * 4):
        literal = Decimal("2.85219") + Decimal(i) / 10007
        a = {"constant": canonical(str(literal.quantize(Decimal(".00001"))))}
        b = {"constant": "10"}
        if i % 3 == 1:
            b = {"constant": canonical(str(Decimal("-1.61321") - Decimal(i) / 100000))}
            # Both directions in this pair need a valid base.
            exprs = (["pow", a, b], ["pow10", b])
        elif i % 3 == 2:
            b = rng.choice(REGISTERS)
            exprs = (["pow", b, a], ["pow", a, b])
        else:
            exprs = (["pow", a, b], ["pow10", a])
        yield exprs, "power", i % 8


def composition_groups(rng, reserved):
    ops = [op for op in OPS if op not in ("int", "frac")]
    triples = [t for t in permutations(ops, 3) if t not in reserved]
    rng.shuffle(triples)
    for i, (outer, middle, inner) in enumerate(triples):
        expr = [outer, [middle, [inner, rng.choice(REGISTERS)]]]
        if i % 3 == 0:
            expr = [rng.choice(("+", "-", "*")), expr,
                    {"constant": canonical(str(Decimal("1.73871") + Decimal(i) / 100000))}]
        if not paths3(expr) & reserved:
            yield (expr,), "composition", i % 31


def fill(pool, groups, count, rng, seen, expressions, used_text):
    result = []
    stream = iter(enumerate(groups))
    for batch in iter(lambda: list(islice(stream, 32)), []):
        jobs = []
        lengths = []
        for index, (group, family, style) in batch:
            if any(key(expr) in expressions for expr in group):
                continue
            destination = rng.choice(REGISTERS) if index % 5 else None
            mode = rng.choice(("RAD", "DEG", "GRAD"))
            group_id = f"cq:closed:{family}:{index:04}"
            jobs_for_group = []
            for side, expr in enumerate(group):
                spec = {"X": expr, "angle": mode, "writes": {destination: expr} if destination else {}}
                if signature(spec) in seen:
                    break
                jobs_for_group.append((spec, f"{group_id}:{side}", "closed", family,
                                       rng.randrange(2**30), style, []))
            if len(jobs_for_group) == len(group):
                jobs.extend(jobs_for_group)
                lengths.append(len(group))
        candidates = iter(pool.map(fixture, jobs, chunksize=2))
        for size in lengths:
            group = [next(candidates) for _ in range(size)]
            if any(g is None for g in group):
                continue
            texts = {intent(g) for g in group}
            keys = {key(g["spec"]["X"]) for g in group}
            if len(texts) != size or used_text & texts or expressions & keys:
                continue
            if size == 2:
                for goal in group:
                    goal["pair_id"] = goal["id"].rsplit(":", 1)[0]
            result.extend(group)
            used_text.update(texts)
            expressions.update(keys)
            seen.update(signature(g["spec"]) for g in group)
            if len(result) == count:
                return result
    raise RuntimeError(f"Only {len(result)} of {count} verified tasks were generated")


def prepare():
    ROOT.mkdir(exist_ok=True)
    manifest = ROOT / "data-frozen.json"
    path = ROOT / "closed.jsonl"
    if manifest.is_file():
        assert sha(path) == read(manifest)["sha256"]
        return
    known = previous_tasks()
    old_paths = set().union(*(paths3(g["spec"]["X"]) for g in known))
    seen = {signature(g["spec"]) for g in known}
    expressions = {key(g["spec"]["X"]) for g in known}
    used_text = {intent(g) for g in known}
    rng = random.Random(SEED)
    with ProcessPoolExecutor(max_workers=5) as pool:
        power = fill(pool, power_groups(rng), POWER_PAIRS * 2, rng, seen, expressions, used_text)
        print("Verified", len(power), "power tasks", flush=True)
        composition = fill(pool, composition_groups(rng, old_paths), COMPOSITIONS, rng, seen, expressions, used_text)
    result = [*power, *composition]
    save_rows(path, result)
    write(manifest, {"sha256": sha(path), "seed": SEED, "tasks": len(result),
                     "families": Counter(g["family"] for g in result), "power_pairs": POWER_PAIRS,
                     "prior_tasks_checked": len(known)})
    print("Frozen", len(result), "tasks", flush=True)


if __name__ == "__main__":
    prepare()
