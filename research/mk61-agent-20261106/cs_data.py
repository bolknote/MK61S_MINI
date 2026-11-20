"""Freeze novel arithmetic trees for the expanded grammar comparison."""

from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from decimal import Decimal
import random

from ay_common import read, rows, save_rows, sha, write
from be_language import paths3
from bh_common import signature
from cn_data import intent
from cq_data import composition_groups, fill, key, previous_tasks
from cr_data import PREVIOUS as INDEPENDENT, ROOT as PREVIOUS
from full_isa_protocol import REGISTERS
from ha_protocol import canonical


FIRST = PREVIOUS.with_name("kon-tiki-nested-direct-v1")
ROOT = PREVIOUS.with_name("kon-tiki-nested-direct-v2")
SEED = 261115953
POWER_PAIRS = 8
COMPOSITIONS = 48
PRODUCTS = 16


def powers(rng):
    for index in range(POWER_PAIRS * 5):
        a = {"constant": canonical(Decimal("3.45671") + Decimal(index) / 100000)}
        if index % 3 == 0:
            pair = (["pow", a, {"constant": "10"}], ["pow10", a])
        else:
            b = rng.choice(REGISTERS) if index % 3 == 1 else {"constant": canonical(
                Decimal("1.15742") + Decimal(index) / 100000)}
            pair = (["pow", a, b], ["pow", b, a])
        yield pair, "power", (index + 3) % 8


def compositions(rng, reserved):
    for index, ((expr,), family, layout) in enumerate(composition_groups(rng, reserved)):
        if index % 3 == 0 and len(expr) == 2:
            op = rng.choice(("+", "-", "*", "/"))
            right = [rng.choice(("square", "abs", "sin", "cos", "sqrt")), rng.choice(REGISTERS)]
            branched = [op, expr, right]
            if not paths3(branched) & reserved:
                expr = branched
        yield (expr,), family, layout


def products(rng, reserved):
    for index, ((left,), family, _) in enumerate(composition_groups(rng, reserved)):
        if index % 2:
            right = [rng.choice(("square", "abs", "sin", "cos")), rng.choice(REGISTERS)]
        else:
            right = {"constant": canonical(Decimal("1.91259") + Decimal(index) / 100000)}
        expr = ["*", left, right]
        if not paths3(expr) & reserved:
            # Editorial layout 3 uses the explicit «надо умножить на» construction.
            yield (expr,), family, 3


def prepare():
    ROOT.mkdir(exist_ok=True)
    closed = ROOT / "closed.jsonl"
    seal = ROOT / "data-frozen.json"
    if seal.exists():
        assert sha(closed) == read(seal)["sha256"]
        return
    older_paths = [folder / "closed.jsonl" for folder in (INDEPENDENT, PREVIOUS, FIRST)]
    assert all(sha(path) == read(path.with_name("data-frozen.json"))["sha256"] for path in older_paths)
    old = [*previous_tasks(), *(g for path in older_paths for g in rows(path))]
    reserved = set().union(*(paths3(g["spec"]["X"]) for g in old))
    seen = {signature(g["spec"]) for g in old}
    expressions = {key(g["spec"]["X"]) for g in old}
    wording = {intent(g) for g in old}
    rng = random.Random(SEED)
    with ProcessPoolExecutor(max_workers=5) as pool:
        power = fill(pool, powers(rng), POWER_PAIRS * 2, rng, seen, expressions, wording)
        print("Verified", len(power), "power tasks", flush=True)
        mult = fill(pool, products(rng, reserved), PRODUCTS, rng, seen, expressions, wording)
        reserved.update(t for g in mult for t in paths3(g["spec"]["X"]))
        comp = fill(pool, compositions(rng, reserved), COMPOSITIONS - PRODUCTS, rng, seen, expressions, wording)
    goals = [*power, *comp, *mult]
    for index, goal in enumerate(goals):
        goal["id"] = f"cs2:closed:{goal['family']}:{index:04}"
        goal["multiplication_wording"] = index >= len(power) + len(comp)
        if "pair_id" in goal:
            goal["pair_id"] = goal["pair_id"].replace("cq:", "cs2:", 1)
    save_rows(closed, goals)
    write(seal, {"sha256": sha(closed), "seed": SEED, "tasks": len(goals), "power_pairs": POWER_PAIRS,
                 "families": Counter(g["family"] for g in goals), "multiplication_wording": PRODUCTS,
                 "prior_tasks_checked": len(old)})
    print("Frozen", len(goals), "tasks", flush=True)


if __name__ == "__main__":
    prepare()
