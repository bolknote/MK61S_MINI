"""Same separate losses; original tag-prefix context for the body decoder."""
from functools import lru_cache
import torch
import aa_course as base
from aa_course import separate_loss,preference_loss
from ab_common import ROOT,ACTION_IDS,ACTION_ID
from ab_protocol import prompt_ids,header_ids,NO_BODY,END
from ab_runtime import initial_prompt
from ha_protocol import encode,constants,bytes_text

base.ROOT=ROOT


class Course(base.Course):
    @lru_cache(maxsize=30000)
    def pair(self,category,index):
        if category in ['expert','online']:
            row=(self.expert if category=='expert'else self.online)[index]
            text=row['prompt'];action=row['action'];body=row['body']
        else:
            row=self.training[index]if category=='compile'else self.rows[index]
            text=initial_prompt(row);action='write';body=encode(row['reference_code'],row.get('constants')or constants(row['task']),'asm')
        x=prompt_ids(self.tokenizer,text)
        if action in NO_BODY:header=[];y=[]
        else:
            header=header_ids(self.tokenizer,action)
            y=self.tokenizer.encode(bytes_text(body),add_special_tokens=False)+[END]
        return x+header+y,[-100]*(len(x)+len(header))+y,len(x)-1,ACTION_IDS.index(ACTION_ID[action])

    def preferences(self,count,device):
        pairs=[]
        while len(pairs)<count:
            category='online'if self.pref_rng.random()<.6 else'expert'
            values=self.online if category=='online'else self.expert
            row=values[self.pick_lesson(category,self.pref_rng)]
            if row['action']==row['rejected']:continue
            ids=prompt_ids(self.tokenizer,row['prompt'])
            if len(ids)>1024:continue
            pairs.append((ids,ACTION_IDS.index(ACTION_ID[row['action']]),ACTION_IDS.index(ACTION_ID[row['rejected']])))
        length=max(len(x[0])for x in pairs);ids=torch.full((count,length),self.tokenizer.pad_token_id or 0,dtype=torch.long);mask=torch.zeros_like(ids)
        for i,(x,*_)in enumerate(pairs):ids[i,:len(x)]=torch.tensor(x);mask[i,:len(x)]=1
        return tuple(x.to(device)for x in [ids,mask,torch.tensor([x[1]for x in pairs]),torch.tensor([x[2]for x in pairs])])
