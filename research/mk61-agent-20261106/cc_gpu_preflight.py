"""Bounded encoder/readout preflight alongside Qwen, with zero optimizer updates."""
import torch
from cc_common import ROOT,PARENT,WORKING,ACTOR,read,write,rows,check_frozen,ACTION_IDS
from cc_model import Actor
from aq_protocol import prompt_ids
from be_model import load
from bs_resources import configure

def main():
    check_frozen();policy=read(ROOT/'policy.json');configure(policy);torch.set_num_threads(3);torch.backends.cuda.matmul.allow_tf32=False
    model=Actor('cuda:0',ROOT/'initial.safetensors');other,tok=load(PARENT,'cuda:0');working,_=load(WORKING,'cuda:0')
    row=max(rows(ROOT/'lessons.jsonl'),key=lambda r:r['input_tokens']);tokens=prompt_ids(tok,row['prompt'])
    ids=torch.tensor([tokens],device='cuda:0');torch.cuda.reset_peak_memory_stats()
    with torch.no_grad():hidden=model.model(input_ids=ids,attention_mask=torch.ones_like(ids),use_cache=False).last_hidden_state[:,-1].detach()
    logits=torch.nn.functional.linear(hidden,model.action_weight());value=logits.square().mean();value.backward()
    assert torch.isfinite(value)and model.decision_head.grad is not None and all(p.grad is None for n,p in model.named_parameters()if n!='decision_head')
    torch.cuda.synchronize();out={'complete':True,'optimizer_updates':0,'trainable_parameters':384,'tokens':len(tokens),'finite_head_gradient':True,
        'peak_reserved_MiB':torch.cuda.max_memory_reserved()/2**20,'peak_allocated_MiB':torch.cuda.max_memory_allocated()/2**20,'Qwen_modified':False}
    assert out['peak_reserved_MiB']<=policy['allocator_MiB'];write(ROOT/'GPU-preflight.json',out);print(out,flush=True)

if __name__=='__main__':main()
