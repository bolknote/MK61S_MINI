"""Memory/gradient probe for repair plus correct-token KD, without an update."""
import gc
import torch
from bv_common import ROOT,BU_ROOT,PARENT,PARENT_CHECKPOINT,write,rows,body_ids
from bu_model import Translator,actor,frozen_digest
from be_model import load
from bu_course import encoded
from bv_course import loss
from aq_course import pad
from bs_resources import headroom,configure


def attempt(microbatch):
    model=Translator('cuda:0',PARENT_CHECKPOINT);teacher,tok=load(PARENT,'cuda:0');unused,_=actor('cuda:0');before=frozen_digest(model)
    values=[]
    for i,g in enumerate(rows(BU_ROOT/'replay.jsonl')[:microbatch]):
        extra=100
        for count in range(240):
            try:
                v=encoded(tok,{**g,'task':g['task']+' Сохрани неназванные регистры.'*extra},'bv-preflight:'+str(i),review=bool(i%2))
                if len(v[0])>=930:break
                extra+=1
            except ValueError:extra-=1
        else:raise RuntimeError('Could not construct bounded preflight input')
        values.append(v)
    batch=(*pad(values,'cuda:0'),torch.tensor([i%2==0 for i in range(microbatch)],device='cuda:0'));head=torch.tensor(body_ids(tok),device='cuda:0')
    torch.cuda.reset_peak_memory_stats()
    with torch.nn.utils.parametrize.cached():value,parts=loss(model,teacher,batch,head)
    value.backward();torch.cuda.synchronize();assert torch.isfinite(value)
    assert all(torch.isfinite(p.grad).all()for p in model.parameters()if p.grad is not None)
    assert frozen_digest(model)==before
    return {'complete':True,'optimizer_updates':0,'microbatch':microbatch,'tokens':max(len(v[0])for v in values),
        'peak_reserved_MiB':torch.cuda.max_memory_reserved()/2**20,'peak_allocated_MiB':torch.cuda.max_memory_allocated()/2**20,
        'finite_gradient':True,'parts':parts,'Qwen_modified':False}


if __name__=='__main__':
    torch.set_num_threads(3);torch.backends.cuda.matmul.allow_tf32=False
    p={'gpu':0,'allocator_MiB':1536,'minimum_free_MiB':8192};headroom(p);configure(p)
    failed=False
    try:r=attempt(8)
    except torch.OutOfMemoryError:failed=True
    if failed:
        gc.collect();torch.cuda.empty_cache();r=attempt(4);r['microbatch8_exceeded_allocator']=True
    write(ROOT/'GPU-preflight.json',r);print(r,flush=True)
