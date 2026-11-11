"""Target self-check repair versus visible-hypothesis conflict, retaining Q4 skills."""
import collections
import hashlib
import json
import random
from bc_common import ROOT,read,rows
from bc_pools import lesson_layout
from ay_course import encoded,loss
from aq_course import pad

class Course:
    def __init__(self,tokenizer,run):
        self.tokenizer=tokenizer;self.run=run;self.rows=rows(ROOT/'lessons.jsonl');self.policy=read(ROOT/'policy.json')
        self.rng=random.Random(self.policy['seeds'][run]);self.counts=collections.Counter();self.digest='00'*32;self.pools={}
        for i in read(ROOT/'valid-ids.json'):self.pools.setdefault(self.rows[i]['origin'],[]).append(i)
        self.binding=[i for i in self.pools['goal']if self.rows[i]['family']=='binding']
        self.priority=[i for i in self.pools['goal']if self.rows[i].get('curriculum')in ['retired_exam_error','hypothesis_partner','semantic_neighbour','exact_retired_prompt']]
        self.done=self.pools['done']+self.pools['self_done']
        self.run_pools={c:[i for i in self.pools['run']if self.rows[i]['body']==[c]]for c in [0,1]}
        assert self.binding and self.priority and all(self.run_pools.values())and self.pools['conflict_unsure']and self.pools['self_repair']

    def draw(self,pool,mode,step,slot):
        for attempt in range(40):
            i=self.rng.choice(pool);salt=f'{self.run}:{step}:{slot}:{attempt}:{self.rng.randrange(2**63)}'
            row=lesson_layout(self.rows[i],mode,salt);value=encoded(self.tokenizer,row,'spec')
            if len(value[0])>1024:self.counts['overlength_resamples']+=1;continue
            self.counts[row['origin']]+=1;self.counts['layout_'+mode]+=1
            if row['origin']=='run':self.counts['RUN_'+str(row['body'][0])]+=1
            self.digest=hashlib.sha256(bytes.fromhex(self.digest)+json.dumps([i,mode,salt],separators=(',',':')).encode()).hexdigest()
            return value
        raise RuntimeError('Cannot draw bounded lesson')

    def pair(self,pool,step,slot):
        i=self.rng.choice(pool)
        return [self.draw([i],self.rng.choice(['default','extras']),step,slot),self.draw([i],self.rng.choice(['full','distractors']),step,slot+1)]

    def batch(self,step,device):
        values=[]
        for pool,n in [(self.binding,1),(self.priority,2),(self.pools['goal'],2),(self.pools['repair'],2),(self.pools['self_repair'],3)]:
            for _ in range(n):values+=self.pair(pool,step,len(values))
        for case in [0,1]:
            for _ in range(2):values.append(self.draw(self.run_pools[case],self.rng.choice(['default','extras','full','distractors']),step,len(values)))
        for _ in range(4):values.append(self.draw(self.done,self.rng.choice(['default','extras','full','distractors']),step,len(values)))
        for _ in range(3):values.append(self.draw(self.pools['conflict_unsure'],self.rng.choice(['default','extras','full','distractors']),step,len(values)))
        values.append(self.draw(self.pools['unsure'],'default',step,len(values)))
        assert len(values)==32;self.rng.shuffle(values);return pad(values,device)
