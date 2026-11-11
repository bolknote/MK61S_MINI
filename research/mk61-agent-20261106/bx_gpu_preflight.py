"""Bounded paired-loss backward pass with the real three resident models, no SGD."""
import gc
import torch
from bx_common import ROOT,ACTOR,PARENT,PARENT_CHECKPOINT,read,write,body_ids,output_ids,compact_head
from bu_model import Translator
from be_model import load
from bx_course import Course,loss
from bs_resources import configure


def main():
    torch.set_num_threads(3);torch.backends.cuda.matmul.allow_tf32=False
    policy=read(ROOT/'policy.json');configure(policy)
    actor,tok=load(ACTOR,'cuda:0');teacher,t=load(PARENT,'cuda:0');compact_head(actor,output_ids(tok));compact_head(teacher,output_ids(tok))
    model=Translator('cuda:0',PARENT_CHECKPOINT);head=torch.tensor(body_ids(tok),device='cuda:0');batch=Course(tok).step(1,'cuda:0')[0]
    # Left-pad every paired sequence to the supported worst-case training length.
    ids,mask,labels,pos,act,positive=batch;extra=1000-ids.shape[1];assert extra>=0
    positive=torch.ones_like(positive)  # Exercise the KD path in this no-update memory stress check.
    import torch.nn.functional as F
    batch=(F.pad(ids,(extra,0),value=tok.pad_token_id or 0),F.pad(mask,(extra,0)),F.pad(labels,(extra,0),value=-100),pos+extra,act,positive)
    torch.cuda.reset_peak_memory_stats()
    with torch.nn.utils.parametrize.cached():value,parts=loss(model,teacher,batch,head,policy['JS_weight'],policy['KD_weight'])
    value.backward();torch.cuda.synchronize()
    assert torch.isfinite(value)and all(torch.isfinite(p.grad).all()for p in model.parameters()if p.grad is not None)
    v={'complete':True,'optimizer_updates':0,'microbatch':policy['microbatch'],'tokens':1000,'finite_gradient':True,
        'peak_reserved_MiB':torch.cuda.max_memory_reserved()/2**20,'peak_allocated_MiB':torch.cuda.max_memory_allocated()/2**20,'loss':float(value.detach()),'parts':parts,'forced_KD_path':True,'Qwen_modified':False}
    assert v['peak_reserved_MiB']<=policy['allocator_MiB'];write(ROOT/'GPU-preflight.json',v);print(v,flush=True)


if __name__=='__main__':main()
