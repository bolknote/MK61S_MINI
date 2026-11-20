"""Seal the new evaluation and package a self-contained unattended run."""

from collections import Counter
import tarfile

from ay_common import read, rows, save_rows, sha, write
from az_data import numbers
from be_language import paths3
from bh_common import signature
from ck_data import wording
from ck_train import ADAPTER_BASE, CURRENT, REPO
from cl_data import LITERALS, PARENT, PREVIOUS, ROOT, recovery_targets
from cl_train import LR, SECONDS
from ci_eval import check_frozen


KEYS = {"id", "task", "spec", "pool", "public_inputs", "source_id", "contrast_id", "contrast_side"}


def unique(goals):
    distinct = {}
    for goal in goals:
        old = distinct.setdefault((goal["spec"]["angle"], visible(goal)), goal)
        assert signature(old["spec"]) == signature(goal["spec"]), goal["id"]
    return list(distinct.values())


def visible(goal):
    return " ".join(goal["task"].casefold().replace("ё", "е").split())


def compact_file(name, goals):
    save_rows(ROOT / (name + ".jsonl"), [{key: value for key, value in g.items() if key in KEYS} for g in goals])


def seal():
    if (ROOT / "exam-frozen.json").exists() and (ROOT / "train-deploy.tar.gz").exists():
        return
    check_frozen()
    foundation = read(ROOT / "ast-frozen.json")
    assert all(sha(ROOT / name) == expected for name, expected in foundation["files"].items())
    teacher = read(ROOT / "teacher-frozen.json")
    assert sha(ROOT / "reworded.jsonl") == teacher["sha256"]
    manifest = read(PARENT / "manifest.json")
    assert sha(PARENT / "model.mkqb") == manifest["Q4_sha256"]
    assert sha(PARENT / "adapter.safetensors") == manifest["adapter_sha256"]

    focus, lost, errors, successes = recovery_targets()
    fresh = {split: wording(rows(ROOT / f"{split}-asts.jsonl"), {}, split) for split in ("train", "development", "closed")}
    keep = [g for g in rows(ROOT / "retention.jsonl") if g["id"] not in {x["id"] for x in focus}]
    retention = [*focus, *keep]
    assert len({g["id"] for g in retention}) == len(retention)
    save_rows(ROOT / "recovery.jsonl", retention)
    for split in ("development", "closed"):
        save_rows(ROOT / (split + ".jsonl"), fresh[split])
    exam = [*fresh["development"], *fresh["closed"]]
    exam_text = {(g["spec"]["angle"], visible(g)) for g in exam}
    assert len(exam_text) == len(exam)
    # The three-operation families deliberately assigned to the fresh exams were
    # excluded from the entire previously observed corpus during generation.
    held = {tuple(path) for split in ("development", "closed") for path in foundation["composition_families"][split]}
    held_signatures = {signature(g["spec"]) for g in exam}
    held_numbers = {text.lstrip("-") for split in ("development", "closed") for text in LITERALS[split]}

    def allowed(goal):
        spec = goal["spec"]
        return (signature(spec) not in held_signatures and not paths3(spec["X"]) & held
                and not numbers(spec["X"]) & held_numbers and (spec["angle"], visible(goal)) not in exam_text)

    reworded = rows(ROOT / "reworded.jsonl")
    focus_ids = {g["id"] for g in focus}
    new_focus = unique([*focus, *(g for g in reworded if g["source_id"] in focus_ids)])
    new_errors = unique([*errors, *(g for g in reworded if g["source_id"] not in focus_ids)])
    assert all(allowed(g) for g in [*fresh["train"], *new_focus, *new_errors])
    protected = {signature(g["spec"]) for g in keep}
    old_train = [{k: v for k, v in g.items() if k not in ("contrast_id", "contrast_side")} for g in rows(PREVIOUS / "train-compact.jsonl")]
    reserved = {(g["spec"]["angle"], visible(g)) for g in [*fresh["train"], *new_focus, *new_errors]}
    replay = unique([g for g in [*successes, *old_train, *rows(PREVIOUS / "replay.jsonl")]
                     if allowed(g) and signature(g["spec"]) not in protected
                     and (g["spec"]["angle"], visible(g)) not in reserved])
    assert len(replay) >= 2000
    for name, values in (("train-compact", fresh["train"]), ("focus", new_focus),
                         ("composition-errors", new_errors), ("replay", replay)):
        compact_file(name, values)
    policy = {"seconds": SECONDS, "lr": LR, "fresh_training_goals": len(fresh["train"]),
              "target_repairs": lost, "target_training_wordings": len(new_focus), "previous_composition_errors": len(errors),
              "composition_error_wordings": len(new_errors), "DeepSeek_variants": len(reworded), "replay": len(replay),
              "retention_tasks": len(retention), "development": len(fresh["development"]), "closed": len(fresh["closed"]),
              "closed_groups": Counter(g["family"] for g in fresh["closed"]), "held_operation_triples": len(held),
              "same_actor_and_runtime": True, "selection_uses_only_development_and_recovery": True,
              "closed_runs": ["original", "one_hour_parent", "validation_selected", "fixed_three_hour_endpoint"]}
    write(ROOT / "policy.json", policy)
    here = REPO / "research/mk61-agent-20261106"
    code = list(here.glob("*.py"))
    model_files = [*ADAPTER_BASE.glob("hf/*"), ADAPTER_BASE / "model.mkqb", *PARENT.glob("*")]
    train_files = [*code, *model_files, *(ROOT / (name + ".jsonl") for name in ("train-compact", "focus", "composition-errors", "replay")),
                   ROOT / "policy.json"]
    write(ROOT / "train-frozen.json", {"files": {str(p.relative_to(REPO)): sha(p) for p in train_files}})
    vm_source = ROOT.parent / "full-isa-v1" / "core-source"
    eval_files = [*(here / name for name in ("full_isa_bridge.cpp", "core_bridge.cpp")), *vm_source.glob("*"),
                  *(p for role in ("translator", "working") for p in (CURRENT / role).rglob("*") if p.is_file() and p.suffix != ".mka"),
                  *(ROOT / (name + ".jsonl") for name in ("development", "closed", "recovery")), ROOT / "train-frozen.json"]
    eval_code = [here / name for name in ("cl_eval.py", "cl_report.py", "ck_eval.py", "ce_eval.py", "ci_eval.py", "ci_runtime.py",
                                        "cg_eval.py", "cg_runtime.py", "cf_eval.py", "cf_runtime.py", "cg_language.py", "cf_language.py")]
    write(ROOT / "exam-frozen.json", {"files": {str(p.relative_to(REPO)): sha(p) for p in [*eval_code, *eval_files]}})
    inputs = {*train_files, *eval_files, ROOT / "exam-frozen.json"}
    with tarfile.open(ROOT / "train-deploy.tar.gz", "w:gz", compresslevel=5) as archive:
        for path in sorted(inputs):
            archive.add(path, arcname=str(path.relative_to(REPO)), recursive=False)
    print(policy, flush=True)


if __name__ == "__main__":
    seal()
