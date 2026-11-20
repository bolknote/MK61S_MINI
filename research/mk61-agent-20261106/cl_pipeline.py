"""Run training, frozen Q4 selection, and the closed comparison in one container."""

import time
import traceback

from ay_common import read, sha, write
from cl_data import ROOT
from cl_eval import PARENT_STEP, current_checkpoints, evaluate, select
from cl_report import make_report
from cl_train import run


def status(phase, **data):
    event = {"phase": phase, "unix": time.time(), **data}
    write(ROOT / "pipeline-status.json", event)
    print(event, flush=True)


def main():
    if not (ROOT / "training.json").exists():
        status("training")
        run()
    status("validation")
    for step in [PARENT_STEP, *current_checkpoints()]:
        for split in ("development", "recovery"):
            status("validation", split=split, step=step)
            evaluate(split, step)
    evaluate("recovery", 0)
    if (ROOT / "preselected.json").exists():
        decision = read(ROOT / "preselected.json")
    else:
        assert not list((ROOT / "eval").glob("closed-*"))
        decision = select()
    for step in decision["closed_steps"]:
        status("closed_Q4", step=step)
        evaluate("closed", step)
    comparison = make_report()
    write(ROOT / "complete.json", {"complete": True, "comparison_sha256": sha(ROOT / "comparison.json"),
                                  "report_sha256": comparison["report_sha256"],
                                  "updates": comparison["training"]["optimizer_updates"]})
    status("complete", report=comparison["report"])


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        status("failed", error=f"{type(error).__name__}: {error}")
        write(ROOT / "pipeline-failure.json", {"error": str(error), "traceback": traceback.format_exc()})
        raise
