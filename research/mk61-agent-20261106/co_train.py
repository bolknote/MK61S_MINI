"""Continue the exact Q4 executor adapter with matched positive and negative states."""

from collections import Counter, defaultdict
from functools import lru_cache
import math
import random
import time
from unittest.mock import patch

import torch
from torch.nn.utils import parametrize

import ck_train
import cn_train
from aq_course import pad
from aq_protocol import ACTIONS
from ay_common import read, rows, sha, write
from be_course import loss
from bu_model import body_ids, frozen_digest
from ck_train import REPO
from cn_data import REVIEW_GROUPS, tokenized
from cn_runtime import CONTEXT
from co_data import PARENT, ROOT, SEED
from native_export import packet


STEPS = (300, 850, 1500)
BATCH = 24
MICRO = 6
LR = 1.6e-5
PARENT_STEP = 900


def parent_dir():
    folder = PARENT / "checkpoints" / f"{PARENT_STEP:06}"
    receipt = read(folder / "manifest.json")
    assert sha(folder / "model.mkqb") == receipt["Q4_sha256"]
    assert sha(folder / "adapter.safetensors") == receipt["adapter_sha256"]
    return folder


def check_inputs():
    manifest = read(ROOT / "inputs-frozen.json")
    for name, digest in manifest["files"].items():
        assert sha(REPO / name) == digest, name
    return manifest


@lru_cache(maxsize=10000)
def tokens(prompt, action, body):
    x, y, at = tokenized(prompt, action, body)
    assert len(x) <= CONTEXT
    return x, y, at, ACTIONS.index(action)


class Course:
    def __init__(self):
        self.random = random.Random(SEED)
        self.counts = Counter()
        self.teacher = defaultdict(list)
        self.replay = defaultdict(list)
        by_goal = defaultdict(dict)
        for row in rows(ROOT / "teacher-lessons.jsonl"):
            self.teacher[row["group"]].append(row)
        for row in rows(ROOT / "matched-lessons.jsonl"):
            if "refusal_id" not in row:
                by_goal[row["task_id"]][row["group"]] = row
        self.pairs = [group for group in by_goal.values() if all(k in group for k in REVIEW_GROUPS)]
        self.hard = rows(ROOT / "retired-refusals.jsonl")
        for row in rows(PARENT / "replay-lessons.jsonl"):
            self.replay[row["group"]].append(row)
        assert self.pairs and self.hard and self.teacher["repair"]

    def choose(self, source, group, count):
        self.counts[group] += count
        return self.random.choices(source, k=count)

    def draw(self, device):
        p, q, r = self.random.sample(self.pairs, 3)
        values = []
        # Two different comparisons have the same condition and code bytes.
        for pair, names in ((p, ("repair", "bad_spec_bad_code")),
                            (q, ("keep", "bad_spec_good_code")),
                            (r, ("repair", "keep", "run_missing"))):
            for name in names:
                values.append(pair[name])
                self.counts[f"paired/{name}"] += 1
        values += self.choose(self.hard, "observed_false_refusal", 2)
        for group, count in (("repair", 5), ("keep", 2), ("run_missing", 1),
                             ("bad_spec_good_code", 1), ("bad_spec_bad_code", 1)):
            source = self.teacher[group] or self.replay[group]
            tag = "teacher" if self.teacher[group] else "replay"
            values += self.choose(source, f"{tag}/{group}", count)
        for group in ("repair", "keep", "run_missing", "bad_spec_good_code", "bad_spec_bad_code"):
            values += self.choose(self.replay[group], f"replay/{group}", 1)
        assert len(values) == BATCH
        fixes = [r for r in values if r["action"] == "write"]
        other = [r for r in values if r["action"] != "write"]
        self.random.shuffle(fixes)
        self.random.shuffle(other)
        count = BATCH // MICRO
        rest = fixes[count:] + other
        for i, write_row in enumerate(fixes[:count]):
            batch = [write_row, *rest[i * (MICRO - 1):(i + 1) * (MICRO - 1)]]
            assert len(batch) == MICRO
            data = pad([tokens(r["short"], r["action"], tuple(r["body"])) for r in batch], device)
            yield (*data, torch.ones(MICRO, device=device, dtype=torch.bool))


def initial_actor(device):
    model = cn_train.new_actor(device)
    parent = parent_dir()
    model.load_checkpoint(parent / "adapter.safetensors")
    path = ROOT / "initial.mkqb"
    model.packed(path)
    header, payload = packet(path)
    original, source = packet(parent / "model.mkqb")
    assert header["tensors"] == original["tensors"] and payload == source
    assert header["mode"] == original["mode"] == "q4"
    return model


def train():
    torch.set_num_threads(2)
    torch.manual_seed(SEED)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    device = "cuda:0"
    torch.cuda.set_device(0)
    torch.cuda.set_per_process_memory_fraction(2**31 / torch.cuda.get_device_properties(0).total_memory)
    manifest = check_inputs()
    actor = initial_actor(device)
    base = frozen_digest(actor)
    params = [p for p in actor.parameters() if p.requires_grad]
    assert sum(p.numel() for p in params) == 317440
    actor.train()
    course = Course()
    head = torch.tensor(body_ids(actor.tokenizer), device=device)
    optimizer = torch.optim.AdamW(params, lr=LR, weight_decay=0.001)
    losses = []
    started = time.monotonic()
    for step in range(1, STEPS[-1] + 1):
        warm = min(1.0, step / 40)
        cosine = 0.30 + 0.70 * (1 + math.cos(math.pi * step / STEPS[-1])) / 2
        optimizer.param_groups[0]["lr"] = LR * warm * cosine
        optimizer.zero_grad(set_to_none=True)
        total = 0.0
        for batch in course.draw(device):
            with parametrize.cached():
                value, _ = loss(actor, batch, head)
            (value / (BATCH // MICRO)).backward()
            total += float(value.detach()) / (BATCH // MICRO)
        torch.nn.utils.clip_grad_norm_(params, 1.0, error_if_nonfinite=True)
        optimizer.step()
        losses.append(total)
        if step == 1 or step % 50 == 0:
            state = {"updates": step, "target": STEPS[-1], "seconds": time.monotonic() - started,
                     "loss": sum(losses[-50:]) / len(losses[-50:]),
                     "peak_reserved_MiB": torch.cuda.max_memory_reserved() / 2**20}
            write(ROOT / "train-status.json", state)
            print(state, flush=True)
        if step in STEPS:
            assert frozen_digest(actor) == base
            with patch.object(ck_train, "ROOT", ROOT):
                ck_train.save_checkpoint(actor, step, time.monotonic() - started, f"refusals-{step}")
    assert frozen_digest(actor) == base
    assert check_inputs() == manifest
    write(ROOT / "training.json", {"optimizer_updates": step, "seconds": time.monotonic() - started,
                                   "counts": course.counts, "frozen_digest": base, "parent_tensor_parity": True,
                                   "parent": sha(parent_dir() / "model.mkqb"), "trainable_parameters": 317440})


if __name__ == "__main__":
    train()
