"""Balanced 2x2 contrasts, verified recoveries, and safe teacher retention."""
import collections
import hashlib
import json
import random
import torch
import torch.nn.functional as F
from al_common import ROOT, ACTIONS, read
from al_model import action_weight, correct_weight
from ac_course import encoded, pad


def forward(model, batch, head):
    ids, mask, labels, positions, actions = batch[:5]
    hidden = model.model(input_ids=ids, attention_mask=mask, use_cache=False).last_hidden_state
    last = hidden[torch.arange(len(ids), device=ids.device), positions]
    action = F.linear(last, action_weight(model)).float()
    semantic = F.linear(last, correct_weight(model)).float()
    target = labels[:, 1:]; valid = target != -100
    mapping = torch.full((len(model.get_input_embeddings().weight),), -100, device=ids.device, dtype=torch.long)
    mapping[head] = torch.arange(len(head), device=ids.device)
    local = mapping[target[valid]]; assert (local >= 0).all()
    body = F.linear(hidden[:, :-1][valid], model.get_input_embeddings().weight[head]).float() if valid.any() else None
    return action, semantic, body, valid, local


def loss(model, batch, head, policy):
    action, semantic, body, valid, local = forward(model, batch, head)
    actions = batch[4]; truth = batch[5]; nquad = batch[6]
    action_loss = F.cross_entropy(action, actions)
    classification = F.cross_entropy(semantic, truth)
    sums = torch.zeros(len(actions), device=actions.device)
    if body is not None:
        logs = body.log_softmax(-1).gather(1, local[:, None]).flatten()
        sums.scatter_add_(0, valid.nonzero()[:, 0], logs)
    body_loss = -(sums / valid.sum(1).clamp_min(1)).mean()
    margin = (semantic[:4*nquad, 1] - semantic[:4*nquad, 0]).reshape(-1, 4)
    done = ACTIONS.index('done'); others = [i for i in range(5) if i != done]
    odds = (action[:4*nquad, done] - action[:4*nquad, others].logsumexp(-1)).reshape(-1, 4)
    def rank(values):
        # Compare both goals at fixed code, and both codes at fixed goal.
        edges = torch.stack([values[:, 0]-values[:, 1], values[:, 3]-values[:, 2],
            values[:, 0]-values[:, 2], values[:, 3]-values[:, 1]], dim=1)
        return F.softplus(policy['cross_margin'] - edges).mean()
    cross_semantic = rank(margin); cross_action = rank(odds)
    value = action_loss + policy['body_weight']*body_loss + policy['semantic_weight']*classification
    value += policy['cross_weight']*(cross_semantic + .5*cross_action)
    return value, {'action': float(action_loss.detach()), 'body': float(body_loss.detach()),
        'semantic': float(classification.detach()), 'cross_semantic': float(cross_semantic.detach()),
        'cross_DONE': float(cross_action.detach())}


def retention(model, teacher, batch, head, policy):
    with torch.no_grad(): old, _, old_body, old_valid, old_local = forward(teacher, batch, head)
    new, _, new_body, valid, local = forward(model, batch, head)
    assert torch.equal(valid, old_valid) and torch.equal(local, old_local)
    temperature = policy['temperature']
    def kl(a, b):
        if len(a) == 0: return a.sum()*0
        p = (b/temperature).softmax(-1)
        return F.kl_div((a/temperature).log_softmax(-1), p, reduction='batchmean').clamp_min(0)*temperature**2
    safe = old.argmax(-1) == batch[4]
    keep_action = kl(new[safe], old[safe])
    keep_body = new.sum()*0
    if new_body is not None:
        good = old_body.argmax(-1) == local
        keep_body = kl(new_body[good], old_body[good])
    return keep_action + keep_body, {'keep_action': float(keep_action.detach()), 'keep_body': float(keep_body.detach())}


class Course:
    def __init__(self, tokenizer):
        self.tokenizer = tokenizer; self.rng = random.Random(141601)
        self.policy = json.loads((ROOT/'policy.json').read_text()); self.digest = '00'*32; self.counts = collections.Counter()
        self.quads = []
        for q in read(ROOT/'crossed.jsonl'):
            enc = [encoded(tokenizer, r) for r in q['rows']]
            if max(len(x[0]) for x in enc) <= 1024 and max(x[2] for x in enc) < 1015:
                self.quads.append((enc, q))
        self.rows = {}; self.pools = {}
        for name, file in [('hard', 'hard-lessons.jsonl'), ('ordinary', 'lessons.jsonl'), ('retention', 'retention.jsonl')]:
            rows = []; unique = {}; conflicts = set()
            for r in read(ROOT/file):
                if 'correctness' not in r: continue
                key = r['prompt']; label = (r['action'], bool(r['correctness']), tuple(r['body']))
                if key in unique and unique[key][0] != label: conflicts.add(key)
                unique[key] = (label, r)
            for key, (_, r) in unique.items():
                if key in conflicts: continue
                enc = encoded(tokenizer, r)
                if len(enc[0]) <= 1024 and enc[2] < 1015: rows.append((enc, r))
            self.rows[name] = rows; self.pools[name] = collections.defaultdict(list)
            for i, (_, r) in enumerate(rows): self.pools[name][r['action']].append(i)
        assert len(self.quads) >= 250 and all(self.rows.values())

    def draw(self, source, action, draws):
        pool = self.pools[source][action]
        if not pool: pool = list(range(len(self.rows[source])))
        i = self.rng.choice(pool); self.counts[source + ':' + self.rows[source][i][1]['action']] += 1
        draws.append([source, i]); return self.rows[source][i]

    def batch(self, step, device):
        encodings = []; truth = []; draws = []; n = self.policy['crossed_groups_per_batch']
        for _ in range(n):
            i = self.rng.randrange(len(self.quads)); enc, q = self.quads[i]
            encodings += enc; truth += q['truth']; draws.append(['quad', i]); self.counts['crossed:'+q['family']] += 1
        quotas = [('write', 3), ('done', 2), ('run', 1), ('trace', 1), ('unsure', 1)]
        for source in ['hard', 'retention', 'ordinary']:
            for action, count in quotas:
                for _ in range(count):
                    enc, r = self.draw(source, action, draws); encodings.append(enc); truth.append(r['correctness'])
        anchors = []
        for action, count in [('write', 3), ('done', 3), ('run', 1), ('trace', 1)]:
            for _ in range(count): anchors.append(self.draw('retention', action, draws)[0])
        self.digest = hashlib.sha256(bytes.fromhex(self.digest)+json.dumps(draws, separators=(',', ':')).encode()).hexdigest()
        return (*pad(self.tokenizer, encodings, device), torch.tensor(truth, device=device), n), pad(self.tokenizer, anchors, device)
