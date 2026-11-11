"""Matched-input logits, exact head/representation split and Q4 block reversions."""
import collections
import copy
import json
import time
import numpy as np
import torch
from transformers import AutoModelForCausalLM,AutoTokenizer
from lowbit import load as load_q4
from aq_protocol import prompt_ids
from bn_common import ROOT,OLD,NEW,ACTIONS,ACTION_IDS,read,write,rows,check


def forward(model,encoded,batch=8):
    hidden=[];device=next(model.parameters()).device
    with torch.inference_mode():
        for at in range(0,len(encoded),batch):
            chunk=encoded[at:at+batch];width=max(map(len,chunk))
            ids=torch.zeros((len(chunk),width),device=device,dtype=torch.long);mask=torch.zeros_like(ids)
            for j,p in enumerate(chunk):ids[j,:len(p)]=torch.tensor(p,device=device);mask[j,:len(p)]=1
            h=model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state
            hidden.append(h[torch.arange(len(ids),device=device),mask.sum(1)-1].detach().cpu())
    return torch.cat(hidden)


def logits(h,head):
    with torch.inference_mode():
        return torch.nn.functional.linear(h.cuda(),head.cuda()).float().cpu().numpy().astype(np.float64)


def metrics(scores,data):
    pred=scores.argmax(1);out={}
    for source in ['old','new']:
        indexes=[i for i,r in enumerate(data)if r['source']==source];wanted=np.array([ACTIONS.index(data[i]['expected_action'])for i in indexes])
        out[source]={'total':len(indexes),'expected_action_matches':int((pred[indexes]==wanted).sum()),
                     'actions':dict(collections.Counter(ACTIONS[pred[i]]for i in indexes))}
    selected=[i for i,r in enumerate(data)if r['source']=='new'and r['abstained']]
    avoidable=[i for i in selected if data[i]['expected_action']!='unsure']
    justified=[i for i in selected if data[i]['expected_action']=='unsure']
    controls=[i for i,r in enumerate(data)if r['source']=='new'and r['pass']]
    out['new_abstentions']={'total':len(selected),'justified_given_current_SPEC_and_budget':len(justified),
                           'avoidable_given_correct_SPEC_and_budget':len(avoidable),
                           'avoidable_still_UNSURE':sum(ACTIONS[pred[i]]=='unsure'for i in avoidable),
                           'avoidable_expected_action':sum(ACTIONS[pred[i]]==data[i]['expected_action']for i in avoidable),
                           'justified_wrongly_DONE':sum(ACTIONS[pred[i]]=='done'for i in justified)}
    out['new_success_controls']={'total':len(controls),'retain_DONE':sum(ACTIONS[pred[i]]=='done'for i in controls)}
    return out


def main():
    check();data=rows(ROOT/'states.jsonl');tok=AutoTokenizer.from_pretrained(NEW/'hf',local_files_only=True)
    encoded=[prompt_ids(tok,r['prompt'])for r in data];started=time.monotonic();models={};hidden={};heads={};scores={};baseline={}
    for name,folder,quantized in [('old_master',OLD,False),('new_master',NEW,False),('old_Q4',OLD,True),('new_Q4',NEW,True)]:
        model=AutoModelForCausalLM.from_pretrained(folder/'hf',local_files_only=True).float()
        if quantized:load_q4(model,folder/'model.mkqb')
        model.cuda().eval().requires_grad_(False);models[name]=model
        h=forward(model,encoded);head=model.get_input_embeddings().weight[ACTION_IDS].detach().cpu()
        s=logits(h,head)
        if quantized:
            source=name.split('_')[0];indexes=[i for i,r in enumerate(data)if r['source']==source]
            mismatches=[i for i in indexes if ACTIONS[s[i].argmax()]!=data[i]['recorded_action']]
            if mismatches:
                h=forward(model,encoded,1);s=logits(h,head)
                mismatches=[i for i in indexes if ACTIONS[s[i].argmax()]!=data[i]['recorded_action']]
            assert not mismatches,('Recorded decision differs',name,[data[i]['id']for i in mismatches[:5]])
        hidden[name]=h;heads[name]=head;scores[name]=s;baseline[name]=metrics(s,data)
        print(json.dumps({'baseline':name,'metrics':baseline[name]}),flush=True)
    # Exact symmetric bilinear decomposition. Action-token embedding rows never
    # occur in any input, so swapping only these rows changes the output head.
    oldh,newh=hidden['old_Q4'].double(),hidden['new_Q4'].double();oldw,neww=heads['old_Q4'].double(),heads['new_Q4'].double()
    dw=neww-oldw;dh=newh-oldh;mh=(newh+oldh)/2;mw=(neww+oldw)/2
    row=(mh@dw.T).numpy();representation=(dh@mw.T).numpy()
    exact_delta=(newh@neww.T-oldh@oldw.T).numpy();error=float(np.abs(exact_delta-row-representation).max());assert error<1e-9,error
    float32_rounding=float(np.abs(scores['new_Q4']-scores['old_Q4']-exact_delta).max())
    u=ACTIONS.index('unsure');decomposed=[]
    for i,r in enumerate(data):
        if r['expected_action']=='unsure':continue
        a=ACTIONS.index(r['expected_action'])
        decomposed.append({'id':r['id'],'source':r['source'],'abstained':r['abstained'],'expected_action':r['expected_action'],
                           'old_action':ACTIONS[int(scores['old_Q4'][i].argmax())],'new_action':ACTIONS[int(scores['new_Q4'][i].argmax())],
                           'UNSURE_minus_expected_old':float(scores['old_Q4'][i,u]-scores['old_Q4'][i,a]),
                           'UNSURE_minus_expected_new':float(scores['new_Q4'][i,u]-scores['new_Q4'][i,a]),
                           'head_contribution':float(row[i,u]-row[i,a]),'hidden_contribution':float(representation[i,u]-representation[i,a])})
    ablations={}
    s=logits(hidden['new_Q4'],heads['old_Q4']);ablations['old_action_rows']=metrics(s,data)
    ablations['new_action_rows_on_old_body']=metrics(logits(hidden['old_Q4'],heads['new_Q4']),data)
    for name in ['old_action_rows','new_action_rows_on_old_body']:print(json.dumps({'ablation':name,'metrics':ablations[name]}),flush=True)
    model=models['new_Q4'];old_state={n:p.detach().clone()for n,p in models['old_Q4'].named_parameters()};new_state={n:p.detach().clone()for n,p in model.named_parameters()}
    plan=read(ROOT/'plan.json')
    for variant in plan['ablations']:
        if variant=='old_action_rows':continue
        selected=[]
        for n in new_state:
            if variant=='old_all_attention'and'.self_attn.'in n:selected.append(n)
            elif variant=='old_all_MLP'and'.mlp.'in n:selected.append(n)
            elif variant=='old_norms'and('layernorm'in n or n=='model.norm.weight'):selected.append(n)
            elif variant.startswith('old_layer_')and n.startswith('model.layers.'+variant[len('old_layer_'):]+'.'):selected.append(n)
            elif variant=='old_input_embeddings_except_action_rows'and n=='model.embed_tokens.weight':selected.append(n)
        assert selected,variant
        with torch.no_grad():
            for n,p in model.named_parameters():p.copy_(new_state[n])
            for n in selected:model.get_parameter(n).copy_(old_state[n])
            if variant=='old_input_embeddings_except_action_rows':model.get_input_embeddings().weight[ACTION_IDS]=new_state['model.embed_tokens.weight'][ACTION_IDS]
        h=forward(model,encoded);head=model.get_input_embeddings().weight[ACTION_IDS].detach().cpu();s=logits(h,head)
        ablations[variant]={**metrics(s,data),'reverted_tensors':selected}
        print(json.dumps({'ablation':variant,'metrics':{k:v for k,v in ablations[variant].items()if k!='reverted_tensors'}}),flush=True)
        write(ROOT/'action-ablation-progress.json',ablations)
    write(ROOT/'logit-attribution.json',{'exact_bilinear_decomposition_max_error':error,'float32_logit_delta_rounding_max_error':float32_rounding,'records':decomposed,
          'caveat':'Head/hidden attribution is exact on fixed prompts. Whole-block grafts are interventions on co-adapted weights, not proof that a tensor alone caused the entire training regression.'})
    write(ROOT/'action-ablation.json',{'baseline':baseline,'ablations':ablations,'same_input_prompts':True,'known_original_Q4_decisions_all_reproduced':True,
          'original_training_or_test_records_modified':False,'optimizer_updates':0,'seconds':time.monotonic()-started})
    write(ROOT/'actions-complete.json',{'complete':True,'optimizer_updates':0});check()


if __name__=='__main__':
    torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False;main()
