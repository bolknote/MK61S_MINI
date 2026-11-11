"""Half retained translation/repair, half diverse fresh cycles; four microbatches."""
import collections
import hashlib
import json
import random
import torch
from bs_common import ROOT,read,rows
from bp_course import encoded
from aq_course import pad
from be_course import loss
from ay_data import op_count


class Course:
    def __init__(self,tokenizer):
        self.rows=rows(ROOT/'lessons.jsonl');self.rng=random.Random(read(ROOT/'policy.json')['data_seed'])
        self.pools=collections.defaultdict(list);self.counts=collections.Counter();self.digest='00'*32
        self.cache={}
        for i in read(ROOT/'valid-ids.json'):
            r=self.rows[i]
            self.cache[i]=encoded(tokenizer,r);self.pools[r['origin']].append(i)
            if r['origin']=='old_translate':self.pools['old_translate_'+('composition'if op_count(r['target_spec']['X'])>=3 else'other')].append(i)
        for k in ['old_translate_composition','old_translate_other','fresh_goal','review_keep','review_fix','fresh_done','fresh_write','rejected_write','rejected_good_run','fresh_run','fresh_diag','fresh_unsure','old_done','old_write','old_run']:assert self.pools[k],k

    def draw(self,kind):
        i=self.rng.choice(self.pools[kind]);self.counts[kind]+=1;return i

    def step(self,step,device='cuda'):
        fresh=[['fresh_done','fresh_write'],['fresh_diag','rejected_write'],['fresh_run','rejected_good_run'],['fresh_unsure','fresh_done']]
        old=['old_done','old_write','old_run','old_write'];chunks=[];record=[]
        for j in range(4):
            kinds=['old_translate_composition','old_translate_composition','old_translate_other','fresh_goal',
                   'review_keep'if j%2==0 else'review_fix',old[j],*fresh[j]]
            draw=[self.draw(k)for k in kinds];order=list(range(8));self.rng.shuffle(order)
            flags=[False]*5+[True]*3
            chunks.append((*pad([self.cache[draw[i]]for i in order],device),torch.tensor([flags[i]for i in order],device=device)))
            record.append([draw,order])
        self.digest=hashlib.sha256(bytes.fromhex(self.digest)+json.dumps([step,record],separators=(',',':')).encode()).hexdigest()
        return chunks
