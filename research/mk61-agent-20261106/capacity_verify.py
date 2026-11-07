"""Local packed reload, CPU/B200 replies, and actual FP16 KV storage probes."""
import argparse
import collections
import hashlib
import json
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM,AutoTokenizer
from transformers.cache_utils import DynamicCache

from course_eval import grading_tasks
from emulator import Emulator
from evaluate import read_tasks
from harness import check_program,extract_code
from lowbit import load,quantize,bits_for
from prompt_variants import without_public_examples
from quantization import load_q4,quantize_matrix


class FP16StorageCache(DynamicCache):
    def update(self,keys,values,layer_idx,*args,**kwargs):
        key_dtype,value_dtype=keys.dtype,values.dtype
        cached_keys,cached_values=super().update(keys.to(torch.float16),values.to(torch.float16),layer_idx,*args,**kwargs)
        return cached_keys.to(key_dtype),cached_values.to(value_dtype)


def generate(model,tokenizer,prompt,half=False):
    prompt=without_public_examples(prompt).replace('<plan>краткий план</plan>','').replace('<plan>взять R0 и R1; сложить</plan>','')
    ids=tokenizer.encode(prompt,add_special_tokens=False)[-384:]
    inputs=torch.tensor([ids]);cache=(FP16StorageCache if half else DynamicCache)(config=model.config)
    with torch.inference_mode():
        out=model.generate(input_ids=inputs,attention_mask=torch.ones_like(inputs),past_key_values=cache,
              max_new_tokens=128,do_sample=False,use_cache=True,pad_token_id=tokenizer.pad_token_id or 0,eos_token_id=tokenizer.eos_token_id)
    stored=sum(layer.keys.numel()*layer.keys.element_size()+layer.values.numel()*layer.values.element_size()for layer in cache.layers)
    if half:
        assert all(layer.keys.dtype==layer.values.dtype==torch.float16 for layer in cache.layers)
        expected=cache.get_seq_length()*2*model.config.num_hidden_layers*model.config.num_key_value_heads*model.config.head_dim*2
        assert stored==expected,(stored,expected)
    return tokenizer.decode(out[0,len(ids):],skip_special_tokens=True),{'bytes':stored,'tokens':cache.get_seq_length(),'fp16_storage':half}


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();torch.set_num_threads(2)
    exports={};chosen_model=None;chosen_tokenizer=None
    for folder in sorted((a.root/'export').iterdir()):
        manifest=json.loads((folder/'manifest.json').read_text());mode=manifest['format']
        weights=folder/('model.mkq4'if mode=='q4'else'model.mkqb')
        assert hashlib.sha256(weights.read_bytes()).hexdigest()==manifest['packed_sha256']
        model=AutoModelForCausalLM.from_pretrained(folder/'hf',local_files_only=True,trust_remote_code=False).eval()
        raw={n:x.detach().clone()for n,x in model.named_parameters()}
        if mode=='q4':load_q4(model,weights)
        else:load(model,weights)
        error=0.
        for name,value in model.named_parameters():
            w=raw[name]
            if w.ndim==2:
                if mode=='q4':codes,scales=quantize_matrix(w);expected=(codes*scales).reshape_as(w)
                else:expected=quantize(w,bits_for(name,mode))[2]
            else:expected=w
            error=max(error,float((value-expected).abs().max().detach()))
        assert error==0.
        exports[folder.name]={'sha256_verified':True,'reload_max_error':error,'bytes':weights.stat().st_size}
        if folder.name=='selected-budget':
            chosen_model=model;chosen_tokenizer=AutoTokenizer.from_pretrained(folder/'hf',local_files_only=True,trust_remote_code=False)
    final=json.loads((a.root/'final-export.json').read_text());choice=final['chosen_under_weight_ceiling'];arm=choice['arm'];mode=choice['format'];kind=choice['kind']
    label=arm+'-q4-fresh'if mode=='q4'else arm+'-'+mode+'-'+kind+'-fresh'
    report=json.loads((a.root/'results'/(label+'.json')).read_text());details=report['metrics']['manual']['program']['details']
    groups=collections.defaultdict(list)
    tasks={t['id']:t for t in grading_tasks(read_tasks(a.root/f'level{final["primary_level"]}-fresh.jsonl'))}
    for row in details:groups[tasks[row['id']]['expression'][0]].append(row)
    probes=[row for group in groups.values()for row in group[:2]]
    for row in details:
        if len(probes)>=16:break
        if row not in probes:probes.append(row)
    rows=[];em=Emulator()
    for row in probes:
        prompt=row['history'][0]['prompt'];reply,fp32=generate(chosen_model,chosen_tokenizer,prompt)
        half_reply,fp16=generate(chosen_model,chosen_tokenizer,prompt,True)
        code=extract_code(half_reply);task=tasks[row['id']]
        half_pass=bool(code and'<run/>'in half_reply and check_program(em,code,task['public_tests']+task['hidden_tests'])['pass'])
        rows.append({'id':row['id'],'cpu_matches_b200':reply==row['history'][0]['reply'],
          'fp16_matches_fp32_reply':half_reply==reply,'fp16_program_pass':half_pass,'original_program_pass':row['pass'],
          'fp32_cache':fp32,'fp16_cache':fp16,'cpu_reply':reply,'b200_reply':row['history'][0]['reply'],'fp16_reply':half_reply})
        print(json.dumps({'checked':len(rows),'total':len(probes)}),flush=True)
    result={'exports':exports,'compared':len(rows),'cpu_b200_reply_matches':sum(r['cpu_matches_b200']for r in rows),
      'fp16_fp32_reply_matches':sum(r['fp16_matches_fp32_reply']for r in rows),'fp16_kv_storage_and_byte_count_verified':True,
      'details':rows,'native_device_inference_measured':False,'attention_math':'Host FP32; persistent keys/values FP16 in the half-storage probe'}
    (a.root/'local-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items()if k!='details'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
