"""Same lesson draws; restore legacy rendering and align the continuation start."""
import collections
import difflib
import random
from am_course import Course as Parent,loss,retention
from an_runtime import bounded_render
from ac_course import encoded
from ha_protocol import bytes_text


class Course(Parent):
    def __init__(self,tokenizer,arm):
        super().__init__(tokenizer,arm);self.rng=random.Random(151602)
        for source,rows in self.rows.items():
            pools=collections.defaultdict(list)
            for i,r in enumerate(rows):
                p={**r,'prompt':bounded_render(tokenizer,r['state'])}if r.get('state')else r
                if len(encoded(tokenizer,p)[0])<=1024:pools[r['action']].append(i)
            self.pools[source]=pools
        self.available={s:[i for group in p.values()for i in group]for s,p in self.pools.items()}
        assert all(self.available.values())

    def encoding(self,r,stage):
        if r.get('state'):
            plan=self.plans.get(r['goal_key'])if self.arm=='planned'else None
            r={**r,'prompt':bounded_render(self.tokenizer,r['state'],plan)}
        enc=encoded(self.tokenizer,r)
        if len(enc[0])>1024 and r.get('state'):enc=encoded(self.tokenizer,{**r,'prompt':bounded_render(self.tokenizer,r['state'])})
        assert len(enc[0])<=1024
        weights=[1.]*len(enc[0]);body=[x for x in enc[1]if x!=-100]
        if r.get('before_body')and r['action']=='write'and body:
            old=self.tokenizer.encode(bytes_text(r['before_body']),add_special_tokens=False);start=len(enc[0])-len(body)
            for tag,i,j,a,b in difflib.SequenceMatcher(a=old,b=body[:-1],autojunk=False).get_opcodes():
                if tag!='equal':
                    for k in range(a,max(a+1,b)):
                        if k<len(body):weights[start+k]=self.policy['changed_token_weight']
        return enc,weights
