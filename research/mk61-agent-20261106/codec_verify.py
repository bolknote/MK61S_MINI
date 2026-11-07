"""Exact eight-export reloads, H32 boundary checks and real FP16 cache replay."""
import argparse
import collections
import json
from pathlib import Path

import torch
from transformers import AutoTokenizer
from transformers.cache_utils import DynamicCache

from capacity_verify import FP16StorageCache
from codec_common import ARMS,MODES,Protocol,compact_head,sha,read,OLD_VOCAB
from course_eval import grading_tasks
from emulator import Emulator
from harness import extract_code,check_program
from native_verify import verify_export


def generate(model,tokenizer,prompt,p,half=False):
    prompt=p.encode_text(prompt);ids=tokenizer.encode(prompt,add_special_tokens=False)
    limit=min(160,model.config.max_position_embeddings-len(ids));assert limit>0
    cache=(FP16StorageCache if half else DynamicCache)(config=model.config)
    inputs=torch.tensor([ids]);mask=torch.ones_like(inputs)
    with torch.inference_mode():out=model.generate(input_ids=inputs,attention_mask=mask,past_key_values=cache,max_new_tokens=limit,
      do_sample=False,use_cache=True,pad_token_id=tokenizer.pad_token_id or 0,eos_token_id=tokenizer.eos_token_id)
    tokens=out[0,len(ids):].tolist()
    if tokenizer.eos_token_id in tokens:tokens=tokens[:tokens.index(tokenizer.eos_token_id)]
    raw=tokenizer.decode(tokens,skip_special_tokens=True,clean_up_tokenization_spaces=False)
    reply,error=p.decode_reply(raw)
    stored=sum(layer.keys.numel()*layer.keys.element_size()+layer.values.numel()*layer.values.element_size()for layer in cache.layers)
    expected=cache.get_seq_length()*2*model.config.num_hidden_layers*model.config.num_key_value_heads*model.config.head_dim*(2 if half else 4)
    assert stored==expected
    if half:assert all(layer.keys.dtype==layer.values.dtype==torch.float16 for layer in cache.layers)
    return {'raw_reply':raw,'reply':reply,'codec_error':error,'generated_token_ids':tokens,
      'cache':{'bytes':stored,'tokens':cache.get_seq_length(),'prompt_tokens':len(ids),'fp16':half}}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();root=a.root.resolve()
    torch.set_num_threads(4);exports={};candidates={}
    for role in ['endpoint','best']:
        for folder in sorted((root/'export'/role).iterdir()):
            model,report=verify_export(folder);manifest=json.loads((folder/'manifest.json').read_text())
            for filename,field in [('codebook-32.json','codebook_sha256'),('output-token-ids.json','output_ids_sha256'),('prompt-template.txt','prompt_template_sha256')]:assert sha(folder/filename)==manifest[field]
            exports[role+'/'+folder.name]=report
            if role=='endpoint':candidates[folder.name]=model
    tasks={t['id']:t for t in grading_tasks([t for level in [1,2,3]for t in read(root/f'fresh{level}.jsonl')])}
    rows=[];em=Emulator()
    for name,model in candidates.items():
        arm,mode=name.split('-');folder=root/'export/endpoint'/name
        tokenizer=AutoTokenizer.from_pretrained(folder/'hf',local_files_only=True,trust_remote_code=False)
        assert len(tokenizer)==OLD_VOCAB+32
        ids=json.loads((folder/'output-token-ids.json').read_text());compact_head(model,ids)
        p=Protocol(mode,json.loads((folder/'codebook-32.json').read_text()))
        result=json.loads((root/f'results/{name}-endpoint.json').read_text());probes=[]
        for part in ['manual1','manual2','manual3']:
            groups=collections.defaultdict(list)
            for row in result['metrics'][part]['program']['details']:groups[tasks[row['id']]['expression'][0]].append(row)
            probes += [(part,values[0])for values in groups.values()]
        for part in ['context1024','context2048']:probes += [(part,row)for row in result['metrics'][part]['program']['details'][:2]]
        for part,row in probes:
            full=generate(model,tokenizer,row['prompt'],p);half=generate(model,tokenizer,row['prompt'],p,True)
            code=extract_code(half['reply']);task=tasks[row['id']]
            passed=bool(code and'<run/>'in half['reply']and half['codec_error']is None and check_program(em,code,task['public_tests']+task['hidden_tests'])['pass'])
            rows.append({'variant':name,'part':part,'id':row['id'],
              'cpu_matches_b200_token_ids':full['generated_token_ids']==row['generated_token_ids'],
              'fp16_matches_fp32_token_ids':full['generated_token_ids']==half['generated_token_ids'],
              'fp16_program_pass':passed,'original_program_pass':row['pass'],'cpu':full,'half':half})
            if len(rows)%10==0:print(json.dumps({'cpu_kv_probes':len(rows)}),flush=True)
    frozen=json.loads((root/'frozen.json').read_text())
    for name,item in frozen['files'].items():assert sha(root/name)==item['sha256']
    result={'exports':exports,'compared':len(rows),'cpu_b200_matches':sum(x['cpu_matches_b200_token_ids']for x in rows),
      'fp16_fp32_matches':sum(x['fp16_matches_fp32_token_ids']for x in rows),'fp16_kv_byte_count_verified':True,
      'frozen_files_verified':True,'max_actual_prompt_tokens':max(x['half']['cache']['prompt_tokens']for x in rows),
      'details':rows,'native_picocalc_measured':False}
    (root/'local-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items()if k not in ['details','exports']},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
