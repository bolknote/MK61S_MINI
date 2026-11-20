"""Use DeepSeek for test wording only, with blind reverse checks."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

import bj_teacher as teacher
from ay_common import read, rows, save_rows, sha, write
from ce_data import ROOT, reword
from ce_wording import editorial_question


def main():
    assert not (ROOT / "frozen.json").exists()
    source = ROOT / "closed-asts.jsonl"
    assert sha(source) == read(ROOT / "ast-frozen.json")["sha256"]
    goals = rows(source)
    teacher.ROOT = ROOT
    teacher.URL = "http://127.0.0.1:18107/v1/chat/completions"
    client = teacher.Client()
    pending = [g for g in goals if g["wording_cohort"] == "freeform"]
    audit = []
    accepted = {}
    errors = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        batches = [pending[i:i + 4] for i in range(0, len(pending), 4)]
        jobs = {executor.submit(teacher.chunk, client, batch): batch for batch in batches}
        for i, future in enumerate(as_completed(jobs), 1):
            batch = jobs[future]
            try:
                result, reviews = future.result()
            except Exception as exc:
                errors.append({"tasks": [g["id"] for g in batch], "error": repr(exc)})
            else:
                audit.extend(reviews)
                for goal in batch:
                    matches = result[goal["id"]]
                    if matches:
                        accepted[goal["id"]] = matches[0]["text"]
            if i % 4 == 0 or i == len(jobs):
                progress = {"batches_done": i, "batches": len(jobs), "wordings_accepted": len(accepted), "failed_batches": len(errors)}
                write(ROOT / "teacher-status.json", progress)
                print(progress, flush=True)
    final = []
    for index, goal in enumerate(goals):
        if goal["wording_cohort"] == "freeform":
            if goal["id"] in accepted:
                goal = reword(goal, accepted[goal["id"]], "deepseek_blind_reviewed")
            else:
                goal = reword(goal, editorial_question(goal["spec"], index), "local_editorial_templates")
        final.append(goal)
    assert len(final) == len({(g["task"], g["spec"]["angle"]) for g in final}) == 256
    save_rows(ROOT / "teacher-audit.jsonl", audit)
    save_rows(ROOT / "closed.jsonl", final)
    write(ROOT / "teacher-wording.json", {
        "model": teacher.MODEL, "counts": dict(Counter(g["wording_source"] for g in final)),
        "errors": errors, "teacher_used_only_to_word_test": True, "blind_reviews_per_accepted_wording": 2,
        "closed_sha256": sha(ROOT / "closed.jsonl"), "audit_sha256": sha(ROOT / "teacher-audit.jsonl"),
    })


if __name__ == "__main__":
    main()
