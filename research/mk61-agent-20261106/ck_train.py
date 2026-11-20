"""Continue the exact Kon-Tiki translator adapter with measured Q4 updates."""

from collections import Counter, defaultdict
from functools import lru_cache
import math
import random
import time

import torch
from torch.nn.utils import parametrize

from aq_course import pad
from ay_common import read, rows, sha, write
from az_teacher import pool_for
from bu_common import SOURCE as ADAPTER_BASE, body_ids
from bu_course import encoded, loss
from bu_model import Translator, frozen_digest
from ck_data import ROOT
from native_export import packet


REPO = ROOT.parents[2]
CURRENT = ROOT.parent / "spec-review-utility-v1" / "profiles"
ADAPTER = ROOT.parent / "spec-phase-adapter-v1" / "server-results" / "last.safetensors"
BATCH = 32
MICRO = 8
TARGET_SECONDS = 3600
SEED = 261114561
LIMIT_MIB = 2048
SECTIONS = (1200, 2400, TARGET_SECONDS)


def status(phase, **data):
    item = {"phase": phase, "unix": time.time(), **data}
    write(ROOT / "train-status.json", item)
    print(item, flush=True)


def check_inputs():
    frozen = read(ROOT / "train-frozen.json")
    for path, digest in frozen["files"].items():
        assert sha(REPO / path) == digest, path
    return frozen


class Course:
    def __init__(self, tokenizer):
        self.tokenizer = tokenizer
        self.rng = random.Random(SEED)
        self.counts = Counter()
        self.coverage = defaultdict(set)
        self.goals = {}
        self.pairs = defaultdict(list)
        self.compositions = []
        self.replay = []
        for name in ("train-compact", "replay"):
            for goal in rows(ROOT / (name + ".jsonl")):
                key = len(self.goals)
                pool = pool_for("")
                goal["pool"] = pool + [value for value in goal["pool"] if value not in pool]
                self.goals[key] = goal
                if name == "replay":
                    self.replay.append(key)
                elif "contrast_id" in goal:
                    self.pairs[goal["contrast_id"]].append(key)
                else:
                    self.compositions.append(key)
        self.pair_keys = list(self.pairs)
        assert all(len(v) == 2 for v in self.pairs.values())
        assert self.pair_keys and self.compositions and self.replay

    @lru_cache(maxsize=24000)
    def lesson(self, key, layout_index, remaining):
        modes = ("default", "default", "extras", "full", "distractors", "default", "extras", "default")
        goal = self.goals[key]
        shared = goal.get("contrast_id", goal["id"])
        return encoded(self.tokenizer, goal, f"{shared}:{layout_index}", modes[layout_index], remaining != 12, remaining)

    def sample(self, key, group, layout_index, remaining):
        self.counts[group] += 1
        self.coverage[group].add(key)
        if remaining != 12:
            self.counts["replan"] += 1
        return self.lesson(key, layout_index, remaining)

    def step(self, device):
        values = []
        for identity in self.rng.sample(self.pair_keys, 6):
            layout_index = self.rng.randrange(8)
            remaining = self.rng.choice([12, 12, 12, 7])
            for key in self.pairs[identity]:
                values.append(self.sample(key, "pair", layout_index, remaining))
        for group, keys, count in (("composition", self.compositions, 8), ("replay", self.replay, 12)):
            for key in self.rng.sample(keys, count):
                values.append(self.sample(key, group, self.rng.randrange(8), self.rng.choice([12, 12, 12, 7])))
        assert len(values) == BATCH
        # Length grouping reduces padding while keeping both sides in the same update.
        values.sort(key=lambda value: len(value[0]))
        return [pad(values[at:at + MICRO], device) for at in range(0, BATCH, MICRO)]


def save_checkpoint(model, step, seconds, name):
    folder = ROOT / "checkpoints" / f"{step:06}"
    folder.mkdir(parents=True, exist_ok=True)
    model.save_checkpoint(folder / "adapter.safetensors")
    model.packed(folder / "model.mkqb")
    write(folder / "manifest.json", {"step": step, "update_elapsed_seconds": seconds, "milestone": name,
                                     "Q4_sha256": sha(folder / "model.mkqb"), "bytes": (folder / "model.mkqb").stat().st_size,
                                     "adapter_sha256": sha(folder / "adapter.safetensors")})
    return folder


def run():
    torch.set_num_threads(3)
    torch.manual_seed(SEED)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.cuda.set_device(0)
    torch.cuda.set_per_process_memory_fraction(LIMIT_MIB * 2**20 / torch.cuda.get_device_properties(0).total_memory)
    frozen = check_inputs()
    assert not (ROOT / "training.json").exists()
    start = time.monotonic()
    model = Translator("cuda:0", ADAPTER)
    initial = ROOT / "initial.mkqb"
    model.packed(initial)
    packed, data = packet(initial)
    expected, expected_data = packet(CURRENT / "translator" / "model.mkqb")
    for header in (packed, expected):
        for key in ("transformers_version", "_name_or_path"):
            header["config"].pop(key, None)
    assert packed == expected and data == expected_data, "Starting Q4 tensors differ from current translator"
    before = frozen_digest(model)
    params = [p for p in model.parameters() if p.requires_grad]
    assert sum(p.numel() for p in params) == 317440
    head = torch.tensor(body_ids(model.tokenizer), device="cuda:0")
    course = Course(model.tokenizer)
    optimizer = torch.optim.AdamW(params, lr=1e-5, weight_decay=0.001)
    torch.cuda.reset_peak_memory_stats()
    optimizer.zero_grad(set_to_none=True)
    with parametrize.cached():
        probe = loss(model, course.step("cuda:0")[0], head)
    probe.backward()
    torch.cuda.synchronize()
    assert torch.isfinite(probe) and all(p.grad is None or torch.isfinite(p.grad).all() for p in params)
    write(ROOT / "preflight.json", {"updates": 0, "first_Q4_packet_equal": True, "loss": float(probe.detach()),
                                    "peak_reserved_MiB": torch.cuda.max_memory_reserved() / 2**20,
                                    "GPU": torch.cuda.get_device_name(0)})
    del probe
    course = Course(model.tokenizer)
    elapsed = 0.0
    step = 0
    losses = []
    checkpoints = []
    while elapsed < TARGET_SECONDS:
        iteration = time.monotonic()
        step += 1
        factor = min(1.0, step / 50) * (0.30 + 0.70 * (1.0 + math.cos(math.pi * elapsed / TARGET_SECONDS)) / 2)
        optimizer.param_groups[0]["lr"] = 1e-5 * factor
        optimizer.zero_grad(set_to_none=True)
        total = 0.0
        for batch in course.step("cuda:0"):
            with parametrize.cached():
                value = loss(model, batch, head)
            (value / (BATCH // MICRO)).backward()
            total += float(value.detach()) / (BATCH // MICRO)
        torch.nn.utils.clip_grad_norm_(params, 1.0, error_if_nonfinite=True)
        optimizer.step()
        torch.cuda.synchronize()
        elapsed += time.monotonic() - iteration
        losses.append(total)
        if step == 1 or step % 25 == 0:
            status("training", step=step, seconds=round(elapsed, 1), target_seconds=TARGET_SECONDS,
                   loss=round(sum(losses[-25:]) / len(losses[-25:]), 6),
                   peak_reserved_MiB=torch.cuda.max_memory_reserved() / 2**20)
        if len(checkpoints) < len(SECTIONS) and elapsed >= SECTIONS[len(checkpoints)]:
            assert frozen_digest(model) == before
            checkpoint = save_checkpoint(model, step, elapsed, f"{SECTIONS[len(checkpoints)] // 60}m")
            checkpoints.append(str(checkpoint.relative_to(ROOT)))
    assert frozen_digest(model) == before and check_inputs() == frozen
    assert len(checkpoints) == len(SECTIONS)
    write(ROOT / "training.json", {"optimizer_updates": step, "update_elapsed_seconds": elapsed,
                                  "wall_seconds": time.monotonic() - start, "checkpoints": checkpoints,
                                  "trainable_parameters": 317440, "counts": dict(course.counts),
                                  "unique_rows_seen": {k: len(v) for k, v in course.coverage.items()},
                                  "peak_reserved_MiB": torch.cuda.max_memory_reserved() / 2**20,
                                  "Q4_every_forward": True, "frozen_base_verified": True, "GPU": torch.cuda.get_device_name(0)})
    status("complete", optimizer_updates=step, seconds=elapsed)


if __name__ == "__main__":
    run()
