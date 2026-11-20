"""Three-hour Q4 continuation of the trained Kon-Tiki translation adapter."""

from collections import defaultdict
import math
import time
from unittest.mock import patch

import torch
from torch.nn.utils import parametrize

import ck_train
from aq_course import pad
from ay_common import read, rows, sha, write
from az_teacher import pool_for
from bu_common import body_ids
from bu_course import loss
from bu_model import Translator, frozen_digest
from cl_data import PARENT, ROOT
from native_export import packet


SECONDS = 10800
MILESTONES = (3600, 7200, SECONDS)
SEED = 261114957
LR = 5e-6
REPO = ck_train.REPO


def check_frozen(stage):
    manifest = read(ROOT / f"{stage}-frozen.json")
    for path, expected in manifest["files"].items():
        assert sha(REPO / path) == expected, path
    return manifest


class RecoveryCourse(ck_train.Course):
    def __init__(self, tokenizer):
        with patch.multiple(ck_train, ROOT=ROOT, SEED=SEED):
            super().__init__(tokenizer)
        self.focus = []
        self.errors = defaultdict(list)
        for file in ("focus", "composition-errors"):
            for goal in rows(ROOT / (file + ".jsonl")):
                key = len(self.goals)
                base = pool_for("")
                goal["pool"] = base + [v for v in goal["pool"] if v not in base]
                self.goals[key] = goal
                if file == "focus":
                    self.focus.append(key)
                else:
                    self.errors[goal.get("source_id", goal["id"])].append(key)
        self.error_families = list(self.errors)
        assert len(self.error_families) == 67 and len(self.focus) >= 3

    def step(self, device):
        values = []
        for identity in self.rng.sample(self.pair_keys, 3):
            layout = self.rng.choice((0, 1, 2, 3, 4, 7))
            remaining = self.rng.choice((12, 12, 12, 7))
            values.extend(self.sample(key, "pair", layout, remaining) for key in self.pairs[identity])
        for group, keys in (
            ("recovery_targets", self.rng.sample(self.focus, 2)),
            ("composition_errors", [self.rng.choice(self.errors[k]) for k in self.rng.sample(self.error_families, 5)]),
            ("new_compositions", self.rng.sample(self.compositions, 3)),
            ("retained", self.rng.sample(self.replay, 16)),
        ):
            for key in keys:
                layout = self.rng.choice((0, 0, 0, 2, 3, 4, 7))
                remaining = self.rng.choice((12, 12, 12, 7))
                values.append(self.sample(key, group, layout, remaining))
        assert len(values) == ck_train.BATCH
        values.sort(key=lambda value: len(value[0]))
        return [pad(values[i:i + ck_train.MICRO], device) for i in range(0, len(values), ck_train.MICRO)]


def run():
    torch.set_num_threads(2)
    torch.manual_seed(SEED)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.cuda.set_device(0)
    torch.cuda.set_per_process_memory_fraction(ck_train.LIMIT_MIB * 2**20 / torch.cuda.get_device_properties(0).total_memory)
    freeze = check_frozen("train")
    assert not (ROOT / "training.json").exists()
    model = Translator("cuda:0", PARENT / "adapter.safetensors")
    model.packed(ROOT / "initial.mkqb")
    packed, data = packet(ROOT / "initial.mkqb")
    expected, expected_data = packet(PARENT / "model.mkqb")
    for header in (packed, expected):
        for key in ("transformers_version", "_name_or_path"):
            header["config"].pop(key, None)
    assert packed == expected and data == expected_data
    before = frozen_digest(model)
    params = [p for p in model.parameters() if p.requires_grad]
    assert sum(p.numel() for p in params) == 317440
    head = torch.tensor(body_ids(model.tokenizer), device="cuda:0")
    optimizer = torch.optim.AdamW(params, lr=LR, weight_decay=0.001)
    torch.cuda.reset_peak_memory_stats()
    with parametrize.cached():
        probe = loss(model, RecoveryCourse(model.tokenizer).step("cuda:0")[0], head)
    probe.backward()
    torch.cuda.synchronize()
    assert torch.isfinite(probe) and all(p.grad is None or torch.isfinite(p.grad).all() for p in params)
    write(ROOT / "preflight.json", {"updates": 0, "initial_hour_Q4_equal": True, "loss": float(probe.detach()),
                                    "peak_reserved_MiB": torch.cuda.max_memory_reserved() / 2**20,
                                    "gpu": torch.cuda.get_device_name(0)})
    del probe
    course = RecoveryCourse(model.tokenizer)
    elapsed, step, checkpoints, losses = 0.0, 0, [], []
    started = time.monotonic()
    with patch.object(ck_train, "ROOT", ROOT):
        while elapsed < SECONDS:
            iteration = time.monotonic()
            step += 1
            decay = .25 + .75 * (1.0 + math.cos(math.pi * elapsed / SECONDS)) / 2
            optimizer.param_groups[0]["lr"] = LR * min(1.0, step / 100) * decay
            optimizer.zero_grad(set_to_none=True)
            total = 0.0
            for batch in course.step("cuda:0"):
                with parametrize.cached():
                    value = loss(model, batch, head) / (ck_train.BATCH // ck_train.MICRO)
                value.backward()
                total += float(value.detach())
            torch.nn.utils.clip_grad_norm_(params, 1.0, error_if_nonfinite=True)
            optimizer.step()
            torch.cuda.synchronize()
            elapsed += time.monotonic() - iteration
            losses.append(total)
            if step == 1 or step % 100 == 0:
                ck_train.status("training", step=step, seconds=round(elapsed, 1), target_seconds=SECONDS,
                                loss=round(sum(losses[-100:]) / len(losses[-100:]), 6),
                                peak_reserved_MiB=torch.cuda.max_memory_reserved() / 2**20)
            if elapsed >= MILESTONES[len(checkpoints)]:
                assert frozen_digest(model) == before
                point = ck_train.save_checkpoint(model, step, elapsed, f"{MILESTONES[len(checkpoints)] // 60}m")
                checkpoints.append(str(point.relative_to(ROOT)))
        assert len(checkpoints) == len(MILESTONES)
        assert frozen_digest(model) == before and check_frozen("train") == freeze
        write(ROOT / "training.json", {"optimizer_updates": step, "update_elapsed_seconds": elapsed,
                                      "wall_seconds": time.monotonic() - started, "checkpoints": checkpoints,
                                      "counts": dict(course.counts), "unique_rows_seen": {k: len(v) for k, v in course.coverage.items()},
                                      "trainable_parameters": 317440, "Q4_every_forward": True, "frozen_base_verified": True,
                                      "peak_reserved_MiB": torch.cuda.max_memory_reserved() / 2**20})
        ck_train.status("complete", optimizer_updates=step, seconds=elapsed)


if __name__ == "__main__":
    run()
