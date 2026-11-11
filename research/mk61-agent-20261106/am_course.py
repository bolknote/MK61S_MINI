"""Separate semantic teaching, error kinds, weighted edits, and safe retention."""
import collections
import difflib
import hashlib
import json
import random
import torch
import torch.nn.functional as F
from am_common import ROOT, ACTIONS, read
from am_model import action_weight, correct_weight
from am_runtime import bounded_render
from ac_course import encoded, pad
from ha_protocol import bytes_text
from al_course import retention


def loss(model, batch, head, policy):
    ids, mask, targets, positions, actions, truth, meaning, errors, sft, token_weights = batch
    h = model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state
    last = h[torch.arange(len(ids),device=ids.device),positions]
    acts = F.linear(last,action_weight(model)).float(); semantic = F.linear(last,correct_weight(model)).float()
    action = F.cross_entropy(acts[sft],actions[sft]); known = truth >= 0
    classification = F.cross_entropy(semantic[known],truth[known],weight=torch.tensor([policy['wrong_class_weight'],1.],device=ids.device))
    valid = targets[:,1:] != -100; coordinates = valid.nonzero(); sums = torch.zeros(len(ids),device=ids.device); denom = torch.zeros_like(sums)
    if valid.any():
        mapping = torch.full((len(model.get_input_embeddings().weight),),-100,dtype=torch.long,device=ids.device);mapping[head] = torch.arange(len(head),device=ids.device)
        local = mapping[targets[:,1:][valid]]; assert (local >= 0).all()
        logs = F.linear(h[:,:-1][valid],model.get_input_embeddings().weight[head]).float().log_softmax(-1).gather(1,local[:,None]).flatten()
        weights = token_weights[:,1:][valid]; sums.scatter_add_(0,coordinates[:,0],logs*weights);denom.scatter_add_(0,coordinates[:,0],weights)
    body = -(sums/denom.clamp_min(1)).mean()
    mk = meaning[:,0] >= 0
    op = F.cross_entropy(model.op_head(last[mk]).float(),meaning[mk,0]) if mk.any() else last.sum()*0
    bind = F.cross_entropy(model.binding_head(last[mk]).float(),meaning[mk,1]) if mk.any() else last.sum()*0
    ek = errors >= 0
    diagnose = F.cross_entropy(model.error_head(last[ek]).float(),errors[ek]) if ek.any() else last.sum()*0
    bad = truth == 0; others = [i for i,a in enumerate(ACTIONS)if a!='done']
    risk = (acts[bad].logsumexp(-1)-acts[bad][:,others].logsumexp(-1)).mean() if bad.any() else last.sum()*0
    value = action+policy['body_weight']*body+policy['semantic_weight']*classification
    value += policy['meaning_weight']*(op+bind)+policy['error_kind_weight']*diagnose+policy['risk_weight']*risk
    return value,{'action':float(action.detach()),'body':float(body.detach()),'semantic':float(classification.detach()),
        'operation':float(op.detach()),'argument':float(bind.detach()),'error_kind':float(diagnose.detach()),'wrong_DONE_risk':float(risk.detach())}


class Course:
    def __init__(self, tokenizer, arm):
        self.tokenizer = tokenizer; self.arm = arm; self.rng = random.Random(151601)
        self.policy = json.loads((ROOT/'policy.json').read_text()); self.plans = {}; self.digest = '00'*32; self.counts = collections.Counter()
        self.rows = {name:read(ROOT/file)for name,file in [('goal','goals.jsonl'),('code','code-reading.jsonl'),
            ('tool','tool-lessons.jsonl'),('retention','retention.jsonl')]}
        self.pools = {}
        for source, rows in self.rows.items():
            self.pools[source] = collections.defaultdict(list)
            for i,r in enumerate(rows):
                if len(encoded(tokenizer,r)[0]) <= 1024:self.pools[source][r['action']].append(i)
        self.available = {s:[i for group in p.values()for i in group]for s,p in self.pools.items()}
        assert all(self.available.values())

    def draw(self, source, action=None):
        pool = self.pools[source][action] if action else self.available[source]
        if not pool: pool = self.available[source]
        i = self.rng.choice(pool); self.counts['draw:'+source+':'+self.rows[source][i]['action']] += 1
        return i,self.rows[source][i]

    def encoding(self,r,stage):
        if self.arm=='planned'and stage==2 and r.get('goal_key')in self.plans:
            r = {**r,'prompt':bounded_render(self.tokenizer,r['state'],self.plans[r['goal_key']])}
        enc = encoded(self.tokenizer,r)
        if len(enc[0]) > 1024 and r.get('state'):
            enc = encoded(self.tokenizer,{**r,'prompt':bounded_render(self.tokenizer,r['state'])})
        assert len(enc[0]) <= 1024
        weights = [1.]*len(enc[0]); body = [x for x in enc[1]if x!=-100]
        if r.get('before_body')and r['action']=='write'and body:
            old = self.tokenizer.encode(bytes_text(r['before_body']),add_special_tokens=False)
            start = len(enc[0])-len(body)
            for tag,i,j,a,b in difflib.SequenceMatcher(a=old,b=body[:-1],autojunk=False).get_opcodes():
                if tag!='equal':
                    for k in range(a,max(a+1,b)):
                        if k<len(body):weights[start+k] = self.policy['changed_token_weight']
        return enc,weights

    def batch(self,step,device):
        stage = 1 if step <= self.policy['warmup_stage_steps']else 2; spec = self.policy['stage'+str(stage)]
        rows = []; chosen = []; draws = []
        for source,n in spec.items():
            schedule = ['write']*8+['done']*8+['run']*4+['trace']*2+['unsure']*2
            for j in range(n):
                action = schedule[j] if source=='tool'and n==24 else ['write','write','done','done','run','trace','unsure','write'][j%8] if source in ['tool','retention']else None
                i,r = self.draw(source,action); rows.append(r); draws.append([source,i]); chosen.append(source)
        encodings = []; weights = []
        for r in rows:
            e,w = self.encoding(r,stage); encodings.append(e);weights.append(w)
        batch = pad(self.tokenizer,encodings,device); width = batch[0].shape[1]
        token_weights = torch.ones_like(batch[0],dtype=torch.float32)
        for i,w in enumerate(weights):token_weights[i,:len(w)] = torch.tensor(w,device=device)
        truth = [r.get('correctness',-1)if s in ['tool','retention']else -1 for s,r in zip(chosen,rows)]
        meaning = [r.get('meaning',[-1,-1])for r in rows]; errors = [r.get('error_kind',-1)for r in rows]
        sft = [s not in ['code','goal']for s in chosen]; anchors = []
        for act in ['write','write','write','done','done','done','run','trace']:
            i,r = self.draw('retention',act);anchors.append(encoded(self.tokenizer,r));draws.append(['anchor',i])
        self.digest = hashlib.sha256(bytes.fromhex(self.digest)+json.dumps(draws,separators=(',',':')).encode()).hexdigest()
        return (*batch,torch.tensor(truth,device=device),torch.tensor(meaning,device=device),torch.tensor(errors,device=device),
            torch.tensor(sft,dtype=torch.bool,device=device),token_weights),pad(self.tokenizer,anchors,device)
