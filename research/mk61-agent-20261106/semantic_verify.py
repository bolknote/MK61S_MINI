"""Exact audited Q4 reloads, CPU/half-cache replay, isolated native MKA exports."""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import shutil
import struct

import torch
from transformers import AutoTokenizer

from semantic_common import read,sha,write_json,compact_head,protocol
from codec_common import ROOT as CODEC_ROOT
from codec_verify import generate
from native_verify import verify_export
from native_export import packet as read_packet
from codec_native import prepare_source,native_tokenizer


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);args=ap.parse_args();root=args.root.resolve()
    torch.set_num_threads(4);exports={};models={};checks=[]
    for name in ['baseline','direct-best','direct-endpoint','auxiliary-best','auxiliary-endpoint']:
        folder=root/'export'/name;model,result=verify_export(folder);exports[name]=result
        manifest=json.loads((folder/'manifest.json').read_text())
        assert sha(folder/'output-token-ids.json')==manifest['output_ids_sha256']
        assert sha(folder/'prompt-template.txt')==manifest['prompt_template_sha256']
        audit=json.loads((root/'results'/(name+'.json')).read_text())
        assert audit['packed_sha256']==manifest['packed_sha256']
        if name in ['baseline','direct-endpoint','auxiliary-endpoint']:models[name]=model
        print(json.dumps({'verified_export':name}),flush=True)
    for name,model in models.items():
        folder=root/'export'/name;tokenizer=AutoTokenizer.from_pretrained(folder/'hf',local_files_only=True,trust_remote_code=False)
        compact_head(model,json.loads((folder/'output-token-ids.json').read_text()));result=json.loads((root/'results'/(name+'.json')).read_text())
        probes=[r for level in [1,2,3]for r in result['metrics'][f'level{level}']['program']['details'][:2]]
        probes += [result['contexts'][str(n)]['all_tasks']['program']['details'][0]for n in [1024,2048]]
        for row in probes:
            full=generate(model,tokenizer,row['prompt'],protocol('hex'));half=generate(model,tokenizer,row['prompt'],protocol('hex'),True)
            checks.append({'label':name,'id':row['id'],'prompt_tokens':full['cache']['prompt_tokens'],
              'cpu_b200_tokens_equal':full['generated_token_ids']==row['generated_token_ids'],
              'fp16_fp32_tokens_equal':half['generated_token_ids']==full['generated_token_ids'],
              'fp16_cache':half['cache'],'cpu_reply':full['reply'],'half_reply':half['reply']})
        print(json.dumps({'verified_cpu_and_half_cache':name,'probes':len(probes)}),flush=True)
    for filename,item in json.loads((root/'prepared.json').read_text())['files'].items():assert sha(root/filename)==item['sha256']
    result={'exports':exports,'cpu_cache_probes':checks,'cpu_b200_matches':sum(x['cpu_b200_tokens_equal']for x in checks),
      'fp16_fp32_matches':sum(x['fp16_fp32_tokens_equal']for x in checks),'compared':len(checks),'frozen_inputs_verified':True,
      'fp16_byte_count_verified':True,'physical_picocalc_measured':False}
    write_json(root/'local-verification.json',result)
    assert result['cpu_b200_matches']==len(checks),'CPU and B200 token mismatch: inspect local-verification.json'
    # Reuse a private frozen native runtime snapshot, never product files.
    out=root/'native';out.mkdir(exist_ok=True);book=json.loads((CODEC_ROOT/'codebook-32.json').read_text())
    source,library,exporter=prepare_source(root,out,book);lib=C.CDLL(str(library))
    lib.mk_ai_open.argtypes=[C.c_void_p,C.c_uint];lib.codec_set_mask.argtypes=[C.POINTER(C.c_ushort),C.c_uint]
    lib.codec_forward.argtypes=[C.c_ushort,C.c_int,C.POINTER(C.c_ushort),C.POINTER(C.c_float)]
    lib.codec_encode.argtypes=[C.c_char_p,C.POINTER(C.c_ushort),C.c_uint,C.POINTER(C.c_uint)]
    native={}
    for name in ['baseline','direct-endpoint','auxiliary-endpoint']:
        folder=root/'export'/name;hf=folder/'hf';adapted=out/(name+'-tokenizer.json');native_tokenizer(hf,adapted)
        package=folder/'model.mka';exporter.export(folder/'model.mkqb',adapted,package,'lut')
        data=package.read_bytes();buffer=C.create_string_buffer(data);assert lib.mk_ai_open(buffer,len(data))==0
        allowed=json.loads((folder/'output-token-ids.json').read_text());mask=(C.c_ushort*len(allowed))(*allowed);lib.codec_set_mask(mask,len(allowed))
        tokenizer=AutoTokenizer.from_pretrained(hf,local_files_only=True,trust_remote_code=False)
        audited=json.loads((root/'results'/(name+'.json')).read_text());rows=[v for level in [1,2,3]for v in audited['metrics'][f'level{level}']['program']['details'][:2]]
        generations=[];encoded=(C.c_ushort*2048)();used=C.c_uint();best=C.c_ushort()
        for row in rows:
            inputs=tokenizer.encode(row['prompt'],add_special_tokens=False)
            assert lib.codec_encode(row['prompt'].encode(),encoded,2048,C.byref(used))==0
            assert list(encoded[:used.value])==inputs
            lib.mk_ai_reset()
            for i,token in enumerate(inputs):assert lib.codec_forward(token,int(i+1==len(inputs)),C.byref(best),None)==0
            tokens=[]
            for _ in range(min(160,2048-len(inputs))):
                token=best.value
                if token==tokenizer.eos_token_id:break
                tokens.append(token);assert lib.codec_forward(token,1,C.byref(best),None)==0
            generations.append({'id':row['id'],'tokens_match_b200':tokens==row['generated_token_ids'],'tokens':tokens})
        record={'source_packet_sha256':sha(folder/'model.mkqb'),'package_sha256':sha(package),'package_bytes':len(data),
          'native_tokenizer_matches':len(rows),'native_generations_match':sum(r['tokens_match_b200']for r in generations),'probes':len(rows),
          'workspace_bytes':lib.mk_ai_workspace(),'cache_bytes':lib.mk_ai_cache(),'native_cache_storage':'FP32',
          'same_private_runtime_snapshot_as_previous_study':True,'physical_picocalc_measured':False,'details':generations}
        # The current native reference cache is FP32: 2048 tokens need 10 MiB
        # for this architecture. Also ship a 1024-context package, preserving
        # every weight byte and the same RoPE prefix, for the 8 MiB target.
        header,payload=read_packet(folder/'model.mkqb');header['config']['max_position_embeddings']=1024
        encoded_header=json.dumps(header,ensure_ascii=False,separators=(',',':')).encode()
        derived=out/(name+'-context1024.mkqb');derived.write_bytes(b'MKQBv1\0\0'+struct.pack('<I',len(encoded_header))+encoded_header+payload)
        assert read_packet(derived)[1]==payload
        small_package=folder/'model-context1024.mka';exporter.export(derived,adapted,small_package,'lut')
        small_data=small_package.read_bytes();small_buffer=C.create_string_buffer(small_data);assert lib.mk_ai_open(small_buffer,len(small_data))==0
        lib.codec_set_mask(mask,len(allowed));short_matches=0
        for row in rows:
            inputs=tokenizer.encode(row['prompt'],add_special_tokens=False);assert len(inputs)+160<1024
            lib.mk_ai_reset()
            for i,token in enumerate(inputs):assert lib.codec_forward(token,int(i+1==len(inputs)),C.byref(best),None)==0
            tokens=[]
            for _ in range(160):
                token=best.value
                if token==tokenizer.eos_token_id:break
                tokens.append(token);assert lib.codec_forward(token,1,C.byref(best),None)==0
            short_matches+=tokens==row['generated_token_ids']
        record['context1024']={'package_sha256':sha(small_package),'package_bytes':len(small_data),
          'weights_payload_identical_to_audited_q4':True,'native_cache_bytes':lib.mk_ai_cache(),
          'workspace_bytes':lib.mk_ai_workspace(),'native_generations_match':short_matches,'probes':len(rows),
          'only_context_header_and_rope_table_length_changed':True,'physical_picocalc_measured':False}
        assert short_matches==len(rows),'1024-context package mismatch: '+name
        write_json(folder/'native-info.json',record);native[name]=record
        assert record['native_generations_match']==len(rows),'Native token mismatch: '+name
        print(json.dumps({'native_verified':name,'matched':record['native_generations_match'],'probes':len(rows)}),flush=True)
    selected=json.loads((root/'final-export.json').read_text())['selected_label']
    if selected not in native:
        # A retained step-0 checkpoint is the original model. Avoid presenting
        # repeated probes of identical weights as tests of trained endpoints.
        selected_folder=root/'export'/selected;selected_header,selected_payload=read_packet(selected_folder/'model.mkqb')
        alias=next(name for name in native if read_packet(root/'export'/name/'model.mkqb')[1]==selected_payload
          and json.loads((root/'export'/name/'hf/tokenizer.json').read_text())==json.loads((selected_folder/'hf/tokenizer.json').read_text()))
        adapted=out/(selected+'-tokenizer.json');native_tokenizer(selected_folder/'hf',adapted)
        exporter.export(selected_folder/'model.mkqb',adapted,selected_folder/'model.mka','lut')
        assert sha(selected_folder/'model.mka')==native[alias]['package_sha256']
        shutil.copyfile(root/'export'/alias/'model-context1024.mka',selected_folder/'model-context1024.mka')
        info={**native[alias],'source_packet_sha256':sha(selected_folder/'model.mkqb'),
          'verified_native_package_identical_to':alias,'weights_and_tokenizer_identical_to':alias}
        write_json(selected_folder/'native-info.json',info)
    for name in ['model.mka','model-context1024.mka','native-info.json']:shutil.copyfile(root/'export'/selected/name,root/'export/selected-budget'/name)
    write_json(root/'native-verification.json',{'models':native,'selected_label':selected,'source_sha256':{p.name:sha(p)for p in source.iterdir()if p.is_file()},'physical_picocalc_measured':False})
    print(json.dumps({'verification_complete':True,'cpu_matches':result['cpu_b200_matches'],'half_matches':result['fp16_fp32_matches'],'probes':len(checks)}),flush=True)


if __name__=='__main__':main()
