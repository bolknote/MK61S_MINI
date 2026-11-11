"""Worst-length paired backward with all three real resident models, zero updates."""
import torch
import torch.nn.functional as F
from cb_common import ROOT,ACTOR,PARENT,read,write,check_frozen,body_ids,output_ids,compact_head
from cb_model import Actor
from cb_course import Course,loss
from be_model import load
from bs_resources import configure


def main():
    check_frozen();torch.set_num_threads(3);torch.backends.cuda.matmul.allow_tf32=False
    policy=read(ROOT/'policy.json');configure(policy)
    teacher,tok=load(ACTOR,'cuda:0');translator,_=load(PARENT,'cuda:0')
    for m in [teacher,translator]:compact_head(m,output_ids(tok))
    model=Actor('cuda:0',ROOT/'initial.safetensors');ids,mask,labels,pos,act,retain=Course(tok).step(1,'cuda:0')[0]
    extra=1000-ids.shape[1];assert extra>=0
    batch=F.pad(ids,(0,extra)),F.pad(mask,(0,extra)),F.pad(labels,(0,extra),value=-100),pos,act,torch.ones_like(retain)
    torch.cuda.reset_peak_memory_stats()
    with torch.nn.utils.parametrize.cached():value,parts=loss(model,teacher,batch,torch.tensor(body_ids(tok),device='cuda:0'))
    value.backward();torch.cuda.synchronize();assert torch.isfinite(value)and all(torch.isfinite(p.grad).all()for p in model.parameters()if p.grad is not None)
    out={'complete':True,'optimizer_updates':0,'microbatch':4,'tokens':1000,'finite_gradient':True,
        'peak_reserved_MiB':torch.cuda.max_memory_reserved()/2**20,'peak_allocated_MiB':torch.cuda.max_memory_allocated()/2**20,
        'loss':float(value.detach()),'parts':parts,'forced_KD_path':True,'Qwen_modified':False}
    assert out['peak_reserved_MiB']<=policy['allocator_MiB'];write(ROOT/'GPU-preflight.json',out);print(out,flush=True)


if __name__=='__main__':main()
