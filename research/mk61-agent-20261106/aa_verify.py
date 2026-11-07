"""Exact Q4 reload and real C++ inference for the new control-token protocol."""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import torch
from transformers import AutoTokenizer
from safetensors.torch import load_file
from aa_common import HERE,ACTION_IDS,read,write,sha,compact_head,output_ids
from aa_protocol import Grammar,target_ids
from aa_eval import generate
from aa_native import Native
from codec_native import prepare_source,native_tokenizer
from codec_common import ROOT as CODEC_ROOT
from native_verify import verify_export
from native_export import packet


def probes(report):
    out=[]
    for op in [0x1C,0x50,0x54,0x53]:
        row=next(r for r in report['isa']['details']if r['opcode']==op and r['angle']=='RAD')
        out.append(row)
    for group in ['literal_copy','composition','stack_source','algorithm_clamp']:
        row=next((r for r in report['language']['details']if r['group']==group),None)
        if row:out.append(row)
    for kind in ['diag','patch','run','trace','done','unsure','write']:
        h=next((h for r in report['tools']['details']for h in r['history']if h['kind']==kind and'generation'in h),None)
        if h:out.append({'id':'tool:'+kind,'prompt':h['prompt'],**h['generation']})
    return out


def verify_parser(out,tokenizer):
    path=out/'action-probe.dylib'
    subprocess.run(['clang++','-std=c++17','-O2','-fPIC','-shared',str(HERE/'aa_native_probe.cpp'),'-o',str(path)],check=True)
    p=C.CDLL(str(path));p.aa_accept.argtypes=[C.c_ushort,C.c_char_p];p.aa_allows.argtypes=[C.c_ushort,C.c_char_p]
    p.aa_body.argtypes=[C.POINTER(C.c_ubyte)];grammar=Grammar(tokenizer,0);checks=0
    outputs=output_ids(tokenizer)
    pieces={i:tokenizer.decode([i],clean_up_tokenization_spaces=False).encode()for i in outputs}
    for action in ['write','patch','run','trace','diag','done','unsure']:
        bodies=[[]]if action in ['trace','done','unsure']else [[b]for b in range(256)]if action=='run'else [[1,28,29,0,b]for b in range(256)]if action=='diag'else [[0,0,b]for b in range(256)]if action=='patch'else [[b]for b in range(256)]
        for body in bodies:
            values=target_ids(tokenizer,action,body);p.aa_reset();text=''
            for at,token in enumerate(values):
                allowed=ACTION_IDS if at==0 else grammar.permitted(action,text)
                for candidate in outputs:
                    piece=pieces[candidate]
                    assert bool(p.aa_allows(candidate,piece))==(candidate in allowed),(action,text,candidate)
                piece=tokenizer.decode([token],clean_up_tokenization_spaces=False).encode()
                assert p.aa_accept(token,piece)
                if at and token!=2:text+=piece.decode()
            if action not in ['trace','done','unsure']:assert p.aa_complete()
            actual=(C.c_ubyte*512)();size=p.aa_body(actual);assert list(actual[:size])==body
            checks+=1
    return {'roundtrips_and_python_masks_matched':checks,'state_bytes':p.aa_state_bytes(),'allocation_free':True,'has_semantic_oracle':False}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();root=a.root.resolve()
    torch.set_num_threads(4);out=root/'native';out.mkdir(exist_ok=True)
    for file in ['data-frozen.json','prepared.json']:
        frozen=json.loads((root/file).read_text())
        for name,digest in frozen['files'].items():assert sha(root/name)==digest,name
    prepared=json.loads((root/'prepared.json').read_text())
    for name,digest in prepared['source_hashes'].items():assert sha(HERE/name)==digest,name
    book=json.loads((CODEC_ROOT/'codebook-32.json').read_text());src,library,exporter=prepare_source(root,out,book)
    first=AutoTokenizer.from_pretrained(root/'export/sft/hf',local_files_only=True)
    parser=verify_parser(out,first);results={}
    for arm in ['sft','preference']:
        folder=root/'export'/arm;model,exact=verify_export(folder);tokenizer=AutoTokenizer.from_pretrained(folder/'hf',local_files_only=True)
        compact_head(model,output_ids(tokenizer));report=json.loads((root/(arm+'-audit.json')).read_text())
        assert sha(folder/'model.mkqb')==report['packed_sha256']
        chosen=probes(report);cpu=[]
        for row in chosen:
            result=generate(model,tokenizer,[row['prompt']])[0]
            cpu.append({'id':row['id'],'tokens_equal_b200':result['generated_token_ids']==row['generated_token_ids'],
                        'cpu':result,'b200':row['generated_token_ids']})
        adapted=out/(arm+'-tokenizer.json');native_tokenizer(folder/'hf',adapted)
        header,payload=packet(folder/'model.mkqb');header['config']['max_position_embeddings']=1024
        raw=json.dumps(header,ensure_ascii=False,separators=(',',':')).encode();derived=out/(arm+'-context1024.mkqb')
        derived.write_bytes(b'MKQBv1\0\0'+struct.pack('<I',len(raw))+raw+payload)
        assert packet(derived)[1]==payload
        exporter.export(derived,adapted,folder/'model.mka','lut')
        native=Native(folder);native_rows=[]
        for row in chosen:
            result=native.generate(row['prompt'])
            assert result.get('input_token_ids')==tokenizer.encode(row['prompt'],add_special_tokens=False)
            native_rows.append({'id':row['id'],'tokens_equal_b200':result['generated_token_ids']==row['generated_token_ids'],
                                'native':result,'b200':row['generated_token_ids']})
        record={'exact_reload':exact,'cpu':cpu,'native':native_rows,'probes':len(chosen),
                'cpu_matches':sum(r['tokens_equal_b200']for r in cpu),'native_matches':sum(r['tokens_equal_b200']for r in native_rows),
                'package_bytes':(folder/'model.mka').stat().st_size,'package_sha256':sha(folder/'model.mka'),
                'cache_bytes':native.lib.mk_ai_cache(),'workspace_bytes':native.lib.mk_ai_workspace(),
                'native_KV_storage':'FP32','context':1024,'physical_picocalc_measured':False}
        results[arm]=record;write(root/'native-verification.json',{'models':results,'parser':parser})
        assert record['cpu_matches']==len(chosen),('CPU/B200 mismatch',arm,cpu)
        assert record['native_matches']==len(chosen),('native mismatch',arm,native_rows)
        for name in ['aa_native.hpp','aa_native_probe.cpp','aa_native.py']:shutil.copyfile(HERE/name,folder/'runtime'/name)
        print(json.dumps({'verified':arm,'probes':len(chosen),'cpu':record['cpu_matches'],'native':record['native_matches']}),flush=True)
    selected=json.loads((root/'preselected.json').read_text())['selected_arm']
    shutil.copytree(root/'export'/selected,root/'export/selected-research',dirs_exist_ok=True)
    # Original Russian/HEX input rows, including all originally trainable output rows, are now protected.
    from aa_common import INITIAL
    reference=load_file(str(INITIAL/'model.safetensors'));key=next(k for k in reference if k.endswith('embed_tokens.weight'))
    keep=torch.ones(reference[key].shape[0],dtype=torch.bool);keep[ACTION_IDS]=False;protected={}
    for arm in ['sft','preference']:
        actual=load_file(str(root/'export'/arm/'hf/model.safetensors'))[key]
        assert torch.equal(reference[key][keep],actual[keep])
        protected[arm]={'rows':int(keep.sum()),'bit_identical':True,'sha256':hashlib.sha256(actual[keep].numpy().tobytes()).hexdigest()}
    write(root/'native-verification.json',{'models':results,'parser':parser,'protected_rows':protected,'complete':True,
                                          'physical_picocalc_measured':False})


if __name__=='__main__':main()
