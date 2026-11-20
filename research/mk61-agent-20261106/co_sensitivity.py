"""Evaluate the most responsive validation snapshot as a separate Q4 comparison."""

import argparse
from unittest.mock import patch

from ay_common import read, sha, write
import co_eval
from co_data import ROOT
from co_train import check_inputs


FOLDER = ROOT / "sensitivity"


def seal():
    check_inputs()
    selection = read(ROOT / "preselected.json")
    step = min(selection["validation"], key=lambda r: (r["avoidable_refusals"], r["repair_losses"], r["step"]))["step"]
    value = {"audit_step": step, "criterion": "fewest avoidable refusals on validation and recovery",
             "validation_selection_sha256": sha(ROOT / "preselected.json"), "policy_source_sha256": sha(__file__),
             "closed_used_for_selection": False}
    output = FOLDER / "preselected.json"
    if output.is_file():
        assert read(output) == value
    else:
        write(output, value)
    print(value, flush=True)


def evaluate():
    check_inputs()
    policy = read(FOLDER / "preselected.json")
    assert sha(__file__) == policy["policy_source_sha256"]
    step = policy["audit_step"]
    baseline = ROOT / "eval/closed-0000"
    assert sha(baseline / "full.json") == read(baseline / "complete.json")["full_sha256"]
    target = FOLDER / "eval/closed-0000"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.is_symlink():
        target.symlink_to(baseline, target_is_directory=True)
    assert target.resolve() == baseline
    checkpoint = co_eval.actor_file(step)
    with patch.multiple(co_eval, ROOT=FOLDER, path_for=lambda _: ROOT / "closed.jsonl",
                        actor_file=lambda _: checkpoint):
        co_eval.evaluate("closed", step)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("seal", "evaluate"))
    {"seal": seal, "evaluate": evaluate}[parser.parse_args().stage]()
