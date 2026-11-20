"""Freeze the translator course and prepare the isolated GPU work directory."""

from collections import Counter
import shutil
import tarfile

from ay_common import read, rows, save_rows, sha, write
from az_data import numbers
from be_language import paths3
from bh_common import signature
from ck_data import LITERALS, ROOT, SOURCE
from ck_train import ADAPTER, ADAPTER_BASE, CURRENT, REPO, TARGET_SECONDS
from ci_eval import check_frozen


def replay_goals(train, held, holdout_literals):
    protected = {signature(row["spec"]) for row in rows(ROOT / "retention.jsonl")}
    labels = {(row["spec"]["angle"], row["task"]): signature(row["spec"]) for row in train}
    previous = ROOT.parent / "spec-phase-adapter-v1"
    replay = []
    for path in (previous / "train.jsonl", previous / "replay.jsonl", ROOT.parent / "spec-retention-recovery-v1" / "anchors.jsonl"):
        for row in rows(path):
            spec = row["spec"]
            if signature(spec) in protected or paths3(spec["X"]) & held or numbers(spec["X"]) & holdout_literals:
                continue
            key = (spec["angle"], row["task"])
            if key in labels:
                continue
            labels[key] = signature(spec)
            replay.append({key: row[key] for key in ("id", "task", "spec", "pool", "public_inputs")})
    return replay


def main():
    check_frozen()
    assert not (ROOT / "train-frozen.json").exists()
    wording = read(ROOT / "wording-frozen.json")
    for name, digest in wording["files"].items():
        assert sha(ROOT / name) == digest
    train, dev, test = [rows(ROOT / (s + ".jsonl")) for s in ("train", "development", "closed")]
    assert (len(train), len(dev), len(test)) == (640, 96, 256)
    held = set().union(*(paths3(g["spec"]["X"]) for g in [*dev, *test]))
    holdout_literals = {v.lstrip("-") for split in ("development", "closed") for v in LITERALS[split]}
    assert not {signature(g["spec"]) for g in dev} & {signature(g["spec"]) for g in test}
    withheld = {signature(g["spec"]) for g in [*dev, *test, *rows(ROOT / "retention.jsonl")]}
    assert not any(signature(g["spec"]) in withheld or paths3(g["spec"]["X"]) & held or
                   numbers(g["spec"]["X"]) & holdout_literals for g in train)
    replay = replay_goals(train, held, holdout_literals)
    assert len(replay) >= 2000
    save_rows(ROOT / "replay.jsonl", replay)
    save_rows(ROOT / "train-compact.jsonl", [{key: value for key, value in g.items()
                                              if key in {"id", "task", "spec", "pool", "public_inputs", "contrast_id", "contrast_side"}}
                                             for g in train])
    proof = {"train": len(train), "pairs": len({g["contrast_id"] for g in train if "contrast_id" in g}),
             "replay": len(replay), "development": len(dev), "closed": len(test), "retention": 48,
             "held_operation_triples": len(held), "sources": Counter(g["wording_source"] for g in train),
             "no_test_families_or_literals_in_training": True, "target_update_seconds": TARGET_SECONDS}
    write(ROOT / "course.json", proof)
    here = REPO / "research/mk61-agent-20261106"
    code = list(here.glob("*.py"))
    models = [*ADAPTER_BASE.glob("hf/*"), ADAPTER_BASE / "model.mkqb", ADAPTER, CURRENT / "translator/model.mkqb"]
    files = [*code, *models, ROOT / "train-compact.jsonl", ROOT / "replay.jsonl", ROOT / "course.json"]
    write(ROOT / "train-frozen.json", {"files": {str(path.relative_to(REPO)): sha(path) for path in files}})
    exam_code = [here / name for name in ("ck_eval.py", "ce_eval.py", "ci_eval.py", "ci_runtime.py", "cg_eval.py", "cg_runtime.py",
                                        "cf_eval.py", "cf_runtime.py", "cg_language.py", "cf_language.py", "ce_short_path.py")]
    tests = [*exam_code, *(ROOT / name for name in ("development.jsonl", "closed.jsonl", "retention.jsonl", "course.json")),
             SOURCE / "frozen.json", ROOT / "train-frozen.json"]
    write(ROOT / "exam-frozen.json", {"files": {str(path.relative_to(REPO)): sha(path) for path in tests},
                                    "closed_used_for_selection": False, "source": str(SOURCE.relative_to(REPO))})
    with tarfile.open(ROOT / "train-deploy.tar.gz", "w:gz", compresslevel=5) as bundle:
        for path in [*files, ROOT / "train-frozen.json"]:
            bundle.add(path, arcname=str(path.relative_to(REPO)), recursive=False)
    print(proof, flush=True)


if __name__ == "__main__":
    main()
