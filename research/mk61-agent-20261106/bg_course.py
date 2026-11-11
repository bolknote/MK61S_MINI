"""Matched ordinary-language draws, with enough replay to preserve existing skills."""
import collections
import hashlib
import json
import random
import torch
from bg_common import ROOT,read,rows
from ay_course import encoded
from aq_course import pad
from bc_pools import lesson_layout
from be_course import loss

class Course:
    def __init__(self,tokenizer):
        self.tokenizer=tokenizer;self.rows=rows(ROOT/'lessons.jsonl');self.rng=random.Random(read(ROOT/'policy.json')['data_seed'])
        self.pools=collections.defaultdict(list);self.counts=collections.Counter();self.digest='00'*32
        for i in read(ROOT/'valid-ids.json'):self.pools[self.rows[i]['origin']].append(i)
        self.old=[i for i in self.pools['natural']if self.rows[i]['wording_source']=='old'and not self.rows[i]['point_edited']]
        self.edited=[i for i in self.pools['natural']if self.rows[i]['point_edited']]
        self.simple=[i for i in self.pools['natural']if self.rows[i]['simple']]
        assert self.old and self.edited and all(self.pools[k]for k in ['structured','run_0','run_1','done','repair','unsure'])
    def draw(self,ids,mode,step,slot):
        for attempt in range(40):
            i=self.rng.choice(ids);salt=f'{step}:{slot}:{attempt}:{self.rng.randrange(2**63)}'
            row=lesson_layout(self.rows[i],mode,salt);value=encoded(self.tokenizer,row,'spec')
            if len(value[0])>1000:continue
            self.counts[row['origin']]+=1;self.counts['layout_'+mode]+=1
            if row['origin']=='natural':self.counts['natural_source_'+row['wording_source']]+=1
            self.digest=hashlib.sha256(bytes.fromhex(self.digest)+json.dumps([i,mode,salt],separators=(',',':')).encode()).hexdigest()
            return value
        raise RuntimeError('Cannot draw a bounded natural lesson')
    def batch(self,step,device):
        values=[];flags=[]
        for pool,n in [(self.old,1),(self.edited,1),(self.pools['natural'],3),(self.pools['structured'],1)]:
            for _ in range(n):
                i=self.rng.choice(pool)
                for mode in [self.rng.choice(['default','extras']),self.rng.choice(['full','distractors'])]:
                    values.append(self.draw([i],mode,step,len(values)));flags.append(False)
        for kind in (['run_'+str(step%2)]*4+['done']*8+['repair']*4+['unsure']*4):
            values.append(self.draw(self.pools[kind],self.rng.choice(['default','extras','full','distractors']),step,len(values)));flags.append(True)
        order=list(range(32));self.rng.shuffle(order)
        return (*pad([values[i]for i in order],device),torch.tensor([flags[i]for i in order],device=device))
