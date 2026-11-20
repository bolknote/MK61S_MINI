"""Time-bounded Q4 continuation from the verified working executor."""

from collections import defaultdict, deque
import math
import signal
import time
from unittest.mock import patch

import torch
from torch.nn.utils import parametrize

import ck_train
import co_train
from aq_course import pad
from ay_common import read, rows, save_rows, sha, write
from be_course import loss
from bl_spec import install
from bl_vm import CachedVM
from bu_model import body_ids, frozen_digest
from cn_data import REVIEW_GROUPS, review_states
from co_train import BATCH, MICRO, REPO, tokens
from cp_data import ROOT, SEED


DURATION = 12 * 3600
MILESTONES = (1, 3, 6, 9, 12)
LR = 4e-6


def check_inputs():
    manifest = read(ROOT / "inputs-frozen.json")
    for name, digest in manifest["files"].items():
        assert sha(REPO / name) == digest, name
    return manifest


def make_lessons():
    install()
    vm = CachedVM(384)
    examples = []
    for name in ("power-train", "composition-train"):
        for goal in rows(ROOT / f"{name}.jsonl"):
            pair = list(review_states(goal, vm))
            if all(pair):
                examples.extend({**row, "course": name} for row in pair)
    assert len(examples) >= 2000
    save_rows(ROOT / "lessons.jsonl", examples)


class Course(co_train.Course):
    def __init__(self):
        super().__init__()
        self.random.seed(SEED)
        self.new_pairs = defaultdict(list)
        by_task = defaultdict(dict)
        for row in rows(ROOT / "lessons.jsonl"):
            by_task[row["course"], row["task_id"]][row["group"]] = row
        for (name, _), group in by_task.items():
            assert all(k in group for k in REVIEW_GROUPS)
            self.new_pairs[name].append(group)
        assert all(self.new_pairs[name] for name in ("power-train", "composition-train"))

    def draw(self, device):
        selected = []
        for name, action in (
            ("power-train", "repair"),
            ("power-train", "keep"),
            ("composition-train", "repair"),
            ("composition-train", "keep"),
        ):
            pair = self.random.choice(self.new_pairs[name])
            counterexample = "bad_spec_bad_code" if action == "repair" else "bad_spec_good_code"
            for group in (action, counterexample, "run_missing"):
                self.counts[f"{name}/{group}"] += 1
                selected.append(pair[group])
        for group, count in (("repair", 2), ("keep", 2), ("run_missing", 1),
                             ("bad_spec_good_code", 1), ("bad_spec_bad_code", 1)):
            selected.extend(self.choose(self.teacher[group], f"DeepSeek/{group}", count))
        for group in REVIEW_GROUPS:
            selected.extend(self.choose(self.replay[group], f"replay/{group}", 1))
        assert len(selected) == BATCH
        writes = [r for r in selected if r["action"] == "write"]
        others = [r for r in selected if r["action"] != "write"]
        self.random.shuffle(writes)
        self.random.shuffle(others)
        count = BATCH // MICRO
        rest = writes[count:] + others
        for i, repair in enumerate(writes[:count]):
            records = [repair, *rest[i * (MICRO - 1):(i + 1) * (MICRO - 1)]]
            assert len(records) == MICRO
            batch = pad([tokens(r["short"], r["action"], tuple(r["body"])) for r in records], device)
            yield (*batch, torch.ones(MICRO, device=device, dtype=torch.bool))


def save(model, step, seconds, name, base):
    assert frozen_digest(model) == base
    with patch.object(ck_train, "ROOT", ROOT):
        return ck_train.save_checkpoint(model, step, seconds, name)


def train(duration=DURATION):
    root_manifest = check_inputs()
    torch.set_num_threads(2)
    torch.manual_seed(SEED)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    device = "cuda:0"
    torch.cuda.set_device(0)
    torch.cuda.set_per_process_memory_fraction(2**31 / torch.cuda.get_device_properties(0).total_memory)
    with patch.object(co_train, "ROOT", ROOT):
        actor = co_train.initial_actor(device)
    base = frozen_digest(actor)
    actor.train()
    course = Course()
    parameters = [p for p in actor.parameters() if p.requires_grad]
    assert sum(p.numel() for p in parameters) == 317440
    head = torch.tensor(body_ids(actor.tokenizer), device=device)
    adam = torch.optim.AdamW(parameters, lr=LR, weight_decay=0.001)
    recent = deque(maxlen=100)
    stop = False

    def on_stop(_sig, _frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, on_stop)
    signal.signal(signal.SIGINT, on_stop)
    saved = []
    marks = iter(MILESTONES)
    mark = next(marks, None)
    started = time.monotonic()
    start_unix = time.time()
    write(ROOT / "train-status.json", {"phase": "training", "updates": 0, "target_seconds": duration,
                                      "started_unix": start_unix, "expected_training_end_unix": start_unix + duration})
    step = 0
    while not stop and (elapsed := time.monotonic() - started) < duration:
        step += 1
        warm = min(1, step / 60)
        cosine = 0.20 + 0.80 * (1 + math.cos(math.pi * elapsed / duration)) / 2
        adam.param_groups[0]["lr"] = LR * warm * cosine
        adam.zero_grad(set_to_none=True)
        total = 0
        for batch in course.draw(device):
            with parametrize.cached():
                value, _ = loss(actor, batch, head)
            (value / (BATCH // MICRO)).backward()
            total += float(value.detach()) / (BATCH // MICRO)
        torch.nn.utils.clip_grad_norm_(parameters, 1.0, error_if_nonfinite=True)
        adam.step()
        recent.append(total)
        elapsed = time.monotonic() - started
        if step == 1 or step % 100 == 0:
            status = {"phase": "training", "updates": step, "seconds": elapsed, "target_seconds": duration,
                      "started_unix": start_unix, "expected_training_end_unix": start_unix + duration,
                      "loss": sum(recent) / len(recent), "peak_reserved_MiB": torch.cuda.max_memory_reserved() / 2**20}
            write(ROOT / "train-status.json", status)
            print(status, flush=True)
        if mark is not None and elapsed >= mark * 3600 and mark < 12:
            folder = save(actor, step, elapsed, f"{mark}h", base)
            saved.append({"step": step, "milestone": f"{mark}h", "manifest_sha256": sha(folder / "manifest.json")})
            mark = next(marks, None)
    elapsed = time.monotonic() - started
    assert step > 0
    name = "interrupted" if stop else "12h"
    folder = save(actor, step, elapsed, name, base)
    if not saved or saved[-1]["step"] != step:
        saved.append({"step": step, "milestone": name, "manifest_sha256": sha(folder / "manifest.json")})
    assert check_inputs() == root_manifest
    report = {"optimizer_updates": step, "seconds": elapsed, "target_seconds": duration, "started_unix": start_unix,
              "interrupted": stop, "checkpoints": saved, "counts": course.counts,
              "parent_tensor_parity": True, "parent_sha256": sha(co_train.parent_dir() / "model.mkqb")}
    write(ROOT / "training.json", report)
    write(ROOT / "train-status.json", {"phase": name, **report})
    return report
