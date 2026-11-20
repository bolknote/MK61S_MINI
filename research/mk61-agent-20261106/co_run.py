"""Run the refusal correction course and its frozen paired Q4 evaluation."""

import argparse
from pathlib import Path
import subprocess
import sys
import tarfile
from unittest.mock import patch

from ay_common import read, sha, write
from ck_train import CURRENT, REPO
from cl_eval import model_path
from cm_eval import STEP
import cn_run
from co_data import PARENT, PREVIOUS, ROOT
from co_train import STEPS, check_inputs, parent_dir


def prepare():
    labels = read(ROOT / "teacher-frozen.json")
    data = read(ROOT / "data-frozen.json")
    for manifest in (labels, data):
        assert all(sha(ROOT / name) == digest for name, digest in manifest["files"].items())
    code = sorted(Path(__file__).resolve().parent.glob("co_*.py"))
    local = [*code, *(ROOT / name for name in (*labels["files"], *data["files"], "data-frozen.json",
                                                "teacher-frozen.json", "refusal-audit.jsonl"))]
    dependencies = [CURRENT / "working/model.mkqb", model_path(STEP), *parent_dir().glob("*"),
                    PARENT / "replay-lessons.jsonl", PARENT / "inputs-frozen.json",
                    PREVIOUS / "recovery.jsonl", PARENT / "fresh.jsonl",
                    PREVIOUS / "development.jsonl", PREVIOUS / "preselected.json"]
    dependencies += [Path(__file__).resolve().with_name(name) for name in (
        "bj_eval.py", "cn_data.py", "cn_eval.py", "cn_review_check.py", "cn_runtime.py", "cn_train.py")]
    manifest = ROOT / "inputs-frozen.json"
    write(manifest, {"files": {str(p.relative_to(REPO)): sha(p) for p in [*local, *dependencies]},
                     "checkpoints": list(STEPS), "context": 1024,
                     "teacher_queries_to_closed": 0, "closed_used_for_selection": False})
    with tarfile.open(ROOT / "deploy.tar.gz", mode="w:gz") as archive:
        for path in [*local, manifest]:
            archive.add(path, arcname=str(path.relative_to(REPO)), recursive=False)


def pipeline():
    def run(script, *args):
        write(ROOT / "status.json", {"phase": " ".join((script, *args))})
        subprocess.run([sys.executable, "-u", f"{cn_run.SCRIPT}/{script}", *args], cwd=REPO, check=True)

    try:
        manifest = check_inputs()
        if not (ROOT / "training.json").exists():
            run("co_train.py")
        for split in ("recovery", "validation"):
            for step in (0, *STEPS):
                run("co_eval.py", split, "--step", str(step))
        run("co_eval.py", "select")
        chosen = read(ROOT / "preselected.json")["audit_step"]
        for split in ("closed", "retired"):
            for step in (0, chosen):
                run("co_eval.py", split, "--step", str(step))
        assert check_inputs() == manifest
    except subprocess.CalledProcessError as error:
        write(ROOT / "status.json", {"phase": "failed", "command": error.cmd, "code": error.returncode})
        raise
    write(ROOT / "complete.json", {"complete": True, "step": chosen,
                                    "training_sha256": sha(ROOT / "training.json"),
                                    "selection_sha256": sha(ROOT / "preselected.json"),
                                    "eval": {p.parent.name: sha(p) for p in sorted((ROOT / "eval").glob("*/complete.json"))}})
    write(ROOT / "status.json", {"phase": "complete"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("deploy", "launch", "pipeline", "status", "fetch"))
    stage = parser.parse_args().stage
    if stage == "pipeline":
        pipeline()
    else:
        with patch.multiple(cn_run, ROOT=ROOT, RUN_NAME=ROOT.name, prepare=prepare):
            if stage == "launch":
                # Reuse the container configuration and point its entry at this course.
                remote = cn_run.remote
                with patch.object(cn_run, "remote", lambda source: remote(source.replace("/cn_run.py pipeline", "/co_run.py pipeline"))):
                    cn_run.launch()
            else:
                getattr(cn_run, stage)()
