"""Verify the audited full-ISA weights on CPU and a private native runtime."""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import shutil
import struct

import torch
from safetensors.torch import load_file
from transformers import AutoTokenizer
from transformers.cache_utils import DynamicCache

from capacity_verify import FP16StorageCache
from full_isa_common import HexProtocol, compact_head, read, sha, write, task_prompt
from full_isa_protocol import decode
from full_isa_vm import FullVM, check_task
from native_verify import verify_export
from native_export import packet
from codec_common import ROOT as CODEC_ROOT
from codec_native import prepare_source, native_tokenizer
from native_context import wrap

LABELS=['baseline','full-best','full-endpoint','protected-best','protected-endpoint']


def generate(model, tokenizer, text, half=False, *, context_limit=None):
    ids=tokenizer.encode(text,add_special_tokens=False)
    limit=min(352,(context_limit or model.config.max_position_embeddings)-len(ids))
    assert limit>0, 'Never truncate the input'
    cache=(FP16StorageCache if half else DynamicCache)(config=model.config)
    inputs=torch.tensor([ids])
    with torch.inference_mode():
        output=model.generate(input_ids=inputs,attention_mask=torch.ones_like(inputs),past_key_values=cache,
          max_new_tokens=limit,do_sample=False,use_cache=True,pad_token_id=tokenizer.pad_token_id or 0,
          eos_token_id=tokenizer.eos_token_id)
    tokens=output[0,len(ids):].tolist()
    if tokenizer.eos_token_id in tokens:tokens=tokens[:tokens.index(tokenizer.eos_token_id)]
    stored=sum(x.keys.numel()*x.keys.element_size()+x.values.numel()*x.values.element_size() for x in cache.layers)
    expected=cache.get_seq_length()*2*model.config.num_hidden_layers*model.config.num_key_value_heads*model.config.head_dim*(2 if half else 4)
    assert stored==expected
    if half:assert all(x.keys.dtype==x.values.dtype==torch.float16 for x in cache.layers)
    return {'reply':tokenizer.decode(tokens,skip_special_tokens=True,clean_up_tokenization_spaces=False),
      'generated_token_ids':tokens,'cache':{'bytes':stored,'tokens':cache.get_seq_length(),'prompt_tokens':len(ids),'fp16':half}}


def choose_probes(audit):
    rows=audit['main']['details'];chosen=[]
    for opcode in [0x1C,0x24,0xA4,0x57,0x5B]:
        chosen.append(next(r for r in rows if r.get('opcode')==opcode and r['angle']=='RAD'))
    for kind in ['numeric_synthesis','programming','interactive_game']:
        chosen.append(next(r for r in rows if r['kind']==kind))
    chosen.append(next(r for r in audit['observed_user_reproductions']['details']
      if r['angle']=='DEG' and '22' in r['prompt'] and 'синус' in r['prompt'].lower()))
    return chosen


def raw_embedding(folder):
    weights=load_file(str(folder/'hf/model.safetensors'))
    key=next(k for k in weights if k.endswith('embed_tokens.weight'))
    return weights[key]


def context_check(root, model, tokenizer):
    tasks=read(root/'audit.jsonl');selected=[]
    for op in [0x1C,0x18,0x21,0x24]:
        selected.append(next(t for t in tasks if t.get('opcode')==op and t['angle']=='RAD'))
    selected += [t for t in tasks if t['kind']=='numeric_synthesis'][:4]
    for group in ['branch_programs','loop_programs','memory_programs','subroutine_programs']:
        selected.append(next(t for t in tasks if t['group']==group))
    vm=FullVM();details=[]
    for index,task in enumerate(selected):
        row={'id':task['id'],'results':{}}
        for context in [512,1024,2048]:
            text=wrap(task['task'],tokenizer,context,6117600+index,audit=True)
            prompt=task_prompt({**task,'task':text})
            output=generate(model,tokenizer,prompt,context_limit=context)
            try:ok=check_task(vm,decode(output['reply']),task)['pass']
            except (ValueError,RuntimeError,ArithmeticError):ok=False
            row['results'][str(context)]={'pass':bool(ok),**output}
        details.append(row)
    short=sum(x['results']['512']['pass']for x in details)
    scores={}
    for n in [1024,2048]:
        retained=sum(x['results']['512']['pass'] and x['results'][str(n)]['pass']for x in details)
        scores[str(n)]={'solved_short':short,'retained_long':retained,'total':len(details),
          'conditional_retention':retained/short if short else None,
          'max_prompt_tokens':max(x['results'][str(n)]['cache']['prompt_tokens']for x in details)}
    result={'scores':scores,'details':details,'cpu_only':True,'used_for_selection':False,
      'same_tasks_short_and_long':True,'irrelevant_notes_not_general_agent_memory':True}
    write(root/'context-verification.json',result)
    return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);args=ap.parse_args();root=args.root.resolve()
    torch.set_num_threads(4)
    selection=json.loads((root/'final-export.json').read_text());selected=selection['selected_label']
    exports={};models={};audits={};probes={};checks=[];payload_labels={};aliases={}
    for label in LABELS:
        folder=root/'export'/label
        model,record=verify_export(folder);exports[label]=record
        manifest=json.loads((folder/'manifest.json').read_text())
        payload_hash=manifest['payload_sha256']
        if payload_hash in payload_labels:aliases[label]=payload_labels[payload_hash]
        else:payload_labels[payload_hash]=label
        assert sha(folder/'output-token-ids.json')==manifest['output_ids_sha256']
        assert sha(folder/'prompt-template.txt')==manifest['prompt_template_sha256']
        audit=json.loads((root/'results'/(label+'.json')).read_text());audits[label]=audit
        assert audit['packed_sha256']==manifest['packed_sha256']
        compact_head(model,json.loads((folder/'output-token-ids.json').read_text()))
        models[label]=model;probes[label]=choose_probes(audit)
        tokenizer=AutoTokenizer.from_pretrained(folder/'hf',local_files_only=True,trust_remote_code=False)
        for row in probes[label]:
            full=generate(model,tokenizer,row['prompt']);half=generate(model,tokenizer,row['prompt'],True)
            checks.append({'label':label,'id':row['id'],'cpu_b200_tokens_equal':full['generated_token_ids']==row['generated_token_ids'],
              'fp16_fp32_tokens_equal':half['generated_token_ids']==full['generated_token_ids'],'cpu':full,'half':half})
        print(json.dumps({'cpu_verified':label,'probes':len(probes[label])}),flush=True)
    for name in ['prepared.json','data-frozen.json','run-policy-frozen.json']:
        item=json.loads((root/name).read_text())
        for filename,digest in item['files'].items():assert sha(root/filename)==digest
    policy=json.loads((root/'run-policy-frozen.json').read_text())
    for filename,digest in policy['private_core_files'].items():assert sha(root/'core-source'/filename)==digest
    original=raw_embedding(root/'export/baseline');ids=json.loads((root/'export/baseline/output-token-ids.json').read_text())
    mask=torch.ones(original.shape[0],dtype=torch.bool);mask[ids]=False;protected={}
    original_rows_sha=hashlib.sha256(original[mask].contiguous().numpy().tobytes()).hexdigest()
    for label in ['protected-best','protected-endpoint']:
        actual=raw_embedding(root/'export'/label)
        digest=hashlib.sha256(actual[mask].contiguous().numpy().tobytes()).hexdigest()
        protected[label]={'unchanged_rows':int(mask.sum()),'bit_identical_to_original':digest==original_rows_sha,
          'sha256':digest,'original_sha256':original_rows_sha}
        assert protected[label]['bit_identical_to_original']
    result={'exports':exports,'cpu_cache_probes':checks,'cpu_b200_matches':sum(x['cpu_b200_tokens_equal']for x in checks),
      'fp16_fp32_matches':sum(x['fp16_fp32_tokens_equal']for x in checks),'compared':len(checks),'frozen_inputs_verified':True,
      'fp16_byte_count_verified':True,'protected_input_embeddings':protected,'physical_picocalc_measured':False,
      'unique_weight_payloads':len(payload_labels),'identical_payload_aliases':aliases,
      'probes_excluding_identical_payloads':sum(x['label']not in aliases for x in checks)}
    write(root/'local-verification.json',result)
    assert result['cpu_b200_matches']==len(checks),'CPU/B200 mismatch; inspect local-verification.json'
    # Native source is the prior research snapshot, never changing product files.
    out=root/'native';out.mkdir(exist_ok=True);book=json.loads((CODEC_ROOT/'codebook-32.json').read_text())
    source,library,exporter=prepare_source(root,out,book);lib=C.CDLL(str(library))
    lib.mk_ai_open.argtypes=[C.c_void_p,C.c_uint];lib.codec_set_mask.argtypes=[C.POINTER(C.c_ushort),C.c_uint]
    lib.codec_forward.argtypes=[C.c_ushort,C.c_int,C.POINTER(C.c_ushort),C.POINTER(C.c_float)]
    lib.codec_encode.argtypes=[C.c_char_p,C.POINTER(C.c_ushort),C.c_uint,C.POINTER(C.c_uint)]
    native={}
    for label in LABELS:
        folder=root/'export'/label;hf=folder/'hf';adapted=out/(label+'-tokenizer.json');native_tokenizer(hf,adapted)
        tokenizer=AutoTokenizer.from_pretrained(hf,local_files_only=True,trust_remote_code=False)
        rows=[probes[label][i]for i in [0,2,3,5,6,8]]
        allowed=json.loads((folder/'output-token-ids.json').read_text());mask=(C.c_ushort*len(allowed))(*allowed)
        header,payload=packet(folder/'model.mkqb');records={}
        for context in [2048,1024]:
            package=folder/('model.mka'if context==2048 else'model-context1024.mka')
            weights=folder/'model.mkqb'
            if context==1024:
                header['config']['max_position_embeddings']=1024
                raw=json.dumps(header,ensure_ascii=False,separators=(',',':')).encode()
                weights=out/(label+'-context1024.mkqb');weights.write_bytes(b'MKQBv1\0\0'+struct.pack('<I',len(raw))+raw+payload)
                assert packet(weights)[1]==payload
            exporter.export(weights,adapted,package,'lut')
            data=package.read_bytes();buffer=C.create_string_buffer(data);assert lib.mk_ai_open(buffer,len(data))==0
            lib.codec_set_mask(mask,len(allowed));details=[]
            encoded=(C.c_ushort*2048)();used=C.c_uint();best=C.c_ushort()
            for row in rows:
                inputs=tokenizer.encode(row['prompt'],add_special_tokens=False)
                assert len(inputs)+352<=context
                assert lib.codec_encode(row['prompt'].encode(),encoded,2048,C.byref(used))==0
                assert list(encoded[:used.value])==inputs
                lib.mk_ai_reset()
                for i,token in enumerate(inputs):assert lib.codec_forward(token,int(i+1==len(inputs)),C.byref(best),None)==0
                tokens=[]
                for _ in range(352):
                    token=best.value
                    if token==tokenizer.eos_token_id:break
                    tokens.append(token);assert lib.codec_forward(token,1,C.byref(best),None)==0
                details.append({'id':row['id'],'tokens_match_b200':tokens==row['generated_token_ids'],'tokens':tokens})
            records[str(context)]={'package_sha256':sha(package),'package_bytes':len(data),'weights_payload_identical_to_audited_q4':True,
              'native_generations_match':sum(x['tokens_match_b200']for x in details),'probes':len(rows),'native_tokenizer_matches':len(rows),
              'native_cache_bytes':lib.mk_ai_cache(),'workspace_bytes':lib.mk_ai_workspace(),
              'package_plus_cache_and_workspace_bytes':len(data)+lib.mk_ai_cache()+lib.mk_ai_workspace(),'details':details}
        record={**records['2048'],'context1024':records['1024'],'source_packet_sha256':sha(folder/'model.mkqb'),
          'native_cache_storage':'FP32','same_private_runtime_snapshot_as_previous_study':True,'physical_picocalc_measured':False}
        write(folder/'native-info.json',record);native[label]=record
        write(root/'native-verification.json',{'models':native,'selected_label':selected,'physical_picocalc_measured':False})
        assert all(x['native_generations_match']==x['probes']for x in records.values()),'Native mismatch: '+label
        print(json.dumps({'native_verified':label,'context2048':records['2048']['native_generations_match'],
          'context1024':records['1024']['native_generations_match']}),flush=True)
    for name in ['model.mka','model-context1024.mka','native-info.json']:
        shutil.copyfile(root/'export'/selected/name,root/'export/selected-budget'/name)
    write(root/'native-verification.json',{'models':native,'selected_label':selected,
      'source_sha256':{str(p.relative_to(source)):sha(p)for p in source.rglob('*')if p.is_file()},'physical_picocalc_measured':False})
    tokenizer=AutoTokenizer.from_pretrained(root/'export'/selected/'hf',local_files_only=True,trust_remote_code=False)
    context_check(root,models[selected],tokenizer)
    print(json.dumps({'verification_complete':True,'cpu_matches':result['cpu_b200_matches'],
      'half_matches':result['fp16_fp32_matches'],'probes':len(checks)}),flush=True)


if __name__=='__main__':main()
