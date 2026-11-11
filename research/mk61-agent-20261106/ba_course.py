"""On-the-fly paired permutations; the input protocol and CE remain unchanged."""
import collections
import hashlib
import json
import random
import torch
from ba_common import ROOT,rows,read
from ba_pools import lesson_layout
from ay_course import encoded,loss
from aq_course import pad


class Course:
    def __init__(self,tokenizer,run):
        self.tokenizer=tokenizer;self.run=run;self.rows=rows(ROOT/'lessons.jsonl');self.policy=read(ROOT/'policy.json')
        self.rng=random.Random(self.policy['seeds'][run]);self.counts=collections.Counter();self.digest='00'*32;self.pools={}
        for i in read(ROOT/'valid-ids.json'):
            r=self.rows[i];self.pools.setdefault(r['origin'],[]).append(i)
        self.binding=[i for i in self.pools['goal']if self.rows[i]['family']=='binding']
        self.nonbinding=[i for i in self.pools['goal']if self.rows[i]['family']!='binding']
        self.priority_repair=[i for i in self.pools['repair']if self.rows[i].get('curriculum')in ['parent_mining','retired_actual_false_DONE','matched_program_contrast']]
        self.hard_done=[i for i in self.pools['done']if self.rows[i].get('curriculum')in ['parent_mining','matched_program_contrast']]
        self.run_pools={c:[i for i in self.pools['run']if self.rows[i]['body']==[c]]for c in [0,1]}
        assert self.binding and self.priority_repair and self.hard_done and all(self.run_pools.values())

    def draw(self,pool,mode,step,slot):
        for attempt in range(40):
            index=self.rng.choice(pool);salt=f'{self.run}:{step}:{slot}:{attempt}:{self.rng.randrange(2**63)}'
            row=lesson_layout(self.rows[index],mode,salt);value=encoded(self.tokenizer,row,'spec')
            if len(value[0])>1024:self.counts['overlength_resamples']+=1;continue
            self.counts[row['origin']]+=1;self.counts['layout_'+mode]+=1
            if row['origin']=='run':self.counts['RUN_'+str(row['body'][0])]+=1
            self.digest=hashlib.sha256(bytes.fromhex(self.digest)+json.dumps([index,mode,salt],separators=(',',':')).encode()).hexdigest()
            return value
        raise RuntimeError('Cannot draw a bounded lesson')

    def pair(self,pool,step,slot):
        # Keep one logical example fixed while changing its table twice.
        index=self.rng.choice(pool);p=[index];first=self.rng.choice(['default','extras']);second=self.rng.choice(['full','distractors'])
        return [self.draw(p,first,step,slot),self.draw(p,second,step,slot+1)]

    def batch(self,step,device):
        batch=[]
        if step<=self.policy['binding_steps']:
            for pool,n in [(self.binding,6),(self.nonbinding,6),(self.priority_repair,2)]:
                for _ in range(n):batch+=self.pair(pool,step,len(batch))
            for case in [0,1]:batch.append(self.draw(self.run_pools[case],self.rng.choice(['default','full']),step,len(batch)))
            for _ in range(2):batch.append(self.draw(self.pools['done'],'default',step,len(batch)))
        else:
            for i in range(6):batch+=self.pair(self.binding if i==0 else self.nonbinding,step,len(batch))
            for i in range(4):batch+=self.pair(self.priority_repair if i%2==0 else self.pools['repair'],step,len(batch))
            for case in [0,1]:
                for _ in range(2):batch.append(self.draw(self.run_pools[case],self.rng.choice(['default','extras','full','distractors']),step,len(batch)))
            for origin in ['done','unsure']:
                for i in range(4):batch.append(self.draw(self.hard_done if origin=='done'and i<2 else self.pools[origin],self.rng.choice(['default','extras','full','distractors']),step,len(batch)))
        assert len(batch)==32;self.rng.shuffle(batch)
        return pad(batch,device)
