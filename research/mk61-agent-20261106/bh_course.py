"""Matched ordinary-language draws, with enough replay to preserve existing skills."""
import collections
import hashlib
import json
import random
import torch
from bh_common import ROOT,read,rows
from ay_course import encoded
from aq_course import pad
from bc_pools import lesson_layout
from be_course import loss

class Course:
    def __init__(self,tokenizer):
        self.tokenizer=tokenizer;self.rows=rows(ROOT/'lessons.jsonl');self.rng=random.Random(read(ROOT/'policy.json')['data_seed'])
        self.pools=collections.defaultdict(list);self.counts=collections.Counter();self.digest='00'*32
        for i in read(ROOT/'valid-ids.json'):self.pools[self.rows[i]['origin']].append(i)
        pairs=collections.defaultdict(dict)
        for i in read(ROOT/'valid-ids.json'):
            r=self.rows[i]
            if r['origin']in ['pair_good','pair_bad']:pairs[r['pair_id']][r['origin']]=i
        self.pairs=[p for p in pairs.values()if len(p)==2]
        assert self.pairs and all(self.pools[k]for k in ['natural','structured','replay_repair','replay_run_0','replay_run_1','replay_done','replay_unsure'])
    def draw(self,ids,mode,step,slot,salt_override=None):
        for attempt in range(40):
            i=self.rng.choice(ids);salt=f'{step}:{slot}:{attempt}:{self.rng.randrange(2**63)}'
            salt=salt_override or salt
            row=lesson_layout(self.rows[i],mode,salt);value=encoded(self.tokenizer,row,'spec')
            if len(value[0])>1000:continue
            self.counts[row['origin']]+=1;self.counts['layout_'+mode]+=1
            if row['origin']=='natural':self.counts['natural_source_'+row['wording_source']]+=1
            self.digest=hashlib.sha256(bytes.fromhex(self.digest)+json.dumps([i,mode,salt],separators=(',',':')).encode()).hexdigest()
            return value
        raise RuntimeError('Cannot draw a bounded natural lesson')
    def batch(self,step,device):
        values=[];flags=[]
        for kind,n in [('natural',3),('structured',1)]:
            for _ in range(n):
                i=self.rng.choice(self.pools[kind])
                for mode in [self.rng.choice(['default','extras']),self.rng.choice(['full','distractors'])]:
                    values.append(self.draw([i],mode,step,len(values)));flags.append(False)
        for slot in range(8):
            for attempt in range(40):
                pair=self.rng.choice(self.pairs);mode=self.rng.choice(['default','extras','full','distractors']);salt=f'paired:{step}:{slot}:{self.rng.randrange(2**63)}'
                if all(len(encoded(self.tokenizer,lesson_layout(self.rows[pair[k]],mode,salt),'spec')[0])<=1000 for k in ['pair_good','pair_bad']):break
            else:raise RuntimeError('No bounded matched pair')
            for kind in ['pair_good','pair_bad']:
                values.append(self.draw([pair[kind]],mode,step,len(values),salt));flags.append(True)
        for kind in ['replay_repair']*4+['replay_run_'+str(step%2)]*2+['replay_done','replay_unsure']:
            values.append(self.draw(self.pools[kind],self.rng.choice(['default','extras','full','distractors']),step,len(values)));flags.append(True)
        order=list(range(32));self.rng.shuffle(order)
        return (*pad([values[i]for i in order],device),torch.tensor([flags[i]for i in order],device=device))
