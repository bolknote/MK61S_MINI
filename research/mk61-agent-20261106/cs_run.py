"""Run the frozen nested-grammar comparison in the existing B200 setup."""

import argparse
from pathlib import Path
import tarfile
from unittest.mock import patch

import cn_run
import cq_run
import cr_run
from ay_common import read, sha, write
from ce_eval import PROFILES
from ck_train import REPO
from cl_eval import model_path
from cm_eval import STEP
from cq_eval import load_actor
from cs_data import FIRST, PREVIOUS, ROOT
from cs_eval import MODES, evaluate


def prepare():
    here = Path(__file__).resolve().parent
    data = ROOT / "closed.jsonl"
    assert sha(data) == read(ROOT / "data-frozen.json")["sha256"]
    sources = [*sorted(here.glob("cs_*.py")), data, ROOT / "data-frozen.json"]
    inputs = [*sources, FIRST / "data-frozen.json", FIRST / "closed.jsonl",
              PREVIOUS / "closed.jsonl", PREVIOUS / "eval/closed/complete.json",
              load_actor(False), model_path(STEP), PROFILES / "working/model.mkqb"]
    inputs += [here / name for name in ("cq_eval.py", "cq_runtime.py", "cq_language.py", "cr_eval.py", "cr_runtime.py",
                                        "cf_language.py", "cg_language.py", "bj_eval.py", "bj_runtime.py", "cn_eval.py",
                                        "cn_review_check.py", "cn_runtime.py", "co_eval.py", "bl_prompt.py",
                                        "bt_decode.py", "ay_codec.py", "ar_spec.py")]
    seal = ROOT / "inputs-frozen.json"
    write(seal, {"files": {str(path.relative_to(REPO)): sha(path) for path in inputs},
                 "modes": MODES, "optimizer_updates": 0, "context": 1024})
    with tarfile.open(ROOT / "deploy.tar.gz", "w:gz") as archive:
        for path in [*sources, seal]:
            archive.add(path, str(path.relative_to(REPO)), recursive=False)


def pipeline(device):
    try:
        seal = cr_run.check_inputs()
        for split in ("diagnostic", "closed"):
            write(ROOT / "status.json", {"phase": split})
            evaluate(split, device)
            if split == "diagnostic":
                previous = read(PREVIOUS / "eval/closed/bounded-compiler/metrics.json")
                replay = read(ROOT / "eval/diagnostic/baseline/metrics.json")
                for key in ("first_correct", "repairs", "completed", "accepted_false_DONE", "corruption", "done",
                            "clarifications", "neural_calls", "repair_source"):
                    assert replay[key] == previous[key], (key, replay[key], previous[key])
        assert cr_run.check_inputs() == seal
        write(ROOT / "complete.json", {"complete": True, "inputs_sha256": seal,
                                      "eval": {split: sha(ROOT / "eval" / split / "complete.json")
                                               for split in ("diagnostic", "closed")}})
        write(ROOT / "status.json", {"phase": "complete"})
    except (Exception, KeyboardInterrupt) as error:
        write(ROOT / "status.json", {"phase": "failed", "error": f"{type(error).__name__}: {error}"})
        raise


def launch():
    remote = cn_run.remote
    with patch.object(cn_run, "remote", lambda source: remote(source.replace("/cn_run.py pipeline", "/cs_run.py pipeline"))):
        cn_run.launch()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("prepare", "deploy", "launch", "status", "pipeline", "fetch"))
    parser.add_argument("--device", default="cuda:0")
    args = parser.parse_args()
    with (patch.multiple(cn_run, ROOT=ROOT, RUN_NAME=ROOT.name, prepare=prepare), patch.object(cr_run, "ROOT", ROOT),
          patch.multiple(cq_run, ROOT=ROOT, check_inputs=cr_run.check_inputs)):
        actions = {"prepare": prepare, "deploy": cn_run.deploy, "launch": launch,
                   "status": cn_run.status, "pipeline": lambda: pipeline(args.device), "fetch": cq_run.fetch}
        actions[args.stage]()
