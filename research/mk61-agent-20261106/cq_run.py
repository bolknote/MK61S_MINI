"""Run the frozen three-way harness comparison on the B200."""

import argparse
from pathlib import Path
import shlex
import subprocess
import tarfile
from unittest.mock import patch

import cn_run
from ay_common import read, sha, write
from ce_eval import PROFILES
from ck_train import REPO
from cl_eval import model_path
from cm_eval import STEP
from cp_data import ROOT as LONG_RUN
from cq_data import ROOT
from cq_eval import DIAGNOSTIC_STEP, MODES, evaluate, load_actor


def prepare():
    here = Path(__file__).resolve().parent
    data = ROOT / "closed.jsonl"
    assert sha(data) == read(ROOT / "data-frozen.json")["sha256"]
    sources = [*sorted(here.glob("cq_*.py")), data, ROOT / "data-frozen.json"]
    previous = LONG_RUN / "eval" / f"closed-{DIAGNOSTIC_STEP:04}"
    inputs = [*sources, LONG_RUN / "closed.jsonl", previous / "complete.json",
              load_actor(True), load_actor(False), model_path(STEP), PROFILES / "working/model.mkqb"]
    inputs += [here / name for name in ("bj_eval.py", "bj_runtime.py", "co_eval.py",
                                        "cn_eval.py", "cn_review_check.py", "cn_runtime.py",
                                        "bt_decode.py", "cf_language.py", "cg_language.py")]
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
        previous = LONG_RUN / "eval" / f"closed-{DIAGNOSTIC_STEP:04}"
        for split in ("diagnostic", "closed"):
            write(ROOT / "status.json", {"phase": split})
            evaluate(split, device)
            if split == "diagnostic":
                expected = read(previous / "metrics.json")
                actual = read(ROOT / "eval/diagnostic/current/metrics.json")
                for key in ("repairs", "completed", "accepted_false_DONE", "corruption", "refusals", "first_correct"):
                    assert actual[key] == expected[key], (key, actual[key], expected[key])
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
    with patch.object(cn_run, "remote", lambda src: remote(src.replace("/cn_run.py pipeline", "/cq_run.py pipeline"))):
        cn_run.launch()


def fetch():
    source = cn_run.prefix() + '''
import sys,tarfile
assert json.loads((folder/'complete.json').read_text())['complete']
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as archive:
    paths=[folder/n for n in ('complete.json','status.json','pipeline.log')]
    paths+=sorted((folder/'eval').rglob('*.json'))
    for p in paths:
        assert not p.is_symlink()
        archive.add(p,arcname=str(p.relative_to(folder)),recursive=False)
'''
    with subprocess.Popen([*cn_run.SSH, "python3 -c " + shlex.quote(source)], stdout=subprocess.PIPE) as child:
        with tarfile.open(fileobj=child.stdout, mode="r|gz") as archive:
            archive.extractall(ROOT, filter="data")
        if child.wait(timeout=45):
            raise RuntimeError("Could not fetch the audit")
    complete = read(ROOT / "complete.json")
    assert complete["complete"] and check_inputs() == complete["inputs_sha256"]
    for split, digest in complete["eval"].items():
        folder = ROOT / "eval" / split
        manifest = folder / "complete.json"
        assert sha(manifest) == digest
        for name, expected in read(manifest)["files"].items():
            assert sha(folder / name) == expected, name
    print(complete, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("prepare", "deploy", "launch", "status", "pipeline", "fetch"))
    parser.add_argument("--device", default="cuda:0")
    args = parser.parse_args()
    with patch.multiple(cn_run, ROOT=ROOT, RUN_NAME=ROOT.name, prepare=prepare):
        actions = {"prepare": prepare, "deploy": cn_run.deploy, "launch": launch,
                   "status": cn_run.status, "pipeline": lambda: pipeline(args.device), "fetch": fetch}
        actions[args.stage]()
