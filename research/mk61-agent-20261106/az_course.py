"""Identical batches, including equal RUN 00/01 targets in every update."""
import collections
import hashlib
import json
import random
import ay_course as original
from az_common import ROOT
from aq_course import pad

original.ROOT=ROOT
encoded=original.encoded
loss=original.loss


class Course(original.Course):
    def __init__(self,tokenizer,arm):
        super().__init__(tokenizer,arm);self.rng=random.Random(26110824);self.run_pools={}
        for stage in ['simple','all']:
            self.run_pools[stage]={case:[i for i in self.pools[stage]['run']if self.rows[i]['body']==[case]]for case in [0,1]}
            assert all(self.run_pools[stage].values())

    def batch(self,step,device):
        stage='simple'if step<=self.policy['curriculum_steps']else'all';ids=[]
        for origin,n in self.policy['batch_sources'].items():
            if origin=='run':
                assert n%2==0
                for case in [0,1]:ids+=self.rng.choices(self.run_pools[stage][case],k=n//2)
            else:ids+=self.rng.choices(self.pools[stage][origin],k=n)
        self.rng.shuffle(ids);self.digest=hashlib.sha256(bytes.fromhex(self.digest)+json.dumps(ids,separators=(',',':')).encode()).hexdigest()
        for i in ids:
            r=self.rows[i];self.counts[r['origin']]+=1
            if r['origin']=='run':self.counts['RUN_'+str(r['body'][0])]+=1
        return pad([self.encoding(i)for i in ids],device)
