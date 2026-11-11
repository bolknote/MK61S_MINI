"""Balanced four-way intent/code contrasts, NL translation, replanning and replay."""
import collections
import hashlib
import json
import random
import torch
from bj_common import ROOT, rows, read
from bj_runtime import render
from ay_course import encoded as original_encoded
from aq_course import pad
from bc_pools import lesson_layout
from be_course import loss
import ay_course


def encoded(tokenizer, row, arm='spec'):
    # The original encoder's only UI dependency is render. Install the same
    # hypothesis display as in actual tool episodes, in this isolated process.
    ay_course.render = render
    return original_encoded(tokenizer, row, arm)


class Course:
    def __init__(self, tokenizer):
        self.tokenizer = tokenizer
        self.rows = rows(ROOT / 'lessons.jsonl')
        self.rng = random.Random(read(ROOT / 'policy.json')['data_seed'])
        self.pools = collections.defaultdict(list)
        self.digest = '00' * 32
        self.counts = collections.Counter()
        pairs = collections.defaultdict(dict)
        for i in read(ROOT / 'valid-ids.json'):
            row = self.rows[i]
            self.pools[row['origin']].append(i)
            if 'contrast_id' in row:
                pairs[row['contrast_id']][row['origin']] = i
        self.kinds = ['good_spec_good_code', 'good_spec_bad_code', 'bad_spec_good_code', 'bad_spec_bad_code']
        self.pairs = [v for v in pairs.values() if all(k in v for k in self.kinds)]
        assert self.pairs

    def draw(self, ids, mode, step, salt=None):
        for attempt in range(60):
            i = self.rng.choice(ids)
            identity = salt or f'{step}:{self.rng.randrange(2**63)}:{attempt}'
            row = lesson_layout(self.rows[i], mode, identity)
            value = encoded(self.tokenizer, row)
            if len(value[0]) > 1000:
                continue
            self.counts[row['origin']] += 1
            self.counts['layout_' + mode] += 1
            self.digest = hashlib.sha256(bytes.fromhex(self.digest) + json.dumps([i, mode, identity]).encode()).hexdigest()
            return value
        raise RuntimeError('No bounded intent lesson')

    def batch(self, step, device):
        values = []; flags = []
        modes = ['default', 'extras', 'full', 'distractors']
        for origin, n in [('natural', 4), ('replan', 2)]:
            for _ in range(n):
                index = self.rng.choice(self.pools[origin])
                for mode in [self.rng.choice(modes[:2]), self.rng.choice(modes[2:])]:
                    values.append(self.draw([index], mode, step)); flags.append(False)
        for _ in range(3):
            for attempt in range(60):
                pair = self.rng.choice(self.pairs); mode = self.rng.choice(modes)
                salt = f'contrast:{step}:{self.rng.randrange(2**63)}'
                if all(len(encoded(self.tokenizer, lesson_layout(self.rows[pair[k]], mode, salt))[0]) <= 1000 for k in self.kinds):
                    break
            else:
                raise RuntimeError('No bounded four-way contrast')
            for kind in self.kinds:
                values.append(self.draw([pair[kind]], mode, step, salt)); flags.append(True)
        for kind in ['replay_repair'] * 4 + ['replay_run_' + str(step % 2)] * 2 + ['replay_done', 'budget_unsure']:
            values.append(self.draw(self.pools[kind], self.rng.choice(modes), step)); flags.append(True)
        assert len(values) == 32
        order = list(range(32)); self.rng.shuffle(order)
        return (*pad([values[i] for i in order], device), torch.tensor([flags[i] for i in order], device=device))
