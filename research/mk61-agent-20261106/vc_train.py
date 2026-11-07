"""A separate Q4 verifier: binary semantic correctness, no coding objective."""
import argparse
import collections
import hashlib
import json
import math
import random
import time

import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM,AutoTokenizer

from vc_common import ROOT,INITIAL,HERE,ARMS,read,sha,write
from native_quant import attach,save,packed_copy


def scores(model,tokenizer,rows,head,batch=32):
    device=next(model.parameters()).device;out=[]
    for at in range(0,len(rows),batch):
        values=rows[at:at+batch];encoded=[tokenizer.encode(r['prompt'],add_special_tokens=False)for r in values]
        length=max(map(len,encoded));assert length<=1024
        ids=torch.zeros((len(values),length),dtype=torch.long,device=device);mask=torch.zeros_like(ids)
        for i,tokens in enumerate(encoded):ids[i,:len(tokens)]=torch.tensor(tokens,device=device);mask[i,:len(tokens)]=1
        with torch.inference_mode():
            hidden=model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state
            last=hidden[torch.arange(len(values),device=device),torch.tensor([len(t)-1 for t in encoded],device=device)]
            logits=F.linear(last,model.get_input_embeddings().weight.index_select(0,head)).float()
        for row,raw in zip(values,logits.cpu().tolist()):out.append({'id':row['id'],'label':row['label'],'score':raw[0]-raw[1],'logits':raw,'prompt':row['prompt']})
    return out


def metrics(rows,threshold=None):
    positive=[r['score']for r in rows if r['label']];negative=[r['score']for r in rows if not r['label']]
    if threshold is None:threshold=max(negative)+.01
    tp=sum(x>=threshold for x in positive);fp=sum(x>=threshold for x in negative)
    auc=sum((a>b)+.5*(a==b)for a in positive for b in negative)/(len(positive)*len(negative))
    return {'true_positive':tp,'positive':len(positive),'false_positive':fp,'negative':len(negative),'coverage':tp/len(positive),
            'threshold':threshold,'auc':auc,'accuracy_at_zero':sum((r['score']>=0)==bool(r['label'])for r in rows)/len(rows)}


def main():
    p=argparse.ArgumentParser();p.add_argument('--arm',choices=ARMS,required=True);a=p.parse_args();out=ROOT/a.arm;out.mkdir(exist_ok=True)
    frozen=json.loads((ROOT/'data-frozen.json').read_text());policy=json.loads((ROOT/'policy.json').read_text())
    for n,d in frozen['files'].items():assert sha(ROOT/n)==d
    prepared=json.loads((ROOT/'prepared.json').read_text())
    for n,d in prepared['source_hashes'].items():assert sha(HERE/n)==d
    torch.set_num_threads(4);torch.manual_seed(6120911);torch.cuda.set_per_process_memory_fraction(.8)
    torch.backends.cuda.matmul.allow_tf32=False
    tokenizer=AutoTokenizer.from_pretrained(INITIAL,local_files_only=True,trust_remote_code=False)
    model=AutoModelForCausalLM.from_pretrained(INITIAL,local_files_only=True,trust_remote_code=False).to('cuda');attach(model,'q4')
    embedding=model.get_input_embeddings().parametrizations.weight.original;original=embedding.detach().clone();embedding.requires_grad_(False)
    optimizer=torch.optim.AdamW([p for p in model.parameters()if p.requires_grad],lr=policy['lr'][a.arm],weight_decay=.01)
    ids_head=json.loads((ROOT/'output-token-ids.json').read_text());head=torch.tensor(ids_head,device='cuda')
    train=read(ROOT/'train.jsonl');val=read(ROOT/'validation.jsonl');encoded=[tokenizer.encode(r['prompt'],add_special_tokens=False)for r in train]
    pools={c:[i for i,r in enumerate(train)if r['label']==c]for c in [0,1]};rng=random.Random(6120912);digest='00'*32;history=[];best=None;best_step=0;started=time.monotonic()
    def validate(step):
        nonlocal best,best_step
        replica,_=packed_copy(model,out/'development.mkqb','q4');replica.to('cuda').eval()
        rows=scores(replica,tokenizer,val,head);m=metrics(rows);key=[m['coverage']>=.8,m['coverage'],m['auc'],m['accuracy_at_zero']]
        record={'step':step,'metrics':m,'key':key};history.append(record);write(out/f'development-{step}.json',{**record,'details':rows})
        if best is None or key>best:best=key;best_step=step;save(model,tokenizer,out/'best','q4')
        assert torch.equal(embedding.detach(),original)
        print(json.dumps({'validation':step,'best_step':best_step,**m}),flush=True);del replica
    validate(0);steps=policy['steps_each'];losses=[]
    for step in range(1,steps+1):
        model.train();chosen=rng.choices(pools[0],k=64)+rng.choices(pools[1],k=64);rng.shuffle(chosen)
        digest=hashlib.sha256(bytes.fromhex(digest)+json.dumps(chosen).encode()).hexdigest()
        length=max(len(encoded[i])for i in chosen);ids=torch.zeros((128,length),dtype=torch.long,device='cuda');mask=torch.zeros_like(ids)
        for j,i in enumerate(chosen):ids[j,:len(encoded[i])]=torch.tensor(encoded[i],device='cuda');mask[j,:len(encoded[i])]=1
        target=torch.tensor([0 if train[i]['label']else 1 for i in chosen],device='cuda');ends=torch.tensor([len(encoded[i])-1 for i in chosen],device='cuda')
        rate=policy['lr'][a.arm]*min(1.,step/100)*(.25+.75*(1+math.cos(math.pi*step/steps))/2)
        for group in optimizer.param_groups:group['lr']=rate
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast('cuda',dtype=torch.bfloat16):
            hidden=model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state
            last=hidden[torch.arange(128,device='cuda'),ends];logits=F.linear(last,model.get_input_embeddings().weight.index_select(0,head))
            loss=F.cross_entropy(logits.float(),target)
        assert torch.isfinite(loss);losses.append(float(loss.detach()));loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1.);optimizer.step()
        if step%50==0:write(out/'status.json',{'phase':'training','step':step,'steps':steps,'best_step':best_step,'loss':sum(losses[-50:])/50,'seconds':time.monotonic()-started})
        if step%policy['validation_interval']==0 or step==steps:validate(step)
    assert torch.equal(embedding.detach(),original)
    write(out/'training.json',{'completed':True,'steps':steps,'best_step':best_step,'best_key':best,'history':history,'sample_plan_digest':digest,
      'all_embeddings_unchanged':True,'embedding_sha256':hashlib.sha256(original.cpu().numpy().tobytes()).hexdigest(),
      'parameters':sum(p.numel()for p in model.parameters()),'trainable_parameters':sum(p.numel()for p in model.parameters()if p.requires_grad),
      'Q4_from_first_update':True,'seconds':time.monotonic()-started,'actual_examples':steps*128})
    write(out/'status.json',{'phase':'complete','step':steps,'best_step':best_step})


if __name__=='__main__':main()
