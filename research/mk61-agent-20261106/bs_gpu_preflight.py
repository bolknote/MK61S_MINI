"""Bounded-memory worst-length gradient preflight, without optimizer updates."""
import json
import torch
from bs_common import ROOT,read,write,rows,body_ids,check_frozen
from bs_resources import configure
from bs_model import agent
from bp_course import encoded
from aq_course import pad
from be_course import loss


if __name__=='__main__':
    torch.set_num_threads(3);torch.backends.cuda.matmul.allow_tf32=False
    check_frozen();policy=read(ROOT/'policy.json');configure(policy);model=agent('cuda:0');model.train()
    r=next(r for r in rows(ROOT/'lessons.jsonl')if r['origin']=='fresh_write');v=encoded(model.tokenizer,r)
    ids,mask,labels,positions,actions=pad([v]*8,'cuda:0');n=policy['context'];assert ids.shape[1]<=n
    padded=torch.zeros((8,n),dtype=torch.long,device='cuda:0');padded[:,:ids.shape[1]]=ids
    targets=torch.full_like(padded,-100);targets[:,:labels.shape[1]]=labels
    batch=(padded,torch.ones_like(padded),targets,positions,actions,torch.ones(8,dtype=torch.bool,device='cuda:0'))
    optimizer_storage=[torch.zeros_like(p)for p in model.parameters()for _ in range(2)]
    torch.cuda.reset_peak_memory_stats()
    with torch.nn.utils.parametrize.cached():value,parts=loss(model,batch,torch.tensor(body_ids(model.tokenizer),device='cuda:0'))
    value.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1.);torch.cuda.synchronize()
    assert torch.isfinite(value)and all(torch.isfinite(p.grad).all()for p in model.parameters()if p.grad is not None)
    result={'complete':True,'optimizer_updates':0,'batch':8,'tokens_per_example':n,'optimizer_moment_storage_simulated':True,
      'peak_allocated_MiB':torch.cuda.max_memory_allocated()/2**20,'peak_reserved_MiB':torch.cuda.max_memory_reserved()/2**20,
      'allocator_limit_MiB':policy['allocator_MiB'],'finite_gradients':True}
    write(ROOT/'GPU-preflight.json',result);print(json.dumps(result),flush=True)
