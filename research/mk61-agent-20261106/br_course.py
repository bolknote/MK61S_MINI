"""A finite clean course: identical state draws and full-Q4 training for both depths."""
import collections
import hashlib
import json
import random
import torch
from br_common import ROOT,read,rows
from bp_course import encoded
from aq_course import pad
from be_course import loss


class Course:
    def __init__(self,tokenizer):
        self.rows=rows(ROOT/'lessons.jsonl');self.tokenizer=tokenizer
        self.rng=random.Random(read(ROOT/'policy.json')['data_seed'])
        self.pools=collections.defaultdict(list);self.counts=collections.Counter();self.digest='00'*32
        for i,row in enumerate(self.rows):self.pools[row['origin']].append(i)
        self.cache={i:encoded(tokenizer,r)for i,r in enumerate(self.rows)}

    def batch(self,step,device):
        values=[];flags=[];draws=[]
        mixture=[('goal',4,False),('review_fix',2,False),('review_keep',2,False),
                 ('done',8,True),('write',5,True),('run_0',2,True),('run_1',2,True),('diag',4,True),
                 ('unsure_used_review',2,True),('unsure_budget',1,True)]
        for origin,n,action in mixture:
            for _ in range(n):
                i=self.rng.choice(self.pools[origin]);values.append(self.cache[i]);flags.append(action)
                draws.append(i);self.counts[origin]+=1
        order=list(range(32));self.rng.shuffle(order)
        self.digest=hashlib.sha256(bytes.fromhex(self.digest)+json.dumps([step,draws,order],separators=(',',':')).encode()).hexdigest()
        return (*pad([values[i]for i in order],device),torch.tensor([flags[i]for i in order],device=device))
