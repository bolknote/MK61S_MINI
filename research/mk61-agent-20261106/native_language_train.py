"""Matched 100M-token language continuation in each arm's final weight format."""
import argparse
import fcntl
import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np
import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM,AutoTokenizer

from tasks import BUILD
from native_quant import attach,restore_scales,save,packed_copy


def loss_values(student,teacher,targets):
    ce=F.cross_entropy(student.float().reshape(-1,student.shape[-1]),targets.reshape(-1))
    if teacher is None:return ce,ce,ce*0
    t=2.;kl=F.kl_div(F.log_softmax(student.float()/t,dim=-1),F.softmax(teacher.float()/t,dim=-1),
                   reduction='none').sum(-1).mean()*t*t
    return .7*ce+.3*kl,ce,kl


def main():
    p=argparse.ArgumentParser();p.add_argument('--arm',choices=['q4','mixed'],required=True)
    p.add_argument('--tokens',type=int,default=100000000);p.add_argument('--micro',type=int,default=16)
    a=p.parse_args();root=BUILD/'native-mixed-v1';output=root/(a.arm+'-language');output.mkdir(exist_ok=True)
    lock=(output/'training.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX)
    if(output/'complete.json').exists():print('Matching language stage complete');return
    torch.set_num_threads(2);torch.manual_seed(6111701);torch.cuda.set_per_process_memory_fraction(.025)
    torch.backends.cuda.matmul.allow_tf32=True
    initial=root/('initial-active'if(root/'initial-active/manifest.json').exists()else'initial')/a.arm
    tokenizer=AutoTokenizer.from_pretrained(initial,local_files_only=True,trust_remote_code=False)
    model=AutoModelForCausalLM.from_pretrained(initial,local_files_only=True,trust_remote_code=False).to('cuda')
    net_parameters=sum(x.numel()for x in model.parameters());attach(model,a.arm);restore_scales(model,initial)
    teacher=AutoModelForCausalLM.from_pretrained(BUILD/'flourish-original',local_files_only=True,trust_remote_code=False).to('cuda').eval()
    teacher.requires_grad_(False)
    weights=[v for n,v in model.named_parameters()if not n.endswith('.log_scale')]
    scales=[v for n,v in model.named_parameters()if n.endswith('.log_scale')]
    groups=[{'params':weights,'factor':1.}]+([{'params':scales,'factor':5.}]if scales else[])
    optimizer=torch.optim.AdamW(groups,lr=2e-4,weight_decay=.01)
    optimizer_ids={id(x)for g in optimizer.param_groups for x in g['params']}
    manifest=json.loads((root/'language/manifest.json').read_text())
    assert hashlib.sha256((initial/'tokenizer.json').read_bytes()).hexdigest()==manifest['tokenizer_sha256']
    train=np.memmap(root/'language/train.u16',mode='r',dtype='<u2');val=np.memmap(root/'language/validation.u16',mode='r',dtype='<u2')
    rng=np.random.default_rng(6111701);blocks=rng.permutation((len(train)-1)//512);cursor=0;steps=math.ceil(a.tokens/(32*512))
    history=[];best=float('inf');best_step=0;started=time.monotonic()
    def batch(stream,positions):
        value=np.stack([stream[int(x):int(x)+513]for x in positions]).astype(np.int64)
        return torch.from_numpy(value).to('cuda')
    def validate(step):
        nonlocal best,best_step
        replica,packet=packed_copy(model,output/'development.mkqb',a.arm);replica.to('cuda').eval()
        total=0.;count=0
        with torch.inference_mode():
            for offset in range(0,65536,4*512):
                window=batch(val,np.arange(offset,offset+4*512,512))
                with torch.autocast('cuda',dtype=torch.bfloat16):
                    logits=replica(window[:,:-1],use_cache=False).logits
                    value=loss_values(logits,None,window[:,1:])[0]
                total+=float(value)*4;count+=4
        nll=total/count;history.append({'step':step,'tokens':step*32*512,'validation_nll':nll,'packed':packet})
        if nll<best:best=nll;best_step=step;save(model,tokenizer,output/'best',a.arm)
        print(json.dumps({'validation_step':step,'nll':nll,'best_step':best_step}),flush=True)
        del replica
        assert optimizer_ids=={id(v)for v in model.parameters()}
    validate(0)
    for step in range(1,steps+1):
        model.train();optimizer.zero_grad(set_to_none=True)
        rate=2e-4*min(1.,step/200)*(.1+.9*(1+math.cos(math.pi*step/steps))/2)
        for g in optimizer.param_groups:g['lr']=rate*g['factor']
        losses=[];ces=[];kls=[]
        for _ in range(32//a.micro):
            if cursor+a.micro>len(blocks):blocks=rng.permutation((len(train)-1)//512);cursor=0
            window=batch(train,blocks[cursor:cursor+a.micro]*512);cursor+=a.micro
            with torch.autocast('cuda',dtype=torch.bfloat16):
                with torch.no_grad():target=teacher(window[:,:-1],use_cache=False).logits
                prediction=model(window[:,:-1],use_cache=False).logits
                loss,ce,kl=loss_values(prediction,target,window[:,1:])
                loss=loss/(32//a.micro)
            if not torch.isfinite(loss):raise ValueError('Non-finite language loss')
            losses.append(float(loss.detach()));ces.append(float(ce.detach()));kls.append(float(kl.detach()));loss.backward()
            del target,prediction,loss,ce,kl,window
        torch.nn.utils.clip_grad_norm_(model.parameters(),1.);optimizer.step()
        if step==1 or step%50==0:
            status={'phase':'language_training','step':step,'steps':steps,'token_exposures':step*32*512,
              'loss':sum(losses),'ce':sum(ces)/len(ces),'kl':sum(kls)/len(kls),'best_step':best_step,
              'seconds':time.monotonic()-started,'gpu_peak_allocated':torch.cuda.max_memory_allocated()}
            embedding=model.get_input_embeddings().parametrizations.weight.original
            status['embedding_hidden_half_difference_max']=float((embedding[:,:128]-embedding[:,128:]).abs().max().detach())
            if step>=100 and status['embedding_hidden_half_difference_max']==0:raise ValueError('Hidden coordinates remain duplicated')
            with torch.no_grad():
                effective=model.get_input_embeddings().weight
                status['quantized_embedding_half_difference_max']=float((effective[:,:128]-effective[:,128:]).abs().max())
            if step>=1000 and status['quantized_embedding_half_difference_max']==0:raise ValueError('Quantized hidden coordinates remain duplicated')
            (output/'status.json').write_text(json.dumps(status)+'\n');print(json.dumps(status),flush=True)
        if step%1000==0 or step==steps:validate(step)
    save(model,tokenizer,output/'last',a.arm)
    result={'completed':True,'arm':a.arm,'weight_parameters':net_parameters,'learned_scale_parameters':sum(x.numel()for x in scales),
      'tokens':steps*32*512,'steps':steps,'best_step':best_step,'best_validation_nll':best,'history':history,
      'context':512,'max_configured_context_not_yet_trained':2048,'precision_from_first_update':True,
      'teacher':'Unmodified original Flourish-3M','loss':'.7 next-token CE + .3 temperature2 teacher KL',
      'language_data':manifest,'initial':str(initial),'retained_warmup_tokens':32768000 if 'initial-active'in initial.parts else 0,
      'seconds':time.monotonic()-started,'fresh_audit_opened':False}
    (output/'training.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    (output/'complete.json').write_text(json.dumps({'completed':True,'best_step':best_step})+'\n')
    (output/'status.json').write_text(json.dumps({'phase':'complete','best_step':best_step,'nll':best})+'\n')


if __name__=='__main__':main()
