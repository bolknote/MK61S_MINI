"""Stage, launch, and audit the unattended twelve-hour executor session."""

import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import time
from unittest.mock import patch

from ay_common import read, sha, write
from ck_train import CURRENT, REPO
from cl_eval import model_path
from cm_eval import STEP
import cn_run
from co_train import parent_dir
from cp_data import LAST, PARENT, PREVIOUS, ROOT, SIZES
from cp_train import DURATION, MILESTONES, check_inputs, make_lessons, train


def prepare():
    data = read(ROOT / "data-frozen.json")
    assert all(sha(ROOT / name) == digest for name, digest in data["files"].items())
    if not (ROOT / "lessons.jsonl").exists():
        make_lessons()
    code = sorted(Path(__file__).resolve().parent.glob("cp_*.py"))
    local = [*code, *(ROOT / f"{split}.jsonl" for split in SIZES), ROOT / "lessons.jsonl",
             ROOT / "data-frozen.json"]
    parents = [CURRENT / "working/model.mkqb", model_path(STEP), *parent_dir().glob("*"),
               PARENT / "replay-lessons.jsonl", *(LAST / f"{name}.jsonl" for name in
                                                 ("matched-lessons", "teacher-lessons", "retired-refusals")),
               PREVIOUS / "preselected.json", PREVIOUS / "recovery.jsonl"]
    folders = [CURRENT / role / "hf" for role in ("working", "translator")]
    parents.extend(item for path in folders for item in path.iterdir() if item.is_file())
    parents.extend(Path(__file__).resolve().with_name(name) for name in (
        "co_eval.py", "co_train.py", "co_data.py", "cn_runtime.py", "cn_eval.py",
        "cn_review_check.py", "cn_train.py", "cn_data.py", "bj_runtime.py", "bj_eval.py",
        "bt_decode.py", "ay_codec.py", "af_model.py"))
    manifest = ROOT / "inputs-frozen.json"
    write(manifest, {"files": {str(p.relative_to(REPO)): sha(p) for p in [*local, *parents]},
                     "duration_seconds": DURATION, "milestones_hours": list(MILESTONES), "context": 1024,
                     "teacher": read(LAST / "teacher-frozen.json")["model"], "new_teacher_queries": 0,
                     "closed_used_for_selection": False})
    with tarfile.open(ROOT / "deploy.tar.gz", mode="w:gz") as archive:
        for path in [*local, manifest]:
            archive.add(path, arcname=str(path.relative_to(REPO)), recursive=False)


def evaluate(split, step):
    # Evaluate the long run with the same prompt, gate and fallback as its parent.
    import co_eval
    from co_eval import actor_file
    checkpoint = ROOT / "checkpoints" / f"{step:06}" / "model.mkqb"
    if step:
        assert sha(checkpoint) == read(checkpoint.parent / "manifest.json")["Q4_sha256"]
    path = PREVIOUS / "recovery.jsonl" if split == "recovery" else ROOT / f"{split}.jsonl"
    with patch.multiple(co_eval, ROOT=ROOT, path_for=lambda _: path,
                        actor_file=lambda _: checkpoint if step else actor_file(0),
                        check_inputs=check_inputs):
        co_eval.evaluate(split, step)


def complete_audit(training):
    steps = [c["step"] for c in training["checkpoints"]]
    assert steps and all(sha(ROOT / "checkpoints" / f"{c['step']:06}" / "manifest.json") == c["manifest_sha256"]
                         for c in training["checkpoints"])
    script = str(Path(__file__).resolve())

    def run(split, step):
        write(ROOT / "status.json", {"phase": "Q4", "split": split, "step": step})
        subprocess.run([sys.executable, "-u", script, "eval", split, str(step)], cwd=REPO, check=True)

    for split in ("recovery", "validation"):
        for step in (0, *steps):
            run(split, step)
    import co_eval
    with patch.multiple(co_eval, ROOT=ROOT, STEPS=tuple(steps)):
        co_eval.select()
    selected = read(ROOT / "preselected.json")
    run("closed", 0)
    run("closed", selected["audit_step"])
    endpoint = steps[-1]
    if endpoint != selected["audit_step"]:
        # The fixed endpoint is also kept for audit, irrespective of selection.
        write(ROOT / "endpoint.json", {"step": endpoint, "validation_choice": selected["audit_step"]})
        # Reuse the evaluator with an isolated selection receipt and shared baseline.
        folder = ROOT / "endpoint-evaluation"
        write(folder / "preselected.json", {"audit_step": endpoint})
        link = folder / "eval/closed-0000"
        link.parent.mkdir(parents=True, exist_ok=True)
        if not link.exists():
            link.symlink_to(ROOT / "eval/closed-0000", target_is_directory=True)
        checkpoint = ROOT / "checkpoints" / f"{endpoint:06}" / "model.mkqb"
        assert sha(checkpoint) == read(checkpoint.parent / "manifest.json")["Q4_sha256"]
        with patch.multiple(co_eval, ROOT=folder, path_for=lambda _: ROOT / "closed.jsonl",
                            actor_file=lambda _: checkpoint, check_inputs=check_inputs):
            co_eval.evaluate("closed", endpoint)
    all_reports = sorted(ROOT.glob("eval/*/complete.json"))
    all_reports += sorted(p for p in ROOT.glob("endpoint-evaluation/eval/closed-*/complete.json")
                          if not p.parent.is_symlink())
    write(ROOT / "complete.json", {"complete": True, "training_sha256": sha(ROOT / "training.json"),
                                   "selection_sha256": sha(ROOT / "preselected.json"),
                                   "step": selected["audit_step"], "endpoint": endpoint,
                                   "eval": {str(p.parent.relative_to(ROOT)): sha(p) for p in all_reports}})
    write(ROOT / "status.json", {"phase": "complete", "selected": selected["audit_step"], "endpoint": endpoint})


def pipeline():
    try:
        check_inputs()
        path = ROOT / "training.json"
        if path.is_file():
            report = read(path)
        else:
            write(ROOT / "status.json", {"phase": "training"})
            report = train()
        if report["interrupted"]:
            write(ROOT / "status.json", {"phase": "interrupted", "step": report["optimizer_updates"]})
            return
        assert report["seconds"] >= DURATION
        complete_audit(report)
    except (Exception, KeyboardInterrupt) as error:
        write(ROOT / "status.json", {"phase": "failed", "error": f"{type(error).__name__}: {error}"})
        raise


def launch():
    # Reuse the same resource limits and detached Docker configuration as before.
    remote = cn_run.remote
    with patch.object(cn_run, "remote", lambda src: remote(src.replace("/cn_run.py pipeline", "/cp_run.py pipeline"))):
        cn_run.launch()


def fetch():
    source = cn_run.prefix() + '''
import sys,tarfile
assert json.loads((folder/'complete.json').read_text())['complete']
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as archive:
    paths=sorted(p for p in folder.glob('**/*') if p.is_file() and not p.is_symlink())
    for p in paths:
        if 'teacher-cache' in p.parts or (p.parent==folder and p.name in ('deploy.tar.gz','lessons.jsonl')):
            continue
        if any(x.is_symlink() for x in p.parents if x != folder and folder in x.parents):
            continue
        archive.add(p,arcname=str(p.relative_to(folder)),recursive=False)
'''
    with subprocess.Popen([*cn_run.SSH, "python3 -c " + shlex.quote(source)], stdout=subprocess.PIPE) as child:
        with tarfile.open(fileobj=child.stdout, mode="r|gz") as archive:
            archive.extractall(ROOT, filter="data")
        if child.wait(timeout=45):
            raise RuntimeError("Could not fetch the audit")
    complete = read(ROOT / "complete.json")
    assert sha(ROOT / "training.json") == complete["training_sha256"]
    assert sha(ROOT / "preselected.json") == complete["selection_sha256"]
    for name, digest in complete["eval"].items():
        folder = ROOT / name
        assert sha(folder / "complete.json") == digest
        result = read(folder / "complete.json")
        for f in ("full", "metrics"):
            assert sha(folder / f"{f}.json") == result[f"{f}_sha256"]
    print(complete)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("prepare", "deploy", "launch", "status", "fetch", "pipeline", "eval"))
    parser.add_argument("split", nargs="?", choices=("recovery", "validation", "closed"))
    parser.add_argument("step", nargs="?", type=int)
    args = parser.parse_args()
    with patch.multiple(cn_run, ROOT=ROOT, RUN_NAME=ROOT.name, prepare=prepare):
        actions = {"prepare": prepare, "deploy": cn_run.deploy, "launch": launch, "status": cn_run.status,
                   "fetch": fetch, "pipeline": pipeline, "eval": lambda: evaluate(args.split, args.step)}
        actions[args.stage]()
