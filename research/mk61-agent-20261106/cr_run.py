"""Run the frozen bounded-repair comparison in the existing B200 setup."""

import argparse
from pathlib import Path
import tarfile
from unittest.mock import patch

import cn_run
import cq_run
from ay_common import read, sha, write
from ce_eval import PROFILES
from ck_train import REPO
from cl_eval import model_path
from cm_eval import STEP
from cq_eval import load_actor
from cr_data import PREVIOUS, ROOT
from cr_eval import MODES, evaluate


def prepare():
    here = Path(__file__).resolve().parent
    data = ROOT / "closed.jsonl"
    assert sha(data) == read(ROOT / "data-frozen.json")["sha256"]
    sources = [*sorted(here.glob("cr_*.py")), data, ROOT / "data-frozen.json"]
    previous = PREVIOUS / "eval/closed"
    inputs = [*sources, PREVIOUS / "closed.jsonl", previous / "complete.json",
              load_actor(False), model_path(STEP), PROFILES / "working/model.mkqb"]
    inputs += [here / name for name in ("cq_eval.py", "cq_runtime.py", "cq_language.py",
                                        "bj_eval.py", "bj_runtime.py", "cn_eval.py", "cn_review_check.py",
                                        "cn_runtime.py", "co_eval.py", "bt_decode.py", "ay_codec.py")]
    seal = ROOT / "inputs-frozen.json"
    write(seal, {"files": {str(p.relative_to(REPO)): sha(p) for p in inputs},
                 "modes": MODES, "optimizer_updates": 0, "context": 1024})
    with tarfile.open(ROOT / "deploy.tar.gz", "w:gz") as archive:
        for path in [*sources, seal]:
            archive.add(path, str(path.relative_to(REPO)), recursive=False)


def check_inputs():
    seal = ROOT / "inputs-frozen.json"
    for path, digest in read(seal)["files"].items():
        assert sha(REPO / path) == digest, path
    return sha(seal)


def pipeline(device):
    try:
        seal = check_inputs()
        previous = read(PREVIOUS / "eval/closed/checked-compact/metrics.json")
        for split in ("diagnostic", "closed"):
            write(ROOT / "status.json", {"phase": split})
            evaluate(split, device)
            if split == "diagnostic":
                actual = read(ROOT / "eval/diagnostic/current/metrics.json")
                for key in ("repairs", "completed", "accepted_false_DONE", "corruption", "unsure",
                            "false_DONE_claims", "first_correct"):
                    assert actual[key] == previous[key], (key, actual[key], previous[key])
                for mode in MODES[1:]:
                    metrics = read(ROOT / "eval/diagnostic" / mode / "metrics.json")
                    assert not metrics["done"].get("repeated_counterexample"), mode
        assert check_inputs() == seal
        write(ROOT / "complete.json", {"complete": True, "inputs_sha256": seal,
                                      "eval": {split: sha(ROOT / "eval" / split / "complete.json")
                                               for split in ("diagnostic", "closed")}})
        write(ROOT / "status.json", {"phase": "complete"})
    except (Exception, KeyboardInterrupt) as error:
        write(ROOT / "status.json", {"phase": "failed", "error": f"{type(error).__name__}: {error}"})
        raise


def launch():
    remote = cn_run.remote
    with patch.object(cn_run, "remote", lambda src: remote(src.replace("/cn_run.py pipeline", "/cr_run.py pipeline"))):
        cn_run.launch()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("prepare", "deploy", "launch", "status", "pipeline", "fetch"))
    parser.add_argument("--device", default="cuda:0")
    args = parser.parse_args()
    with (patch.multiple(cn_run, ROOT=ROOT, RUN_NAME=ROOT.name, prepare=prepare),
          patch.multiple(cq_run, ROOT=ROOT, check_inputs=check_inputs)):
        actions = {"prepare": prepare, "deploy": cn_run.deploy, "launch": launch,
                   "status": cn_run.status, "pipeline": lambda: pipeline(args.device), "fetch": cq_run.fetch}
        actions[args.stage]()
