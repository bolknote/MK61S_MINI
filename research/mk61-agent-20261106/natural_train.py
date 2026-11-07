"""Continue full-ISA training while making ordinary requests half the batch."""
import collections
import hashlib
import json
from pathlib import Path

import torch

import full_isa_train as training
from natural_common import ROOT,INITIAL,sha,write
from natural_eval import development,brief,selection


class Course(training.Course):
    def __init__(self,tokenizer):
        super().__init__(tokenizer)
        self.repairs=training.read(ROOT/'fresh-repair-examples.jsonl')

    def batch(self,context,step,device):
        rng=self.rng;rows=[];lm=[];draws=[]
        quotas=[('natural_request',64),('legacy',24),('primitive',20),('programming',8),('tools',4),('interactive_game',2)]
        for category,n in quotas:
            count=0
            while count<n:
                kind=rng.choices(['repair','trace','done'],weights=[.6,.2,.2])[0]if category=='tools'else category
                index=self.pick(kind);salt=rng.randrange(32);x,y=self.pair(index,kind,context,salt)
                if len(x)>context:self.counts['resampled_overlength']+=1;continue
                rows.append((x,y));lm.append(False);draws.append([kind,index,context,salt]);count+=1
                self.counts['kind:'+kind]+=1
                if category not in ['tools','legacy']:
                    row=self.rows[index];self.counts['group:'+row['group']]+=1
                    if row.get('opcode')is not None:self.counts[f'opcode:{row["opcode"]:02X}']+=1
        for _ in range(3):
            if rng.random()<.5:
                index=rng.randrange(len(self.domain));source=self.domain[index];start=rng.randrange(max(1,len(source)-511));ids=source[start:start+512];draws.append(['domain',index,start])
            else:
                start=rng.randrange(len(self.stream)-513);ids=self.stream[start:start+512].astype('int64').tolist();draws.append(['language',start])
            rows.append((ids,ids));lm.append(True);self.counts['language']+=1
        count=0
        while count<3:
            index=self.pick('plan');salt=rng.randrange(32);x,y=self.pair(index,'plan',context,salt)
            if len(x)>context:self.counts['resampled_plan']+=1;continue
            rows.append((x,y));lm.append(True);draws.append(['plan',index,context,salt]);self.counts['auxiliary_plan']+=1;count+=1
        assert len(rows)==128
        order=list(range(128));rng.shuffle(order);rows=[rows[i]for i in order];lm=[lm[i]for i in order]
        self.digest=hashlib.sha256(bytes.fromhex(self.digest)+json.dumps([step,context,draws,order],separators=(',',':')).encode()).hexdigest()
        size=max(len(x)for x,y in rows);ids=torch.full((128,size),self.tokenizer.pad_token_id or 0,dtype=torch.long);labels=torch.full_like(ids,-100);mask=torch.zeros_like(ids)
        for i,(x,y)in enumerate(rows):ids[i,:len(x)]=torch.tensor(x);labels[i,:len(y)]=torch.tensor(y);mask[i,:len(x)]=1
        return ids.to(device),mask.to(device),labels.to(device),torch.tensor(lm,dtype=torch.bool,device=device)


def main():
    prepared=json.loads((ROOT/'prepared.json').read_text())
    for name,digest in prepared['natural_source_hashes'].items():assert sha(Path(__file__).parent/name)==digest
    training.ROOT=ROOT;training.INITIAL=INITIAL;training.Course=Course
    training.development=development;training.brief=brief;training.selection=selection
    training.main()


if __name__=='__main__':main()
