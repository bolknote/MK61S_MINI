"""Paired Q4 students: identical draws, different reversible program formats."""
import argparse
import collections
import fcntl
from functools import lru_cache
import hashlib
import json
import math
import random
import shutil
import time

import numpy as np
import torch
from transformers import AutoModelForCausalLM,AutoTokenizer

from ha_common import ROOT,INITIAL,ARMS,HERE,read,sha,write,allowed,compact_head
from ha_protocol import constants,encode,write_call,prompt
from ha_eval import development,brief,selection
from codec_train import compact_loss
from native_quant import attach,save,packed_copy
from tasks import BUILD


class Course:
    def __init__(self,tokenizer):
        self.tokenizer=tokenizer;self.rng=random.Random(6119211);self.rows=read(ROOT/'sft-light.jsonl');self.tools=read(ROOT/'tool-lessons.jsonl')
        self.pools=collections.defaultdict(list);self.primitives=collections.defaultdict(list);self.tool_pools=collections.defaultdict(list)
        for i,t in enumerate(self.rows):
            if t['kind']=='primitive':self.primitives[t['opcode']].append(i)
            elif t['group']in ['literal_copy','literal_function','register_source','stack_source']:self.pools['basic'].append(i)
            elif t['group']=='composition':self.pools['composition'].append(i)
            elif t['group'].startswith('algorithm_')or t['kind']in ['programming','interactive_game']:self.pools['algorithm'].append(i)
            else:self.pools['legacy'].append(i)
        for i,t in enumerate(self.tools):self.tool_pools[t['kind']].append(i)
        assert set(self.primitives)==set(range(256))
        catalog=json.loads((ROOT/'catalog.json').read_text());self.documented=[x['code']for x in catalog if x['risk']=='documented'];self.other=[x for x in range(256)if x not in self.documented]
        self.stream=np.memmap(BUILD/'native-mixed-v1/language/train.u16',mode='r',dtype='<u2')
        self.domain=[tokenizer.encode(x['text'],add_special_tokens=False)for x in read(BUILD/'training/domain-documents.jsonl')]
        self.domain=[x for x in self.domain if len(x)>=32]
        self.counts=collections.Counter();self.digest='00'*32

    def encode_pair(self,text,answer):
        x=self.tokenizer.encode(text,add_special_tokens=False);y=self.tokenizer.encode(answer,add_special_tokens=False)+[self.tokenizer.eos_token_id]
        return x+y,[-100]*len(x)+y

    @lru_cache(maxsize=16000)
    def paired(self,category,index,notes):
        if category=='tool':
            row=self.tools[index]
            return {arm:self.encode_pair(value['prompt'],value['answer'])for arm,value in row['pair'].items()}
        task=self.rows[index];pool=task.get('constants')or constants(task['task'])
        return {arm:self.encode_pair(prompt(task,arm,notes=notes),write_call(encode(task['reference_code'],pool,arm)))for arm in ARMS}

    def batch(self,arm,step,device):
        rng=self.rng;rows=[];lm=[];draws=[]
        quotas=[('basic',64),('composition',8),('algorithm',8),('primitive',20),('legacy',8),('tool',16)]if step<=500 else[
          ('basic',32),('composition',20),('algorithm',12),('primitive',16),('legacy',16),('tool',28)]
        for category,total in quotas:
            count=0
            while count<total:
                if category=='primitive':
                    op=rng.choice(self.documented if rng.random()<.95 else self.other);index=rng.choice(self.primitives[op])
                elif category=='tool':
                    kind=rng.choices(['inspect','repair','verify','done'],weights=[.28,.43,.15,.14])[0];index=rng.choice(self.tool_pools[kind])
                else:index=rng.choice(self.pools[category])
                note_id=rng.randrange(8)
                notes=''if category=='tool'or note_id<6 else'Это новая попытка. Используй условие задачи, текущий код и фактические результаты эмулятора.'if note_id==6 else'Архив предыдущих запусков хранится отдельно. Обложка журнала синяя; это не вход вычисления.'
                pair=self.paired(category,index,notes)
                if max(len(p[0])for p in pair.values())>1024:self.counts['resampled_overlength_both']+=1;continue
                rows.append(pair[arm]);lm.append(False);draws.append([category,index,note_id]);count+=1
                self.counts[category]+=1
                if category=='primitive':self.counts[f'opcode:{op:02X}']+=1
                if category=='tool':self.counts['tool:'+self.tools[index]['kind']]+=1
        for _ in range(4):
            if rng.random()<.5:
                index=rng.randrange(len(self.domain));source=self.domain[index];start=rng.randrange(max(1,len(source)-511));ids=source[start:start+512];draws.append(['domain',index,start])
            else:
                start=rng.randrange(len(self.stream)-513);ids=self.stream[start:start+512].astype('int64').tolist();draws.append(['language',start])
            rows.append((ids,ids));lm.append(True);self.counts['language']+=1
        assert len(rows)==128
        order=list(range(128));rng.shuffle(order);rows=[rows[i]for i in order];lm=[lm[i]for i in order]
        self.digest=hashlib.sha256(bytes.fromhex(self.digest)+json.dumps([step,draws,order],separators=(',',':')).encode()).hexdigest()
        length=max(len(x)for x,y in rows);ids=torch.full((128,length),self.tokenizer.pad_token_id or 0,dtype=torch.long);labels=torch.full_like(ids,-100);mask=torch.zeros_like(ids)
        for i,(x,y)in enumerate(rows):ids[i,:len(x)]=torch.tensor(x);labels[i,:len(y)]=torch.tensor(y);mask[i,:len(x)]=1
        return ids.to(device),mask.to(device),labels.to(device),torch.tensor(lm,dtype=torch.bool,device=device)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--arm',choices=ARMS,required=True);a=ap.parse_args();out=ROOT/a.arm;out.mkdir(exist_ok=True)
    lock=(out/'training.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    prepared=json.loads((ROOT/'prepared.json').read_text());policy=json.loads((ROOT/'policy.json').read_text())
    for name,digest in prepared['files'].items():assert sha(ROOT/name)==digest
    for name,digest in prepared['source_hashes'].items():assert sha(HERE/name)==digest
    signature={'arm':a.arm,'prepared_sha256':sha(ROOT/'prepared.json'),'initial_master_sha256':sha(INITIAL/'model.safetensors'),
      'policy_sha256':sha(ROOT/'policy.json'),'steps':policy['steps_each'],'sources':prepared['source_hashes']}
    if(out/'training.json').exists():assert json.loads((out/'training.json').read_text())['signature']==signature;return
    torch.set_num_threads(4);torch.manual_seed(6119212);torch.cuda.set_per_process_memory_fraction(.8);torch.backends.cuda.matmul.allow_tf32=True
    state_path=out/'optimizer/state.pt';state=torch.load(state_path,map_location='cpu',weights_only=True)if state_path.exists()else None
    if state:assert state['signature']==signature
    source=out/'last'if state else INITIAL;tokenizer=AutoTokenizer.from_pretrained(source,local_files_only=True,trust_remote_code=False)
    model=AutoModelForCausalLM.from_pretrained(source,local_files_only=True,trust_remote_code=False).to('cuda');attach(model,'q4')
    embedding=model.get_input_embeddings().parametrizations.weight.original;head=torch.tensor(allowed(),device='cuda')
    row_mask=torch.zeros(embedding.shape[0],dtype=torch.bool,device='cuda');row_mask[head]=True;original_rows=embedding.detach()[~row_mask].clone()
    optimizer=torch.optim.AdamW([{'params':[p for p in model.parameters()if p is not embedding],'factor':1.,'weight_decay':policy['weight_decay']},
      {'params':[embedding],'factor':policy['embedding_lr_factor'],'weight_decay':0.}],lr=policy['lr'])
    course=Course(tokenizer);history=[];best=None;best_step=0;first=0
    if state:
        optimizer.load_state_dict(state['optimizer']);course.rng.setstate(state['rng']);torch.set_rng_state(state['torch_rng']);torch.cuda.set_rng_state_all(state['cuda_rng'])
        course.counts.update(state['counts']);course.digest=state['digest'];history=state['history'];best=state['best'];best_step=state['best_step'];first=state['step']
    def validate(step):
        nonlocal best,best_step
        assert torch.equal(embedding.detach()[~row_mask],original_rows)
        replica,packed=packed_copy(model,out/'development.mkqb','q4');replica.to('cuda').eval();compact_head(replica,allowed())
        previous_tf32=torch.backends.cuda.matmul.allow_tf32;torch.backends.cuda.matmul.allow_tf32=False
        result=development(replica,tokenizer,a.arm);torch.backends.cuda.matmul.allow_tf32=previous_tf32
        key=selection(result);record={'step':step,'key':key,'summary':brief(result),'packet':packed};history.append(record)
        write(out/f'development-{step}.json',{'metrics':result,**record})
        if best is None or key>best:best=key;best_step=step;save(model,tokenizer,out/'best','q4')
        print(json.dumps({'validation':step,'best_step':best_step,'key':key,'groups':record['summary']['language']['by_group'],
          'doc':record['summary']['isa']['documented'],'tools':record['summary']['tools']}),flush=True);del replica
    if not state:validate(0)
    started=time.monotonic();losses=[];steps=policy['steps_each']
    for step in range(first+1,steps+1):
        model.train();optimizer.zero_grad(set_to_none=True)
        rate=policy['lr']*min(1.,step/policy['warmup_updates'])*(.25+.75*(1+math.cos(math.pi*step/steps))/2)
        for g in optimizer.param_groups:g['lr']=rate*g['factor']
        ids,mask,labels,lm=course.batch(a.arm,step,'cuda')
        with torch.autocast('cuda',dtype=torch.bfloat16):loss=compact_loss(model,ids,mask,labels,lm,head)
        if not torch.isfinite(loss):raise ValueError('Nonfinite loss')
        losses.append(float(loss.detach()));loss.backward();del loss,ids,mask,labels,lm
        embedding.grad.mul_(row_mask[:,None]);torch.nn.utils.clip_grad_norm_(model.parameters(),1.);optimizer.step()
        if step==1 or step%50==0:
            write(out/'status.json',{'phase':'training','arm':a.arm,'step':step,'steps':steps,'best_step':best_step,
              'loss':sum(losses[-50:])/len(losses[-50:]),'seconds':time.monotonic()-started,'counts':dict(course.counts),'sample_plan_digest':course.digest})
        if step%policy['validation_interval']==0 or step==steps:
            validate(step);save(model,tokenizer,out/'last','q4');state_path.parent.mkdir(exist_ok=True)
            current={'signature':signature,'step':step,'optimizer':optimizer.state_dict(),'rng':course.rng.getstate(),'torch_rng':torch.get_rng_state(),
              'cuda_rng':torch.cuda.get_rng_state_all(),'counts':dict(course.counts),'digest':course.digest,'history':history,'best':best,'best_step':best_step}
            tmp=state_path.with_suffix('.tmp');torch.save(current,tmp);tmp.replace(state_path)
    assert all(course.counts[f'opcode:{op:02X}']>0 for op in range(256))
    write(out/'training.json',{'signature':signature,'completed':True,'steps':steps,'best_step':best_step,'best_key':best,
      'history':history,'counts':dict(course.counts),'sample_plan_digest':course.digest,'seconds':time.monotonic()-started,
      'actual_examples':128*steps,'all_256_opcodes_sampled':True,'protected_rows_unchanged':True,
      'protected_rows_sha256':hashlib.sha256(embedding.detach()[~row_mask].cpu().contiguous().numpy().tobytes()).hexdigest(),
      'Q4_from_first_update':True,'context':1024,'fresh_used_for_selection':False})
    write(out/'status.json',{'phase':'complete','step':steps,'best_step':best_step})


if __name__=='__main__':main()
