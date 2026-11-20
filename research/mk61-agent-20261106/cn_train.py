"""Distill verified DeepSeek action targets into the Q4 executor adapter."""

from collections import Counter, defaultdict
import math
import random
import time
from unittest.mock import patch

import torch
import torch.nn.functional as F
from torch.nn.utils import parametrize

import bu_model
import ck_train
from aq_course import pad
from aq_protocol import ACTIONS
from ay_common import read, rows, sha, write
from be_course import loss
from ck_train import CURRENT, REPO
from cn_data import REVIEW_GROUPS, ROOT, SEED, tokenized
from cn_runtime import CONTEXT
from native_export import packet


MILESTONES = (300, 900)
BATCH = 24
MICRO = 6
LR = 2.5e-5


def check_inputs():
    manifest = read(ROOT / "inputs-frozen.json")
    for name, digest in manifest["files"].items():
        assert sha(REPO / name) == digest, name
    return manifest


class Course:
    def __init__(self):
        self.rng = random.Random(SEED)
        self.counts = Counter()
        self.bank = defaultdict(list)
        for source, path in (("teacher", "teacher-lessons.jsonl"), ("replay", "replay-lessons.jsonl")):
            seen = set()
            for row in rows(ROOT / path):
                text = row["short"] if row["short"] is not None else row["full"]
                group = row["group"]
                if (group, text) in seen:
                    continue
                seen.add((group, text))
                x, y, at = tokenized(text, row["action"], row["body"])
                assert len(x) <= CONTEXT
                self.bank[source, group].append((x, y, at, ACTIONS.index(row["action"])))
        assert all(self.bank[source, key] for source in ("teacher", "replay") for key in REVIEW_GROUPS)
        assert all(self.bank["replay", key] for key in ("old_done", "old_write", "old_run", "old_diag"))

    def sample(self, source, group, count):
        self.counts[f"{source}/{group}"] += count
        return self.rng.choices(self.bank[source, group], k=count)

    def batches(self, device):
        values = []
        for group, teacher, replay in (
            ("repair", 4, 3), ("keep", 3, 1), ("bad_spec_good_code", 2, 1),
            ("bad_spec_bad_code", 2, 1), ("run_missing", 2, 1),
        ):
            values.extend(self.sample("teacher", group, teacher))
            values.extend(self.sample("replay", group, replay))
        for group in ("old_done", "old_write", "old_run", "old_diag"):
            values.extend(self.sample("replay", group, 1))
        assert len(values) == BATCH
        self.rng.shuffle(values)
        for start in range(0, BATCH, MICRO):
            batch = pad(values[start:start + MICRO], device)
            mask = torch.ones(MICRO, device=device, dtype=torch.bool)
            yield (*batch, mask)


def new_actor(device):
    parent = CURRENT / "working"
    with patch.object(bu_model, "SOURCE", parent):
        return bu_model.Translator(device)


def verify_initial(actor):
    initial = ROOT / "initial.mkqb"
    actor.packed(initial)
    header, payload = packet(initial)
    baseline, expected = packet(CURRENT / "working/model.mkqb")
    for config in (header["config"], baseline["config"]):
        for name in ("transformers_version", "_name_or_path"):
            config.pop(name, None)
    # Packet metadata can differ by exporter. The tensor layout and all bytes
    # must be identical for the adapter's zero-update state.
    assert header["tensors"] == baseline["tensors"] and payload == expected
    assert header["mode"] == baseline["mode"] == "q4"


def train():
    torch.set_num_threads(3)
    torch.manual_seed(SEED)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    device = "cuda:0"
    torch.cuda.set_device(0)
    torch.cuda.set_per_process_memory_fraction(2**31 / torch.cuda.get_device_properties(0).total_memory)
    manifest = check_inputs()
    assert not (ROOT / "training.json").exists()
    actor = new_actor(device)
    verify_initial(actor)
    digest = bu_model.frozen_digest(actor)
    params = [p for p in actor.parameters() if p.requires_grad]
    assert sum(p.numel() for p in params) == 317440
    actor.train()
    head = torch.tensor(bu_model.body_ids(actor.tokenizer), device=device)
    optimizer = torch.optim.AdamW(params, lr=LR, weight_decay=0.001)
    stream = Course()
    losses = []
    start = time.monotonic()
    for step in range(1, MILESTONES[-1] + 1):
        warmup = min(1.0, step / 40)
        cosine = 0.25 + 0.75 * (1 + math.cos(math.pi * step / MILESTONES[-1])) / 2
        optimizer.param_groups[0]["lr"] = LR * warmup * cosine
        optimizer.zero_grad(set_to_none=True)
        total = 0.0
        for batch in stream.batches(device):
            with parametrize.cached():
                if torch.any(batch[2] != -100):
                    value, _ = loss(actor, batch, head)
                else:
                    ids, mask, _, at, actions, _ = batch
                    hidden = actor.model(input_ids=ids, attention_mask=mask, use_cache=False).last_hidden_state
                    logits = F.linear(hidden[torch.arange(len(at), device=device), at], actor.action_weight())
                    value = F.cross_entropy(logits, actions)
            (value / (BATCH // MICRO)).backward()
            total += float(value.detach()) / (BATCH // MICRO)
        torch.nn.utils.clip_grad_norm_(params, 1.0, error_if_nonfinite=True)
        optimizer.step()
        losses.append(total)
        if step == 1 or step % 25 == 0:
            status = {"step": step, "target": MILESTONES[-1], "loss": sum(losses[-25:]) / len(losses[-25:]),
                      "seconds": round(time.monotonic() - start, 1),
                      "peak_reserved_MiB": torch.cuda.max_memory_reserved() / 2**20}
            write(ROOT / "train-status.json", status)
            print(status, flush=True)
        if step in MILESTONES:
            assert bu_model.frozen_digest(actor) == digest
            with patch.object(ck_train, "ROOT", ROOT):
                ck_train.save_checkpoint(actor, step, time.monotonic() - start, f"prompt-distill-{step}")
    assert check_inputs() == manifest
    write(ROOT / "training.json", {"optimizer_updates": step, "seconds": time.monotonic() - start,
                                  "trainable_parameters": 317440, "frozen_tensors_sha256": digest,
                                  "initial_Q4_bytes_verified": True, "counts": stream.counts,
                                  "checkpoints": list(MILESTONES), "peak_reserved_MiB": torch.cuda.max_memory_reserved() / 2**20})


if __name__ == "__main__":
    train()
