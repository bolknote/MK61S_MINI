"""Cache only frozen Q4 encoder outputs from training prompts; no held-out states."""
import time
import torch
from safetensors.torch import save_file
from cc_common import ROOT,ACTOR,read,write,rows,sha,check_frozen,ACTIONS,ACTION_IDS
from aq_protocol import prompt_ids
from aq_model import action_weight
from be_model import load
from bs_resources import headroom,duty

@torch.inference_mode()
def extract(policy,progress):
    if(ROOT/'features-frozen.json').exists():
        info=read(ROOT/'features-frozen.json');assert sha(ROOT/'features.safetensors')==info['sha256'];return info
    check_frozen();model,tok=load(ACTOR,'cuda:0');data=rows(ROOT/'lessons.jsonl');hidden=[];logits=[];started=time.monotonic()
    head=action_weight(model)
    for i,row in enumerate(data):
        if i%100==0:headroom(policy,progress)
        active=time.monotonic();tokens=prompt_ids(tok,row['prompt']);assert len(tokens)==row['input_tokens']and not set(tokens)&set(ACTION_IDS)
        ids=torch.tensor([tokens],device='cuda:0');h=model.model(input_ids=ids,attention_mask=torch.ones_like(ids),use_cache=False).last_hidden_state[:,-1].float()
        hidden.append(h[0].cpu());logits.append(torch.nn.functional.linear(h,head)[0].float().cpu());duty(active,policy)
        if(i+1)%500==0:progress('frozen_features',states=i+1,total=len(data),seconds=time.monotonic()-started)
    tensors={'hidden':torch.stack(hidden),'teacher_logits':torch.stack(logits),'labels':torch.tensor([ACTIONS.index(r['action'])for r in data]),
        'retain':torch.tensor([bool(r.get('retain')or r.get('successful_repair_replay'))for r in data])}
    save_file(tensors,str(ROOT/'features.safetensors'));info={'complete':True,'sha256':sha(ROOT/'features.safetensors'),'rows':len(data),
        'source_lessons_sha256':sha(ROOT/'lessons.jsonl'),'frozen_parent_packet_sha256':sha(ACTOR/'model.mkqb'),'held_out_states_used':False,
        'optimizer_updates':0,'seconds':time.monotonic()-started,'peak_reserved_MiB':torch.cuda.max_memory_reserved()/2**20}
    write(ROOT/'features-frozen.json',info);del model;torch.cuda.empty_cache();check_frozen();return info
