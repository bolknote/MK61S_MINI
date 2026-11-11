"""One bounded QAT backward pass on retired inputs; no optimizer update."""
import torch
from bu_common import ROOT,BS_ROOT,read,write,rows,body_ids
from bu_model import Translator,frozen_digest
from bu_course import encoded,loss
from aq_course import pad
from bs_resources import configure,headroom


def main():
    torch.set_num_threads(3);torch.backends.cuda.matmul.allow_tf32=False
    policy={'gpu':0,'allocator_MiB':1536,'minimum_free_MiB':8192};headroom(policy);configure(policy)
    model=Translator('cuda:0');before=frozen_digest(model);values=[]
    for i,g in enumerate(rows(BS_ROOT/'replay-goals.jsonl')[:8]):
        extra=100
        while True:
            try:
                v=encoded(model.tokenizer,{**g,'task':g['task']+' Сохрани неназванные регистры.'*extra},'preflight:'+str(i),review=bool(i%2))
                if len(v[0])>=930:break
                extra+=1
            except ValueError:extra-=1
        values.append(v)
    head=torch.tensor(body_ids(model.tokenizer),device='cuda:0');torch.cuda.reset_peak_memory_stats()
    with torch.nn.utils.parametrize.cached():value=loss(model,pad(values,'cuda:0'),head)
    value.backward();torch.cuda.synchronize();assert torch.isfinite(value)
    assert all(torch.isfinite(p.grad).all()for p in model.parameters()if p.grad is not None)
    assert frozen_digest(model)==before
    result={'complete':True,'optimizer_updates':0,'trainable_parameters':model.trainable_count(),'microbatch':8,
         'tokens':max(len(v[0])for v in values),'finite_gradient':True,'peak_reserved_MiB':torch.cuda.max_memory_reserved()/2**20,
         'peak_allocated_MiB':torch.cuda.max_memory_allocated()/2**20,'Qwen_modified':False}
    write(ROOT/'GPU-preflight.json',result);print(result,flush=True)


if __name__=='__main__':main()
