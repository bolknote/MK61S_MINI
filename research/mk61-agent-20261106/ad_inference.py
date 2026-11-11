"""Frozen local Q4 inference and reproducible, shared four-candidate banks."""
import hashlib
import json
import time
from pathlib import Path
import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM,AutoTokenizer,LogitsProcessorList
from ad_common import ROOT,MODEL,PREVIOUS,write
from ac_common import ACTION_ID,END,body_ids,output_ids,compact_head
from ac_protocol import prompt_ids,header_ids,decode
from ac_eval import generate as original_generate
from ab_eval import BodyGrammar
from ac_course import encoded,pad,scores
from lowbit import load


def key(text):return hashlib.sha256(text.encode()).hexdigest()


class IndependentSampling:
    """Each prompt has its own RNG stream, independent of batching and other arms."""
    def __init__(self,prompts,index,start):
        self.start=start;self.generators=[]
        for prompt in prompts:
            seed=int(key(f'ad-v1:{index}:'+prompt)[:15],16)
            self.generators.append(torch.Generator(device='cpu').manual_seed(seed))

    def __call__(self,ids,logits):
        out=torch.full_like(logits,-float('inf'))
        for i,g in enumerate(self.generators):
            if END in ids[i,self.start:].tolist():token=END
            else:
                values,order=torch.sort(logits[i].float()/.8,descending=True);p=values.softmax(-1)
                p[(p.cumsum(0)-p)>.95]=0;p/=p.sum()
                token=int(order[torch.multinomial(p.cpu(),1,generator=g)])
            out[i,token]=0
        return out


class Bank:
    def __init__(self,batch=16):
        torch.set_num_threads(4);torch.manual_seed(1071123)
        self.tokenizer=AutoTokenizer.from_pretrained(MODEL/'hf',local_files_only=True)
        self.model=AutoModelForCausalLM.from_pretrained(MODEL/'hf',local_files_only=True);load(self.model,MODEL/'model.mkqb');self.model.eval()
        compact_head(self.model,output_ids(self.tokenizer));self.batch=batch
        self.cache=ROOT/'cache';self.cache.mkdir(exist_ok=True);self.actual={'policy_prompts':0,'sampled_writes':0,'model_seconds':0.}

    def writes(self,prompts,index):
        rows=[None]*len(prompts);prefixes=[prompt_ids(self.tokenizer,p)+header_ids(self.tokenizer,'write')for p in prompts]
        valid=[i for i,p in enumerate(prefixes)if len(p)<1024]
        for i in set(range(len(rows)))-set(valid):rows[i]={'action':None,'body':[],'codec_error':'context_overflow','generated_token_ids':[]}
        if not valid:return rows
        length=max(len(prefixes[i])for i in valid);values=torch.zeros((len(valid),length),dtype=torch.long);attention=torch.zeros_like(values)
        for j,i in enumerate(valid):p=prefixes[i];values[j,-len(p):]=torch.tensor(p);attention[j,-len(p):]=1
        processors=[BodyGrammar(self.tokenizer,length,'write')]
        if index:processors.append(IndependentSampling([prompts[i]for i in valid],index,length))
        with torch.inference_mode():
            out=self.model.generate(input_ids=values,attention_mask=attention,max_new_tokens=min(511,1024-length),
               do_sample=False,use_cache=True,pad_token_id=0,eos_token_id=END,logits_processor=LogitsProcessorList(processors))
        for j,i in enumerate(valid):
            tail=out[j,length:].tolist();ended=END in tail
            if ended:tail=tail[:tail.index(END)]
            tokens=[ACTION_ID['write'],*tail]
            if not ended and len(prompts)>1 and len(prefixes[i])<length:
                rows[i]=self.writes([prompts[i]],index)[0];continue
            try:
                if not ended:raise ValueError('incomplete')
                action,body=decode(self.tokenizer,tokens);error=None
            except ValueError as error_:action=None;body=[];error=str(error_)
            rows[i]={'action':action,'body':body,'codec_error':error,'generated_token_ids':tokens,'input_tokens':len(prefixes[i])}
        return rows

    def actions(self,prompts):
        result=[None]*len(prompts);missing=[]
        for i,prompt in enumerate(prompts):
            path=self.cache/('action-'+key(prompt)+'.json')
            if path.exists():result[i]=json.loads(path.read_text())
            else:missing.append(i)
        for at in range(0,len(missing),self.batch):
            indexes=missing[at:at+self.batch];texts=[prompts[i]for i in indexes];started=time.monotonic()
            rows=original_generate(self.model,self.tokenizer,texts)
            for j,(i,row)in enumerate(zip(indexes,rows)):
                if row.get('codec_error')=='incomplete'and row['generated_token_ids'][:1]==[ACTION_ID['write']]:row=self.writes([texts[j]],0)[0]
                result[i]=row;write(self.cache/('action-'+key(prompts[i])+'.json'),row)
            self.actual['policy_prompts']+=len(indexes);self.actual['model_seconds']+=time.monotonic()-started
        return result

    def likelihood(self,prompts,rows):
        valid=[i for i,r in enumerate(rows)if r.get('action')=='write'and not r.get('codec_error')]
        for row in rows:row['mean_body_logprob']=-1e9
        head=torch.tensor(body_ids(self.tokenizer))
        for at in range(0,len(valid),self.batch):
            indexes=valid[at:at+self.batch];items=[encoded(self.tokenizer,{'prompt':prompts[i],'action':'write','body':rows[i]['body']})for i in indexes]
            batch=pad(self.tokenizer,items,'cpu')
            with torch.inference_mode():a,b,n=scores(self.model,batch,head)
            for i,value in zip(indexes,(b/n.clamp_min(1)).tolist()):rows[i]['mean_body_logprob']=value
        return rows

    def candidates(self,prompts,greedy=None):
        results=[None]*len(prompts);missing=[]
        for i,prompt in enumerate(prompts):
            path=self.cache/('bank-'+key(prompt)+'.json')
            if path.exists():results[i]=json.loads(path.read_text())
            else:missing.append(i)
        if greedy is None:greedy=self.actions(prompts)
        for at in range(0,len(missing),self.batch):
            indexes=missing[at:at+self.batch];texts=[prompts[i]for i in indexes];started=time.monotonic();columns=[]
            first=[greedy[i]if greedy[i].get('action')=='write'else None for i in indexes]
            needed=[j for j,r in enumerate(first)if r is None]
            if needed:
                values=self.writes([texts[j]for j in needed],0)
                for j,row in zip(needed,values):first[j]=row
            columns.append(self.likelihood(texts,first))
            for number in range(1,4):columns.append(self.likelihood(texts,self.writes(texts,number)))
            for j,i in enumerate(indexes):
                bank=[column[j]for column in columns];results[i]=bank;write(self.cache/('bank-'+key(prompts[i])+'.json'),bank)
            self.actual['sampled_writes']+=3*len(indexes);self.actual['model_seconds']+=time.monotonic()-started
        return results

    def compiler(self,tasks):
        from hf_runtime import prompt
        from hf_eval import generate
        from ha_protocol import parse_call
        folder=PREVIOUS/'export/compiler';model=AutoModelForCausalLM.from_pretrained(folder/'hf',local_files_only=True)
        load(model,folder/'model.mkqb');model.eval();compact_head(model,json.loads((folder/'output-token-ids.json').read_text()))
        result=[]
        for at in range(0,len(tasks),self.batch):
            rows=generate(model,self.tokenizer,[prompt(t)for t in tasks[at:at+self.batch]])
            for row in rows:
                try:a,b=parse_call(row['reply']);row.update(action=a,body=b)
                except ValueError:row.update(action=None,body=[])
                result.append(row)
        return result
