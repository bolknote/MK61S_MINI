"""Use the frozen Q4 harness for selection and independent paired testing."""

from pathlib import Path
from unittest.mock import patch

import ck_eval
import ce_eval
from ay_common import read, sha, write
from cl_data import PARENT, ROOT
from cl_train import check_frozen


PARENT_STEP = 12727  # Evaluation slot for the carried-over one-hour checkpoint.
FIRST_BASELINE = 0


def model_path(step):
    if step == FIRST_BASELINE:
        return ck_eval.CURRENT / "translator/model.mkqb"
    folder = PARENT if step == PARENT_STEP else ROOT / "checkpoints" / f"{step:06}"
    path = folder / "model.mkqb"
    assert sha(path) == read(folder / "manifest.json")["Q4_sha256"]
    return path


def adapter_reader(step):
    def read_file(path):
        if path == ROOT / "training.json" and not path.exists():
            model_path(step)
            return {"optimizer_updates": step}
        if path == ROOT / "training.json" and step == PARENT_STEP:
            return {"optimizer_updates": step}
        if path == ROOT / "preselected.json":
            decision = read(path)
            assert step in decision["closed_steps"]
            return {**decision, "candidate_step": step}
        return read(path)
    return read_file


def evaluate(split, step):
    if split == "closed":
        assert step in read(ROOT / "preselected.json")["closed_steps"]
    original_load = ce_eval.load

    def load_gpu(path, device):
        return original_load(path, "cuda:0")

    with patch.multiple(ck_eval, ROOT=ROOT, model_path=model_path, read=adapter_reader(step),
                        check_exam=lambda: check_frozen("exam")), patch.object(ce_eval, "load", load_gpu):
        ck_eval.evaluate(split, step, 2)


def evaluation_folder(split, step):
    return ROOT / "eval" / f"{split}-{step:06}"


def repair_ids(step):
    values = read(evaluation_folder("recovery", step) / "full.json")["records"]
    return {row["id"] for row in values if row["pass"] and not row["initially_correct"]}


def select():
    policy = read(ROOT / "policy.json")
    training = read(ROOT / "training.json")
    parent = read(evaluation_folder("development", PARENT_STEP) / "metrics.json")
    keep = repair_ids(PARENT_STEP)
    targets = set(policy["target_repairs"])
    choices = []
    for name in training["checkpoints"]:
        step = read(ROOT / name / "manifest.json")["step"]
        dev = read(evaluation_folder("development", step) / "metrics.json")
        ids = repair_ids(step)
        restored = len(ids & targets)
        protected = (restored == len(targets) and keep <= ids and dev["first"]["correct"] >= parent["first"]["correct"]
                     and dev["assisted"]["accepted_false_DONE"] <= parent["assisted"]["accepted_false_DONE"]
                     and dev["assisted"]["corruption"] <= parent["assisted"]["corruption"])
        key = [protected, restored, len(ids & keep), dev["first"]["correct"],
               dev["first"]["composition_correct"], dev["full_cycle"]["repairs"], -dev["clarifications"], -step]
        choices.append({"step": step, "key": key, "passed_all": protected, "restored_ids": sorted(ids & targets),
                        "lost_repairs_vs_parent": sorted(keep - ids), "dev_first": dev["first"]["correct"]})
    chosen = max(choices, key=lambda trial: trial["key"])
    endpoint = training["optimizer_updates"]
    result = {"candidate_step": chosen["step"], "endpoint_step": endpoint, "candidates": choices,
              "closed_steps": list(dict.fromkeys([FIRST_BASELINE, PARENT_STEP, chosen["step"], endpoint])),
              "selection_uses_closed_results": False, "parent_repairs_ids": sorted(keep),
              "parent_dev_first": parent["first"]["correct"], "targets": sorted(targets)}
    write(ROOT / "preselected.json", result)
    return result


def current_checkpoints():
    return [read(path)["step"] for path in sorted((ROOT / "checkpoints").glob("*/manifest.json"))]


if __name__ == "__main__":
    import argparse
    args = argparse.ArgumentParser()
    args.add_argument("split", choices=("development", "recovery", "closed", "select"))
    args.add_argument("step", nargs="?", type=int)
    options = args.parse_args()
    if options.split == "select":
        print(select(), flush=True)
    else:
        evaluate(options.split, options.step)
