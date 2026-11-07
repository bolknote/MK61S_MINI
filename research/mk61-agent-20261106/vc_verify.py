import argparse
import ctypes as C
import json
import shutil
import struct
from pathlib import Path

import torch
from transformers import AutoTokenizer
from safetensors.torch import load_file
from vc_common import HERE,sha,write
from vc_train import scores
from native_verify import verify_export
from codec_native import prepare_source,native_tokenizer
from codec_common import ROOT as CODEC_ROOT
from native_export import packet


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();root=a.root.resolve();torch.set_num_threads(4)
    book=json.loads((CODEC_ROOT/'codebook-32.json').read_text());out=root/'native';out.mkdir(exist_ok=True)
    src,path,exporter=prepare_source(root,out,book);lib=C.CDLL(str(path));lib.mk_ai_open.argtypes=[C.c_void_p,C.c_uint]
    lib.codec_set_mask.argtypes=[C.POINTER(C.c_ushort),C.c_uint];lib.codec_forward.argtypes=[C.c_ushort,C.c_int,C.POINTER(C.c_ushort),C.POINTER(C.c_float)]
    lib.codec_encode.argtypes=[C.c_char_p,C.POINTER(C.c_ushort),C.c_uint,C.POINTER(C.c_uint)]
    head_ids=json.loads((root/'output-token-ids.json').read_text());head=torch.tensor(head_ids);records={};original=None
    for label in ['baseline','slow-best','fast-best']:
        folder=root/'export'/label;model,verified=verify_export(folder);tokenizer=AutoTokenizer.from_pretrained(folder/'hf',local_files_only=True,trust_remote_code=False)
        master=load_file(str(folder/'hf/model.safetensors'));key=next(k for k in master if k.endswith('embed_tokens.weight'));embedding=master[key]
        if original is None:original=embedding
        else:assert torch.equal(original,embedding)
        report=json.loads((root/'results'/(label+'.json')).read_text());threshold=report['validation']['threshold'];probes=[]
        for name in ['validation_details','details']:
            for truth in [0,1]:probes+=sorted([r for r in report[name]if r['label']==truth],key=lambda r:abs(r['score']-threshold))[:4]
        cpu=scores(model,tokenizer,probes,head,batch=1)
        adapted=out/(label+'-tokenizer.json');native_tokenizer(folder/'hf',adapted)
        header,payload=packet(folder/'model.mkqb');header['config']['max_position_embeddings']=1024
        raw=json.dumps(header,ensure_ascii=False,separators=(',',':')).encode();derived=out/(label+'-context1024.mkqb')
        derived.write_bytes(b'MKQBv1\0\0'+struct.pack('<I',len(raw))+raw+payload);assert packet(derived)[1]==payload
        package=folder/'model.mka';exporter.export(derived,adapted,package,'lut');data=package.read_bytes();buffer=C.create_string_buffer(data)
        assert lib.mk_ai_open(buffer,len(data))==0;ids=(C.c_ushort*2)(*head_ids);lib.codec_set_mask(ids,2)
        encoded=(C.c_ushort*1024)();used=C.c_uint();best=C.c_ushort();logits=(C.c_float*8224)();rows=[]
        for row,local in zip(probes,cpu):
            expected=tokenizer.encode(row['prompt'],add_special_tokens=False)
            assert lib.codec_encode(row['prompt'].encode(),encoded,1024,C.byref(used))==0 and list(encoded[:used.value])==expected
            lib.mk_ai_reset()
            for i,token in enumerate(expected):assert lib.codec_forward(token,int(i==len(expected)-1),C.byref(best),logits)==0
            native_score=float(logits[head_ids[0]]-logits[head_ids[1]])
            cpu_error=abs(local['score']-row['score']);native_error=abs(native_score-row['score'])
            assert cpu_error<.005 and native_error<.005,(label,row['id'],cpu_error,native_error)
            assert (local['score']>=threshold)==(native_score>=threshold)==(row['score']>=threshold)
            rows.append({'id':row['id'],'cpu_error':cpu_error,'native_error':native_error,'threshold_decisions_match':True})
        records[label]={'export':verified,'probes':len(rows),'decisions_match':len(rows),'details':rows,'package_bytes':len(data),
          'native_cache_bytes':lib.mk_ai_cache(),'workspace_bytes':lib.mk_ai_workspace(),'working_context':1024,
          'native_kv_storage':'FP32','all_input_embedding_rows_unchanged':True,'package_sha256':sha(package)}
        write(folder/'native-info.json',records[label]);print(json.dumps({'native_verified':label,'probes':len(rows)}),flush=True)
    for name in ['data-frozen.json','prepared.json']:
        d=json.loads((root/name).read_text())
        for n,h in d['files'].items():assert sha(root/n)==h
    frozen=json.loads((root/'data-frozen.json').read_text())
    for name,digest in frozen['private_core_files'].items():assert sha(root/'core-source'/name)==digest
    selected=json.loads((root/'final-export.json').read_text())['selected_label']
    for name in ['model.mka','native-info.json']:shutil.copyfile(root/'export'/selected/name,root/'export/selected-budget'/name)
    write(root/'native-verification.json',{'models':records,'probes':sum(r['probes']for r in records.values()),
      'decisions_match':sum(r['decisions_match']for r in records.values()),'source_sha256':{p.name:sha(p)for p in src.iterdir()if p.is_file()},
      'physical_picocalc_measured':False,'source_coder_unchanged':True})


if __name__=='__main__':main()
