"""Freeze an independent test for the bounded repair loop."""

from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from decimal import Decimal
import random

from ay_common import read, rows, save_rows, sha, write
from be_language import paths3
from bh_common import signature
from cn_data import intent
from cq_data import (ROOT as PREVIOUS, COMPOSITIONS, POWER_PAIRS, composition_groups, fill, key,
                     previous_tasks)
from full_isa_protocol import REGISTERS
from ha_protocol import canonical


ROOT = PREVIOUS.with_name("kon-tiki-bounded-repair-v1")
SEED = 261115211


def power_groups(rng):
    for index in range(POWER_PAIRS * 4):
        value = (Decimal("2.61379") + Decimal(index) / 9931).quantize(Decimal(".00001"))
        a = {"constant": canonical(str(value))}
        if index % 3 == 0:
            values = (["pow", a, {"constant": "10"}], ["pow10", a])
        else:
            exponent = (Decimal("1.28143") + Decimal(index) / 100000).quantize(Decimal(".00001"))
            b = rng.choice(REGISTERS) if index % 3 == 1 else {"constant": canonical(str(exponent))}
            values = (["pow", a, b], ["pow", b, a])
        yield values, "power", (index + 5) % 8


def prepare():
    ROOT.mkdir(exist_ok=True)
    data = ROOT / "closed.jsonl"
    seal = ROOT / "data-frozen.json"
    if seal.is_file():
        assert sha(data) == read(seal)["sha256"]
        return
    old_path = PREVIOUS / "closed.jsonl"
    assert sha(old_path) == read(PREVIOUS / "data-frozen.json")["sha256"]
    old = [*previous_tasks(), *rows(old_path)]
    triples = set().union(*(paths3(g["spec"]["X"]) for g in old))
    seen = {signature(g["spec"]) for g in old}
    expressions = {key(g["spec"]["X"]) for g in old}
    wording = {intent(g) for g in old}
    rng = random.Random(SEED)
    with ProcessPoolExecutor(max_workers=5) as pool:
        power = fill(pool, power_groups(rng), POWER_PAIRS * 2, rng, seen, expressions, wording)
        print("Verified", len(power), "power tasks", flush=True)
        comp = fill(pool, composition_groups(rng, triples), COMPOSITIONS, rng, seen, expressions, wording)
    goals = [{**g, "id": g["id"].replace("cq:", "cr:", 1)} for g in [*power, *comp]]
    for g in goals:
        if "pair_id" in g:
            g["pair_id"] = g["pair_id"].replace("cq:", "cr:", 1)
    save_rows(data, goals)
    write(seal, {"sha256": sha(data), "seed": SEED, "tasks": len(goals),
                 "families": Counter(g["family"] for g in goals), "power_pairs": POWER_PAIRS,
                 "prior_tasks_checked": len(old)})
    print("Frozen", len(goals), "tasks", flush=True)


if __name__ == "__main__":
    prepare()
