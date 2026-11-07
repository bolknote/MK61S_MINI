"""Verify the actual padded long-context backward pass fits the reserved GPU share."""
import gc
import json

import torch
from transformers import AutoModelForCausalLM

from capacity_train import example_loss
from native_quant import attach,restore_scales
from tasks import BUILD


def main():
    torch.set_num_threads(2);torch.manual_seed(6112201);torch.cuda.set_per_process_memory_fraction(.025)
    root=BUILD/'native-mixed-v1';records=[]
    for arm in ['q4','mixed']:
        source=root/'initial-active'/arm
        model=AutoModelForCausalLM.from_pretrained(source,local_files_only=True,trust_remote_code=False).to('cuda')
        attach(model,arm);restore_scales(model,source);model.train()
        for length,micro in [(512,16),(1024,8),(2048,4)]:
            model.zero_grad(set_to_none=True);torch.cuda.empty_cache();torch.cuda.reset_peak_memory_stats()
            ids=torch.randint(10,8192,(micro,length),device='cuda');mask=torch.ones_like(ids);labels=torch.full_like(ids,-100)
            for i in range(micro):
                n=length if i%2 else min(length,384)
                mask[i,n:]=0;labels[i,n-20:n]=ids[i,n-20:n]
            with torch.autocast('cuda',dtype=torch.bfloat16):
                logits=model(input_ids=ids,attention_mask=mask,use_cache=False).logits;loss=example_loss(logits,labels)
            loss.backward();assert torch.isfinite(loss)
            peak=torch.cuda.max_memory_allocated();records.append({'arm':arm,'sequence':length,'micro':micro,'padded_rows':micro//2,
              'peak_allocated_bytes':peak,'loss':float(loss.detach()),'all_gradients_finite':all(torch.isfinite(p.grad).all().item()for p in model.parameters()if p.grad is not None)})
            print(json.dumps(records[-1]),flush=True)
            del ids,mask,labels,logits,loss
        del model;gc.collect();torch.cuda.empty_cache()
    (root/'gpu-memory-preflight.json').write_text(json.dumps({'probes':records,'diagnostic_updates_saved':False},indent=2)+'\n')


if __name__=='__main__':main()
