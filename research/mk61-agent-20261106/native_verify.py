"""Verify exact learned-scale exports and sample CPU / FP16-KV behavior."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import struct
import tempfile

import torch
from transformers import AutoModelForCausalLM,AutoTokenizer
from transformers.cache_utils import DynamicCache

from capacity_verify import FP16StorageCache
from course_eval import grading_tasks
from emulator import Emulator
from harness import check_program,extract_code
from lowbit import load
from native_export import packet
from native_quant import attach,restore_scales,export,plain_master,Learned2
from native_eval import read
from quantization import quantize_matrix


@torch.no_grad()
def verify_export(folder):
    manifest=json.loads((folder/'manifest.json').read_text());path=folder/'model.mkqb'
    mode=manifest.get('quantization_mode',manifest['arm'])
    assert hashlib.sha256(path.read_bytes()).hexdigest()==manifest['packed_sha256']
    for name,digest in manifest['checkpoint_files'].items():
        assert hashlib.sha256((folder/'hf'/name).read_bytes()).hexdigest()==digest
    qat=AutoModelForCausalLM.from_pretrained(folder/'hf',local_files_only=True,trust_remote_code=False)
    attach(qat,mode);restore_scales(qat,folder/'hf')
    header,payload=packet(path)
    with tempfile.TemporaryDirectory()as tmp:
        repacked=Path(tmp)/'model.mkqb';export(qat,repacked,mode)
        again,again_payload=packet(repacked)
        assert payload==again_payload and header['tensors']==again['tensors']
    model=plain_master(qat);expected={}
    for name,p in model.named_parameters():
        w=p.detach().clone()
        if w.ndim==2:
            quantizer=qat.get_submodule(name.rsplit('.',1)[0]).parametrizations.weight[0]
            if isinstance(quantizer,Learned2):
                amp=quantizer.amplitude().detach().cpu()
                codes=((w.reshape(w.shape[0],-1,32)/amp+1)*1.5).round().clamp(0,3)
                w=((codes*(2/3)-1)*amp).reshape_as(w)
            else:
                codes,amp=quantize_matrix(w);w=(codes*amp).reshape_as(w)
        expected[name]=w
    load(model,path)
    error=max(float((p-expected[name]).abs().max())for name,p in model.named_parameters())
    assert error==0.,error
    report={'sha256_verified':True,'checkpoint_hashes_verified':True,
            'reexport_payload_identical':True,'reload_max_error':error,
            'packed_bytes':path.stat().st_size,'parameters':sum(p.numel()for p in model.parameters())}
    return model.eval(),report


def generate(model,tokenizer,prompt,half=False):
    ids=tokenizer.encode(prompt,add_special_tokens=False)
    assert len(ids)+128<=model.config.max_position_embeddings,'Never silently truncate a long probe'
    inputs=torch.tensor([ids]);cache=(FP16StorageCache if half else DynamicCache)(config=model.config)
    with torch.inference_mode():
        output=model.generate(input_ids=inputs,attention_mask=torch.ones_like(inputs),past_key_values=cache,
          max_new_tokens=128,do_sample=False,use_cache=True,pad_token_id=tokenizer.pad_token_id or 0,
          eos_token_id=tokenizer.eos_token_id)
    stored=sum(layer.keys.numel()*layer.keys.element_size()+layer.values.numel()*layer.values.element_size()for layer in cache.layers)
    tokens=cache.get_seq_length();element_bytes=2 if half else 4
    expected=tokens*2*model.config.num_hidden_layers*model.config.num_key_value_heads*model.config.head_dim*element_bytes
    assert stored==expected,(stored,expected)
    if half:assert all(layer.keys.dtype==layer.values.dtype==torch.float16 for layer in cache.layers)
    return tokenizer.decode(output[0,len(ids):],skip_special_tokens=True),{'bytes':stored,'tokens':tokens,
             'prompt_tokens':len(ids),'fp16_storage':half}


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args()
    torch.set_num_threads(2);root=a.root
    exports={};chosen=None
    for folder in sorted((root/'export').iterdir()):
        model,report=verify_export(folder);exports[folder.name]=report
        if folder.name=='selected-budget':chosen=model
    selected=json.loads((root/'final-export.json').read_text())['selected_arm']
    tokenizer=AutoTokenizer.from_pretrained(root/'export/selected-budget/hf',local_files_only=True,trust_remote_code=False)
    fresh=json.loads((root/(selected+'-fresh.json')).read_text())
    tasks={t['id']:t for t in grading_tasks(read(root/'fresh-level1.jsonl')+read(root/'fresh-level2.jsonl'))}
    groups=collections.defaultdict(list)
    for row in fresh['metrics']['manual']['program']['details']:groups[tasks[row['id']]['expression'][0]].append(row)
    probes=[('manual',r)for values in groups.values()for r in values[:2]]
    for part in ['context1024','context2048','composed']:
        details=fresh['metrics'][part]['program']['details']
        for index in [0,3,8]if part!='composed'else[0,1]:
            if index<len(details):probes.append((part,details[index]))
    rows=[];em=Emulator()
    for part,row in probes:
        reply,fp32=generate(chosen,tokenizer,row['prompt'])
        half_reply,fp16=generate(chosen,tokenizer,row['prompt'],True)
        code=extract_code(half_reply);task=tasks[row['id']]
        passed=bool(code and'<run/>'in half_reply and check_program(em,code,task['public_tests']+task['hidden_tests'])['pass'])
        rows.append({'part':part,'id':row['id'],'cpu_matches_b200':reply==row['reply'],
          'fp16_matches_fp32_reply':half_reply==reply,'fp16_program_pass':passed,'original_program_pass':row['pass'],
          'fp32_cache':fp32,'fp16_cache':fp16,'cpu_reply':reply,'b200_reply':row['reply'],'fp16_reply':half_reply})
        print(json.dumps({'checked':len(rows),'total':len(probes),'part':part}),flush=True)
    frozen=json.loads((root/'frozen.json').read_text())
    for name,entry in frozen['files'].items():assert hashlib.sha256((root/name).read_bytes()).hexdigest()==entry['sha256']
    result={'exports':exports,'selected_arm':selected,'compared':len(rows),
      'cpu_b200_reply_matches':sum(r['cpu_matches_b200']for r in rows),
      'fp16_fp32_reply_matches':sum(r['fp16_matches_fp32_reply']for r in rows),
      'fp16_program_passes':sum(r['fp16_program_pass']for r in rows),
      'original_program_passes':sum(r['original_program_pass']for r in rows),
      'fp16_kv_storage_and_byte_count_verified':True,'frozen_files_hashes_verified':True,
      'max_probed_prompt_tokens':max(r['fp16_cache']['prompt_tokens']for r in rows),
      'attention_math':'Host FP32 with persistent FP16 key/value tensors in the half-storage probe',
      'details':rows,'native_device_inference_measured':False}
    (root/'local-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items()if k!='details'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
