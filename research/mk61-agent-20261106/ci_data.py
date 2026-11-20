"""Prepare a new paired test with a power-notation control group."""

import argparse
from unittest.mock import patch

import ce_data
import cg_data
from ar_spec import verify
from ay_codec import compile_spec
from bl_spec import install
from bl_vm import CachedVM


ROOT = cg_data.ROOT.parent / "spec-formula-clarification-v1"
LITERALS = ["0.31947", "1.81947", "4.31947", "43.81947", "-0.31947"]
SEED = 261114971
QUOTAS = {"steps": (20, 4), "structured": (20, 4), "freeform": (100, 20)}


def power_controls(pool, rng, signatures, old_triples):
    install()
    vm = CachedVM()
    accepted = []
    for batch in range(30):
        jobs = []
        for index in range(16):
            exponent = {"constant": rng.choice(LITERALS)} if index % 2 == 0 else f"R{rng.randrange(15):X}"
            expr = ["pow10", exponent]
            if index % 3 == 0:
                expr = [rng.choice(["sign", "ln", "sqrt", "atan"]), expr]
            elif index % 3 == 1:
                expr = ["+", expr, {"constant": rng.choice(LITERALS)}]
            job = ce_data.item(expr, f"ci:pow10:{batch:02}:{index:02}", "power", rng, signatures, old_triples)
            if job is not None:
                jobs.append(job)
        for goal in pool.map(ce_data.worker, jobs):
            if goal is None:
                continue
            goal["wording_cohort"] = "pow10"
            expr = goal["spec"]["X"]
            power = expr if expr[0] == "pow10" else expr[1]
            exponent = ce_data.atom(power[1])
            lead = f"Возведи 10 в степень {exponent}"
            out = ["pow", {"constant": "10"}, power[1]]
            if expr[0] != "pow10":
                suffix = (f"прибавь {ce_data.atom(expr[2])}" if expr[0] == "+"
                          else f"вычисли {ce_data.NOUNS[expr[0]]} полученного результата")
                lead = f"Сначала {lead[0].lower() + lead[1:]}, затем {suffix}"
                out = [expr[0], out, *expr[2:]]
            if goal["spec"]["writes"]:
                lead += " и запиши ответ в " + next(iter(goal["spec"]["writes"]))
            goal = ce_data.reword(goal, lead + ".", "authored_power_alias")
            angle = goal["spec"]["angle"]
            alias = {"X": out, "writes": {reg: out for reg in goal["spec"]["writes"]}, "angle": angle}
            bank = goal["public_inputs"] + goal["checker_inputs"] + goal["audit_inputs"]
            alias_program = compile_spec(alias, goal["pool"])
            if verify(vm, alias_program, goal["pool"], goal["spec"], bank)["status"] != "TESTED":
                continue
            accepted.append(goal)
            if len(accepted) == 32:
                print({"cohort": "pow10", "tasks_ready": 32}, flush=True)
                return accepted
    raise RuntimeError("Could not construct 32 checked power transcription controls")


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("stage", choices=("asts", "wording"))
    stage = cli.parse_args().stage
    with patch.multiple(cg_data, ROOT=ROOT, LITERALS=LITERALS, SEED=SEED, QUOTAS=QUOTAS, targeted_rows=power_controls):
        if stage == "asts":
            cg_data.build_asts()
        else:
            cg_data.build_wordings()
