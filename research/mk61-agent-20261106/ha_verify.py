"""Exact Q4 reload, CPU/FP16 replay and a native 1024-token harness boundary."""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import shutil
import struct
import time

import torch
from safetensors.torch import load_file
from transformers import AutoTokenizer
from transformers.cache_utils import DynamicCache

from ha_common import HERE,sha,write,compact_head
from ha_protocol import constants,parse_call,assemble
from ha_runtime import Session
from full_isa_common import read
from full_isa_vm import FullVM,check_task
from ha_native_check import verify_all as verify_frontend,cpp_assemble
from capacity_verify import FP16StorageCache
from native_verify import verify_export
from native_export import packet
from codec_native import prepare_source,native_tokenizer
from codec_common import ROOT as CODEC_ROOT

LABELS=[arm+'-'+role for arm in ['direct','asm']for role in ['baseline','best','endpoint']]


def generate(model,tokenizer,text,half=False):
    ids=tokenizer.encode(text,add_special_tokens=False);limit=min(512,1024-len(ids));assert limit>0
    cache=(FP16StorageCache if half else DynamicCache)(config=model.config);inputs=torch.tensor([ids])
    with torch.inference_mode():
        output=model.generate(input_ids=inputs,attention_mask=torch.ones_like(inputs),past_key_values=cache,
          max_new_tokens=limit,do_sample=False,use_cache=True,pad_token_id=tokenizer.pad_token_id or 0,eos_token_id=tokenizer.eos_token_id)
    tokens=output[0,len(ids):].tolist()
    if tokenizer.eos_token_id in tokens:tokens=tokens[:tokens.index(tokenizer.eos_token_id)]
    stored=sum(x.keys.numel()*x.keys.element_size()+x.values.numel()*x.values.element_size()for x in cache.layers)
    expected=cache.get_seq_length()*2*model.config.num_hidden_layers*model.config.num_key_value_heads*model.config.head_dim*(2 if half else 4)
    assert stored==expected
    if half:assert all(x.keys.dtype==x.values.dtype==torch.float16 for x in cache.layers)
    return {'reply':tokenizer.decode(tokens,skip_special_tokens=True,clean_up_tokenization_spaces=False),
      'generated_token_ids':tokens,'cache':{'bytes':stored,'tokens':cache.get_seq_length(),'prompt_tokens':len(ids),'fp16':half}}


def probes(report):
    selected=[]
    for opcode in [0x1C,0xA4,0x53]:selected.append(next(r for r in report['isa']['details']if r.get('opcode')==opcode and r['angle']=='RAD'))
    for group in ['literal_copy','literal_function','composition','algorithm_clamp']:
        selected.append(next(r for r in report['language']['details']if r['group']==group))
    selected.append(next(r for r in report['observed_user_reproductions']['details']if r['id']=='user-repro:sin:DEG:22'))
    for kind in ['trace','patch','run','done']:
        found=next((h for t in report['tools']['details']for h in t['history']if h.get('kind')==kind and 'prompt'in h),None)
        if found:selected.append({'id':'tool:'+kind,**found})
    return selected


def embedding(folder):
    weights=load_file(str(folder/'hf/model.safetensors'));key=next(k for k in weights if k.endswith('embed_tokens.weight'));return weights[key]


def agent_probes(root,models):
    tasks=read(root/'fresh.jsonl');groups={}
    for task in tasks:groups.setdefault(task['group'],[]).append(task)
    chosen=[t for values in groups.values()for t in values[:2]];result={};vm=FullVM()
    for arm in ['direct','asm']:
        label=arm+'-best';model=models[label];folder=root/'export'/label
        tokenizer=AutoTokenizer.from_pretrained(folder/'hf',local_files_only=True,trust_remote_code=False);details=[]
        for task in chosen:
            session=Session(task,arm,vm=vm)
            for _ in range(5):
                request=session.request()
                try:row=generate(model,tokenizer,request)
                except AssertionError:session.history.append({'kind':'context_overflow'});break
                session.apply(row['reply'])
                if session.finished:break
            try:code=assemble(session.body,session.pool,arm);correct=check_task(vm,code,task)['pass']
            except (ValueError,RuntimeError,ArithmeticError,TypeError):code=None;correct=False
            details.append({'id':task['id'],'pass':bool(correct and session.finished),'program_correct':bool(correct),
              'finished':session.finished,'history':session.history})
        result[arm]={'passed':sum(x['pass']for x in details),'program_correct':sum(x['program_correct']for x in details),
          'total':len(details),'details':details,'cpu_only':True,'initial_program_supplied':False,
          'oracle_answers_in_feedback':False,'used_for_selection':False}
        write(root/'agent-from-scratch.json',result)
    return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();root=a.root.resolve();torch.set_num_threads(4)
    frontend=verify_frontend(root,root/'native-frontend')
    from ha_native_check import library
    frontend_lib=library(root/'native-frontend')
    exports={};models={};reports={};rows={};checks=[];aliases={};payloads={}
    for label in LABELS:
        folder=root/'export'/label;model,info=verify_export(folder);exports[label]=info
        manifest=json.loads((folder/'manifest.json').read_text());report=json.loads((root/'results'/(label+'.json')).read_text());reports[label]=report
        assert report['packed_sha256']==manifest['packed_sha256']
        assert sha(folder/'output-token-ids.json')==manifest['output_ids_sha256']and sha(folder/'prompt-template.txt')==manifest['prompt_template_sha256']
        payload_hash=manifest['payload_sha256']
        if payload_hash in payloads:aliases[label]=payloads[payload_hash]
        else:payloads[payload_hash]=label
        compact_head(model,json.loads((folder/'output-token-ids.json').read_text()));models[label]=model;rows[label]=probes(report)
        tokenizer=AutoTokenizer.from_pretrained(folder/'hf',local_files_only=True,trust_remote_code=False)
        for row in rows[label]:
            full=generate(model,tokenizer,row['prompt']);half=generate(model,tokenizer,row['prompt'],True)
            checks.append({'label':label,'id':row['id'],'cpu_b200_tokens_equal':full['generated_token_ids']==row['generated_token_ids'],
              'fp16_fp32_tokens_equal':half['generated_token_ids']==full['generated_token_ids'],'cpu':full,'half':half})
        print(json.dumps({'cpu_verified':label,'probes':len(rows[label])}),flush=True)
    for name in ['data-frozen.json','prepared.json']:
        data=json.loads((root/name).read_text())
        for filename,digest in data['files'].items():assert sha(root/filename)==digest
    frozen=json.loads((root/'data-frozen.json').read_text())
    for filename,digest in frozen['private_core_files'].items():assert sha(root/'core-source'/filename)==digest
    baseline_label=next(label for label in LABELS if label.endswith('-baseline'))
    original=embedding(root/'export'/baseline_label);ids=json.loads((root/'output-token-ids.json').read_text())
    mask=torch.ones(original.shape[0],dtype=torch.bool);mask[ids]=False
    digest=hashlib.sha256(original[mask].contiguous().numpy().tobytes()).hexdigest();protected={}
    for label in LABELS:
        actual=embedding(root/'export'/label);actual_hash=hashlib.sha256(actual[mask].contiguous().numpy().tobytes()).hexdigest()
        assert actual_hash==digest
        protected[label]={'bit_identical':True,'rows':int(mask.sum()),'sha256':actual_hash}
    local={'exports':exports,'details':checks,'compared':len(checks),'cpu_b200_matches':sum(x['cpu_b200_tokens_equal']for x in checks),
      'fp16_fp32_matches':sum(x['fp16_fp32_tokens_equal']for x in checks),'protected_rows':protected,'frozen_inputs_verified':True,
      'fp16_cache_bytes_verified':True,'unique_weight_payloads':len(payloads),'identical_payload_aliases':aliases,
      'different_protocols_tested_even_when_weights_identical':True,'physical_picocalc_measured':False}
    write(root/'local-verification.json',local)
    assert local['cpu_b200_matches']==len(checks),'Inspect CPU/B200 differences'
    out=root/'native';out.mkdir(exist_ok=True);book=json.loads((CODEC_ROOT/'codebook-32.json').read_text())
    source,path,exporter=prepare_source(root,out,book);lib=C.CDLL(str(path))
    lib.mk_ai_open.argtypes=[C.c_void_p,C.c_uint];lib.codec_set_mask.argtypes=[C.POINTER(C.c_ushort),C.c_uint]
    lib.codec_forward.argtypes=[C.c_ushort,C.c_int,C.POINTER(C.c_ushort),C.POINTER(C.c_float)]
    lib.codec_encode.argtypes=[C.c_char_p,C.POINTER(C.c_ushort),C.c_uint,C.POINTER(C.c_uint)]
    native={}
    # C++ inference consumes the exact audited packet payload; only context metadata changes.
    for label in LABELS:
        folder=root/'export'/label;arm=label.split('-')[0];hf=folder/'hf';adapted=out/(label+'-tokenizer.json');native_tokenizer(hf,adapted)
        header,payload=packet(folder/'model.mkqb');header['config']['max_position_embeddings']=1024
        raw=json.dumps(header,ensure_ascii=False,separators=(',',':')).encode();derived=out/(label+'-context1024.mkqb')
        derived.write_bytes(b'MKQBv1\0\0'+struct.pack('<I',len(raw))+raw+payload);assert packet(derived)[1]==payload
        package=folder/'model.mka';exporter.export(derived,adapted,package,'lut');data=package.read_bytes();buffer=C.create_string_buffer(data)
        assert lib.mk_ai_open(buffer,len(data))==0
        allowed=json.loads((folder/'output-token-ids.json').read_text());head=(C.c_ushort*len(allowed))(*allowed);lib.codec_set_mask(head,len(allowed))
        tokenizer=AutoTokenizer.from_pretrained(hf,local_files_only=True,trust_remote_code=False);encoded=(C.c_ushort*1024)();count=C.c_uint();best=C.c_ushort();details=[]
        for row in rows[label]:
            inputs=tokenizer.encode(row['prompt'],add_special_tokens=False)
            assert lib.codec_encode(row['prompt'].encode(),encoded,1024,C.byref(count))==0 and list(encoded[:count.value])==inputs
            lib.mk_ai_reset();started=time.perf_counter()
            for i,token in enumerate(inputs):assert lib.codec_forward(token,int(i+1==len(inputs)),C.byref(best),None)==0
            prefill=time.perf_counter()-started;started=time.perf_counter();tokens=[]
            for _ in range(min(512,1024-len(inputs))):
                token=best.value
                if token==tokenizer.eos_token_id:break
                tokens.append(token);assert lib.codec_forward(token,1,C.byref(best),None)==0
            details.append({'id':row['id'],'tokens_match_b200':tokens==row['generated_token_ids'],'tokens':tokens,
              'input_tokens':len(inputs),'prefill_seconds':prefill,'decode_seconds':time.perf_counter()-started})
        record={'native_generations_match':sum(x['tokens_match_b200']for x in details),'probes':len(details),'details':details,
          'package_sha256':sha(package),'package_bytes':len(data),'native_tokenizer_matches':len(details),'native_cache_bytes':lib.mk_ai_cache(),
          'workspace_bytes':lib.mk_ai_workspace(),'package_plus_kv_workspace_bytes':len(data)+lib.mk_ai_cache()+lib.mk_ai_workspace(),
          'working_context':1024,'native_kv_storage':'FP32','source_packet_sha256':sha(folder/'model.mkqb'),
          'derived_context_packet_sha256':sha(derived),'audited_weights_payload_unchanged':True,'physical_picocalc_measured':False}
        native[label]=record;write(folder/'native-info.json',record)
        for filename in ['ha_native.hpp','ha_native_probe.cpp']:shutil.copyfile(HERE/filename,folder/'runtime'/filename)
        write(folder/'runtime/frontend-verification.json',frontend)
        shutil.copyfile(package,folder/'model-context1024.mka')
        write(root/'native-verification.json',{'models':native,'frontend':frontend,'physical_picocalc_measured':False})
        assert record['native_generations_match']==len(details),'Native mismatch: '+label
        print(json.dumps({'native_verified':label,'matches':record['native_generations_match'],'probes':len(details)}),flush=True)
    selected=json.loads((root/'final-export.json').read_text())['selected_label']
    for name in ['model.mka','model-context1024.mka','native-info.json']:shutil.copyfile(root/'export'/selected/name,root/'export/selected-budget'/name)
    shutil.copytree(root/'export'/selected/'runtime',root/'export/selected-budget/runtime',dirs_exist_ok=True)
    write(root/'native-verification.json',{'models':native,'selected_label':selected,'frontend':frontend,
      'source_sha256':{p.name:sha(p)for p in source.iterdir()if p.is_file()},'physical_picocalc_measured':False})
    agent_probes(root,models)
    print(json.dumps({'verification_complete':True,'cpu_matches':local['cpu_b200_matches'],'half_matches':local['fp16_fp32_matches'],'probes':len(checks)}),flush=True)


if __name__=='__main__':main()
