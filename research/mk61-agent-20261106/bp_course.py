"""Calibrated own-error prevalence, matched controls, NL and successful replay."""
import collections
import hashlib
import json
import random
import torch
from bp_common import ROOT, rows, read, ACTIONS, END
from bl_runtime import render, direct_prompt
from aq_protocol import prompt_ids, header_ids, NO_BODY
from aq_course import pad
from ha_protocol import bytes_text
from bc_pools import lesson_layout
from be_course import loss


def encoded(tokenizer, row, arm='spec'):
    text, info = direct_prompt(row, tokenizer) if 'raw_prompt' in row else render(row['state'], tokenizer)
    if not info['fits']: raise ValueError('Unfitted compact input')
    x = prompt_ids(tokenizer, text); action = row['action']
    body = row['spec_body'] if action == 'write' else row['body']
    h = [] if action in NO_BODY else header_ids(tokenizer, action)
    y = [] if action in NO_BODY else tokenizer.encode(bytes_text(body), add_special_tokens=False) + [END]
    if len(h) + len(y) > 160: raise ValueError('Oversized SPEC target')
    return x+h+y, [-100]*(len(x)+len(h))+y, len(x)-1, ACTIONS.index(action)


class Course:
    def __init__(self, tokenizer):
        self.tokenizer = tokenizer; self.rows = rows(ROOT / 'lessons.jsonl')
        self.rng = random.Random(read(ROOT / 'policy.json')['data_seed'])
        self.pools = collections.defaultdict(list); self.counts = collections.Counter(); self.digest = '00'*32
        pairs = collections.defaultdict(dict)
        for i in read(ROOT / 'valid-ids.json'):
            r = self.rows[i]; self.pools[r['origin']].append(i)
            if 'contrast_id' in r: pairs[r['contrast_id']][r['origin']] = i
        self.good = [v for v in pairs.values() if all(k in v for k in ['good_spec_good_code','good_spec_bad_code'])]
        self.bad = [v for v in pairs.values() if all(k in v for k in ['own_bad_good_code','own_bad_bad_code'])]
        assert self.good and self.bad

    def draw(self, ids, mode, step, salt=None):
        for attempt in range(80):
            i = self.rng.choice(ids); identity = salt or f'{step}:{self.rng.randrange(2**63)}:{attempt}'
            original = self.rows[i]
            try:
                r = original if 'raw_prompt' in original else lesson_layout(original, mode, identity)
                value = encoded(self.tokenizer, r)
            except (ValueError, ArithmeticError): continue
            self.counts[r['origin']] += 1
            self.digest = hashlib.sha256(bytes.fromhex(self.digest)+json.dumps([i,mode,identity]).encode()).hexdigest()
            return value
        raise RuntimeError(('No bounded compact lesson', self.rows[ids[0]]['origin']))

    def batch(self, step, device):
        values=[]; flags=[]; modes=['default','extras','full','distractors']
        # 8 NL + 4 code-free reviews. Reviews balance correction and preservation.
        for origin, n in [('natural',4),('review_fix',1),('review_keep',1)]:
            for _ in range(n):
                i=self.rng.choice(self.pools[origin])
                for mode in [self.rng.choice(modes[:2]),self.rng.choice(modes[2:])]:
                    values.append(self.draw([i],mode,step));flags.append(False)
        # 12 paired action decisions; wrong SPEC prevalence alternates 1/6 and2/6,
        # The exact row/action mixture is retained from the paired BL experiment.
        nbad=1+step%2
        for bad,n in [(False,6-nbad),(True,nbad)]:
            kinds=['own_bad_good_code','own_bad_bad_code']if bad else['good_spec_good_code','good_spec_bad_code']
            for _ in range(n):
                pair=self.rng.choice(self.bad if bad else self.good); mode=self.rng.choice(modes)
                salt=f'pair:{step}:{self.rng.randrange(2**63)}'
                for kind in kinds:
                    ids=self.pools['own_policy_diag'] if bad and step%3==0 and self.pools['own_policy_diag'] else [pair[kind]]
                    values.append(self.draw(ids,mode,step,salt));flags.append(True)
        # On-policy data and retained successful repairs alternate, with fixed
        # action counts, so easy abstention does not crowd out repair trajectories.
        for slot,kind in enumerate(['replay_repair']*4+['replay_run_'+str(step%2)]*2+['replay_done','budget_unsure']):
            target={'replay_repair':'write','replay_run_0':'run','replay_run_1':'run','replay_done':'done','budget_unsure':'unsure'}[kind]
            origin='own_policy_'+target if (step+slot)%2 and self.pools['own_policy_'+target] else kind
            values.append(self.draw(self.pools[origin],self.rng.choice(modes),step));flags.append(True)
        assert len(values)==32
        order=list(range(32));self.rng.shuffle(order)
        return (*pad([values[i]for i in order],device),torch.tensor([flags[i]for i in order],device=device))
