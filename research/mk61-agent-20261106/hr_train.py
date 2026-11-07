"""Same corrective curriculum, two learning rates, unchanged ASM protocol."""
from functools import lru_cache
import hashlib
import json
import sys
import torch

import ha_train as base
from hr_common import ROOT,INITIAL,ARMS,HERE,read,sha
from ha_protocol import constants,encode,write_call,prompt
from hr_eval import development,brief,selection


class Course(base.Course):
    def __init__(self,tokenizer):
        super().__init__(tokenizer)
        self.new_hard=[i for i,t in enumerate(self.rows)if t.get('repair_category')=='hard']
        self.new_boundary=[i for i,t in enumerate(self.rows)if t.get('repair_category')=='boundary']
        self.old_composition=[i for i,t in enumerate(self.rows)if t['group']=='composition'and t.get('repair_category')!='hard']
        assert self.new_hard and self.new_boundary

    @lru_cache(maxsize=16000)
    def paired(self,category,index,notes):
        if category=='tool':
            value=self.tools[index]['pair']['asm'];encoded=self.encode_pair(value['prompt'],value['answer'])
        else:
            task=self.rows[index];pool=task.get('constants')or constants(task['task'])
            encoded=self.encode_pair(prompt(task,'asm'),write_call(encode(task['reference_code'],pool,'asm')))
        return {arm:encoded for arm in ARMS}

    def batch(self,arm,step,device):
        rng=self.rng;rows=[];lm=[];draws=[]
        for category,total in [('hard',72),('boundary',24),('primitive',12),('algorithm',8),('tool',8)]:
            count=0
            while count<total:
                if category=='hard':
                    choice=rng.random();index=rng.choice(self.new_hard if choice<.6 else self.pools['legacy']if choice<.8 else self.old_composition)
                elif category=='boundary':index=rng.choice(self.new_boundary if rng.random()<.85 else self.pools['basic'])
                elif category=='primitive':
                    op=rng.choice(self.documented if rng.random()<.95 else self.other);index=rng.choice(self.primitives[op])
                elif category=='algorithm':index=rng.choice(self.pools['algorithm'])
                else:
                    kind=rng.choices(['inspect','repair','verify','done'],weights=[.25,.35,.2,.2])[0];index=rng.choice(self.tool_pools[kind])
                pair=self.paired(category,index,'')
                if len(pair[arm][0])>1024:self.counts['resampled_overlength_both']+=1;continue
                rows.append(pair[arm]);lm.append(False);draws.append([category,index]);count+=1;self.counts[category]+=1
                if category=='primitive':self.counts[f'opcode:{op:02X}']+=1
        for _ in range(4):
            if rng.random()<.5:
                index=rng.randrange(len(self.domain));source=self.domain[index];start=rng.randrange(max(1,len(source)-511));ids=source[start:start+512];draws.append(['domain',index,start])
            else:
                start=rng.randrange(len(self.stream)-513);ids=self.stream[start:start+512].astype('int64').tolist();draws.append(['language',start])
            rows.append((ids,ids));lm.append(True);self.counts['language']+=1
        order=list(range(128));rng.shuffle(order);rows=[rows[i]for i in order];lm=[lm[i]for i in order]
        self.digest=hashlib.sha256(bytes.fromhex(self.digest)+json.dumps([step,draws,order],separators=(',',':')).encode()).hexdigest()
        length=max(len(x)for x,y in rows);ids=torch.full((128,length),self.tokenizer.pad_token_id or 0,dtype=torch.long);labels=torch.full_like(ids,-100);mask=torch.zeros_like(ids)
        for i,(x,y)in enumerate(rows):ids[i,:len(x)]=torch.tensor(x);labels[i,:len(y)]=torch.tensor(y);mask[i,:len(x)]=1
        return ids.to(device),mask.to(device),labels.to(device),torch.tensor(lm,dtype=torch.bool,device=device)


def configure():
    base.ROOT=ROOT;base.INITIAL=INITIAL;base.ARMS=ARMS;base.Course=Course
    base.development=development;base.brief=brief;base.selection=selection


def main():
    configure();strategy=sys.argv[sys.argv.index('--arm')+1]
    policy=json.loads((ROOT/'policy.json').read_text());scale=policy['learning_rate_scale'][strategy]
    original=torch.optim.AdamW
    def scaled(params,*args,**kwargs):
        optimizer=original(params,*args,**kwargs)
        for group in optimizer.param_groups:group['factor']*=scale
        return optimizer
    torch.optim.AdamW=scaled
    base.main()


if __name__=='__main__':main()

