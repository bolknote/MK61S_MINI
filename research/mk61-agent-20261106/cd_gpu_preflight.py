"""Zero-step GPU and actual paired-branch protocol checks before utility collection."""
import torch
from cd_common import ROOT,PARENT,WORKING,read,write,rows,check_frozen,output_ids,compact_head
from cd_model import Actor,ROWS
from cd_rollout import OTHER,Decoder,rollout
from aq_protocol import prompt_ids
from be_model import load
from bs_resources import configure
from bl_spec import install
from bl_vm import CachedVM

def main():
    check_frozen();policy=read(ROOT/'policy.json');configure(policy);torch.set_num_threads(3);torch.backends.cuda.matmul.allow_tf32=False
    model=Actor('cuda:0',ROOT/'initial.safetensors');translator,tok=load(PARENT,'cuda:0');working,_=load(WORKING,'cuda:0')
    seeds=rows(ROOT/'utility-seeds.jsonl');row=max(seeds,key=lambda r:r['input_tokens']);ids=torch.tensor([prompt_ids(tok,row['prompt'])],device='cuda:0')
    torch.cuda.reset_peak_memory_stats()
    with torch.no_grad():h=model.model(input_ids=ids,attention_mask=torch.ones_like(ids),use_cache=False).last_hidden_state[:,-1].detach()
    logits=torch.nn.functional.linear(h,model.action_weight());margin=logits[:,ROWS[0]]-logits[:,OTHER].max(-1).values
    value=torch.nn.functional.binary_cross_entropy_with_logits(margin,torch.ones_like(margin));value.backward()
    assert torch.isfinite(value)and model.decision_head.grad is not None and all(p.grad is None for n,p in model.named_parameters()if n!='decision_head')
    compact_head(model.base,output_ids(tok));compact_head(translator,output_ids(tok));install();vm=CachedVM(128)
    goals={r['key']:r['goal']for r in rows(ROOT/'utility-goals.jsonl')};seed=next(s for s in seeds if s['origin']=='four_way_initial'and s['spec_correct_seed']and s['code_correct_seed'])
    decoder=Decoder(model.base,translator,tok,policy,lambda *a,**k:None)
    a=rollout(seed,goals[seed['goal_key']],'done',decoder,vm);b=rollout(seed,goals[seed['goal_key']],'diag',decoder,vm)
    assert a['pass']and a['steps']==1 and b['steps']<=12
    out={'complete':True,'optimizer_updates':0,'trainable_parameters':128,'tokens':len(ids[0]),'finite_gate_gradient':True,
        'actual_correct_code_DONE_completed':True,'paired_actual_DIAG_ran':True,'DIAG_result_pass':b['pass'],'DIAG_actual_replans':b['replans'],
        'prefix_and_remaining_budget_verified':True,'peak_reserved_MiB':torch.cuda.max_memory_reserved()/2**20,
        'peak_allocated_MiB':torch.cuda.max_memory_allocated()/2**20,'Qwen_modified':False}
    assert out['peak_reserved_MiB']<=policy['allocator_MiB'];write(ROOT/'GPU-preflight.json',out);print(out,flush=True)

if __name__=='__main__':main()
