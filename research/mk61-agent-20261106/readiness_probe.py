"""Frozen-Q4 readiness probe: train/validate a tiny head, never a runtime oracle."""
import argparse
import collections
import json
from pathlib import Path
import random

import numpy as np
import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM,AutoTokenizer

from hf_common import read,sha,write
from hf_runtime import Session
from hf_tools import seed
from ha_protocol import constants,encode
from full_isa_vm import FullVM
from lowbit import load


def pairs(tasks,part,vm,per_group=None):
    groups=collections.defaultdict(list);out=[];rng=random.Random(6120811)
    for t in tasks:groups[t['group']].append(t)
    chosen=[]
    for values in groups.values():rng.shuffle(values);chosen+=values[:per_group]if per_group else values
    for i,task in enumerate(chosen):
        for correct in [True,False]:
            item=seed(task,vm,6120812+i,correct=correct)
            pool=task.get('constants')or constants(task['task']);s=Session(task,'asm',body=encode(item['initial_code'],pool,'asm'),vm=vm)
            for index in range(len(task['public_tests'])):s.run(index)
            out.append({'id':f'{part}:{i}:{int(correct)}','prompt':s.request(),'label':int(correct),'part':part,'origin':'paired_programs'})
    return out


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--root',type=Path,required=True)
    ap.add_argument('--samples',type=Path);ap.add_argument('--action-prefix',action='store_true');a=ap.parse_args()
    source=a.source;root=a.root;root.mkdir(exist_ok=True,parents=True)
    folder=source/'export/selected-budget';manifest=json.loads((folder/'manifest.json').read_text());packet=folder/'model.mkqb'
    assert sha(packet)==manifest['packed_sha256'];vm=FullVM()
    rows=[{'id':r['id'],'prompt':r['prompt'],'label':int(r['grader_current_correct']),'part':'train','origin':'student_trajectory'}
          for r in read(source/'dagger-lessons.jsonl')]
    rows+=pairs(read(source/'train.jsonl'),'train',vm,48)
    rows+=pairs(read(source/'validation.jsonl'),'validation',vm)
    audit=json.loads((source/'results'/(manifest['strategy']+'-best.json')).read_text())
    for task in audit['tools']['details']:
        for i,h in enumerate(task['history']):
            if h['kind']=='done':rows.append({'id':task['id']+f':done:{i}','prompt':h['prompt'],
              'label':int(h['grader_program_correct_at_attempt']),'part':'observed_done_test','origin':'closed_exam_DONE'})
    if a.samples:rows=read(a.samples)
    with(root/'samples.jsonl').open('w')as f:
        for row in rows:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    torch.set_num_threads(4);torch.cuda.set_per_process_memory_fraction(.2);torch.backends.cuda.matmul.allow_tf32=False
    tokenizer=AutoTokenizer.from_pretrained(folder/'hf',local_files_only=True,trust_remote_code=False)
    model=AutoModelForCausalLM.from_pretrained(folder/'hf',local_files_only=True,trust_remote_code=False);load(model,packet);model.to('cuda').eval()
    prefix=[]
    if a.action_prefix:
        tags=[tokenizer.encode(t,add_special_tokens=False)for t in ['<write>','<patch>','<run>','<trace/>','<done/>']]
        for group in zip(*tags):
            if len(set(group))!=1:break
            prefix.append(group[0])
        assert prefix
    encoded=[tokenizer.encode(r['prompt'],add_special_tokens=False)+prefix for r in rows];features=[];kept=[];overflow=collections.Counter()
    for at in range(0,len(rows),16):
        indices=[i for i in range(at,min(at+16,len(rows)))if len(encoded[i])<1024]
        for i in range(at,min(at+16,len(rows))):
            if len(encoded[i])>=1024:overflow[rows[i]['part']]+=1
        if not indices:continue
        length=max(len(encoded[i])for i in indices);ids=torch.full((len(indices),length),tokenizer.pad_token_id or 0,dtype=torch.long,device='cuda');mask=torch.zeros_like(ids)
        for j,i in enumerate(indices):ids[j,-len(encoded[i]):]=torch.tensor(encoded[i],device='cuda');mask[j,-len(encoded[i]):]=1
        positions=(mask.cumsum(-1)-1).clamp_min(0)
        with torch.inference_mode():hidden=model.model(input_ids=ids,attention_mask=mask,position_ids=positions,use_cache=False).last_hidden_state[:,-1].float().cpu()
        features.append(hidden);kept+=indices
        if at%256==0:print(json.dumps({'features':len(kept),'of':len(rows)}),flush=True)
    x=torch.cat(features).double();labels=torch.tensor([rows[i]['label']for i in kept],dtype=torch.double)
    parts=[rows[i]['part']for i in kept];train=torch.tensor([p=='train'for p in parts]);val=torch.tensor([p=='validation'for p in parts]);test=torch.tensor([p=='observed_done_test'for p in parts])
    np.savez(root/'features.npz',features=x.numpy(),labels=labels.numpy(),indices=np.array(kept))
    mean=x[train].mean(0);scale=x[train].std(0).clamp_min(1e-5);z=(x-mean)/scale
    weights=torch.where(labels[train]>0,.5/labels[train].sum(),.5/(len(labels[train])-labels[train].sum()))
    candidates=[];fitted=[]
    for l2 in [.0001,.001,.01,.1,1.]:
        w=torch.zeros(x.shape[1],dtype=torch.double,requires_grad=True);b=torch.zeros((),dtype=torch.double,requires_grad=True)
        optimizer=torch.optim.LBFGS([w,b],max_iter=160,line_search_fn='strong_wolfe')
        def closure():
            optimizer.zero_grad();loss=(F.binary_cross_entropy_with_logits(z[train]@w+b,labels[train],reduction='none')*weights).sum()+.5*l2*w.square().sum()
            loss.backward();return loss
        optimizer.step(closure)
        with torch.no_grad():
            raw_w=w/scale;raw_b=b-(mean*raw_w).sum();logits=x@raw_w+raw_b
            threshold=float(logits[val & (labels==0)].max())+.01
            accepted=logits>=threshold;positive=val & (labels==1);negative=val & (labels==0)
            coverage=float(accepted[positive].double().mean());fp=int(accepted[negative].sum())
            row={'l2':l2,'validation_positive_coverage':coverage,'validation_false_accepts':fp,'threshold_logit':threshold,
                 'validation_positive_total':int(positive.sum()),'validation_negative_total':int(negative.sum())}
            candidates.append(row);fitted.append((raw_w.clone(),raw_b.clone(),logits.clone()));print(json.dumps(row),flush=True)
    best=max(range(len(candidates)),key=lambda i:(candidates[i]['validation_positive_coverage'],-candidates[i]['l2']))
    choice=candidates[best];w,b,logits=fitted[best];accepted=logits>=choice['threshold_logit']
    qualified=choice['validation_false_accepts']==0 and choice['validation_positive_coverage']>=.8
    result={'source_packet_sha256':sha(packet),'model_weights_modified':False,'train_samples':int(train.sum()),'validation_samples':int(val.sum()),
            'parameters':int(w.numel()+1),'float32_weight_bytes':int((w.numel()+1)*4),'qualified_for_integration':qualified,'feature_prefix_ids':prefix,
            'criterion':'zero validation false accepts and at least80% positive coverage; choice uses validation only',
            'candidates':candidates,'selected':choice,'context_overflows':dict(overflow),'physical_picocalc_measured':False,
            'observed_done_test':{'total':int(test.sum()),'correct_before':int((labels[test]==1).sum()),'wrong_before':int((labels[test]==0).sum()),
              'accepted_correct':int((accepted & test & (labels==1)).sum()),'accepted_wrong':int((accepted & test & (labels==0)).sum()),
              'used_for_selection':False,'observed_not_new_independent_benchmark':True},'oracle_labels_in_model_input':False}
    write(root/'probe.json',result);write(root/'head.json',{'weight':w.tolist(),'bias':float(b),'threshold_logit':choice['threshold_logit'],
      'source_packet_sha256':sha(packet),'qualified_for_integration':qualified,'feature_prefix_ids':prefix})
    assert sha(packet)==manifest['packed_sha256'];print(json.dumps(result),flush=True)


if __name__=='__main__':main()
