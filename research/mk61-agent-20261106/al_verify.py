"""Prove Q4 decoder immutability, exact exports, and native action streams."""
import argparse
import ctypes as C
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import torch
from transformers import AutoModelForCausalLM,AutoTokenizer
from al_common import HERE,INITIAL,INITIAL_PACKET,ACTION_IDS,CORRECT_IDS,ARMS,read,write,sha,output_ids,compact_head
from al_eval import generate
from lowbit import load
from aj_native import Engine,prepare_source,MAX_INPUT_BYTES
from ac_verify import verify_parser
from ac_protocol import prompt_ids
from codec_native import native_tokenizer
from codec_common import ROOT as CODEC_ROOT
from native_export import packet
from native_verify import verify_export


def choose(report):
    values=[h for p in report.values()for r in p['details']for h in r['history']if'prompt'in h and'generation'in h]
    result=[];seen=set()
    for action in ['write','run','trace','done','unsure']:
        for h in [h for h in values if h['generation'].get('action')==action][:2]:
            if h['prompt']not in seen:result.append(h);seen.add(h['prompt'])
    return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();root=a.root.resolve();out=root/'native';out.mkdir(exist_ok=True)
    torch.set_num_threads(4)
    for name in ['data-frozen.json','prepared.json']:
        for n,d in json.loads((root/name).read_text())['files'].items():assert sha(root/n)==d,n
    for n,d in json.loads((root/'prepared.json').read_text())['source_hashes'].items():assert sha(HERE/n)==d,n
    prepare_source(root,out,json.loads((CODEC_ROOT/'codebook-32.json').read_text()))
    spec=importlib.util.spec_from_file_location('ak_exporter',out/'source/export_model.py');exporter=importlib.util.module_from_spec(spec);spec.loader.exec_module(exporter)
    tokenizer=AutoTokenizer.from_pretrained(INITIAL,local_files_only=True);parser=verify_parser(out,tokenizer)
    source=AutoModelForCausalLM.from_pretrained(INITIAL,local_files_only=True);load(source,INITIAL_PACKET);reference={n:p.detach().clone()for n,p in source.named_parameters()};del source
    profiles=[*ARMS,*[a+'-research'for a in ARMS],*[a+'-coupled'for a in ARMS]];models={};results={}
    for arm in ['compiler',*profiles]:
        folder=root/'export'/arm;manifest=json.loads((folder/'manifest.json').read_text())
        if arm!='compiler':
            assert sha(folder/'model.mkqb')==manifest['packed_sha256'];manifest.update(arm='asm',checkpoint_files={p.name:sha(p)for p in(folder/'hf').iterdir()if p.is_file()});write(folder/'manifest.json',manifest)
        model,exact=verify_export(folder);models[arm]=model
        if arm!='compiler':
            changed=[]
            for name,p in model.named_parameters():
                if name=='model.embed_tokens.weight':
                    mask=torch.ones(len(p),dtype=torch.bool);mask[ACTION_IDS+CORRECT_IDS]=False;assert torch.equal(p[mask],reference[name][mask])
                    changed=[i for i in ACTION_IDS+CORRECT_IDS if not torch.equal(p[i],reference[name][i])]
                else:
                    adapted = name.startswith('model.layers.') and name.endswith(('.self_attn.q_proj.weight','.self_attn.v_proj.weight','.mlp.gate_proj.weight','.mlp.up_proj.weight','.mlp.down_proj.weight'))
                    if adapted and arm.startswith('late'): adapted = int(name.split('.')[2]) >= 8
                    if not adapted: assert torch.equal(p,reference[name]),(arm,name)

        compact_head(model,json.loads((folder/'output-token-ids.json').read_text()));native_tokenizer(folder/'hf',out/(arm+'-tokenizer.json'))
        header,payload=packet(folder/'model.mkqb');header['config']['max_position_embeddings']=1024;raw=json.dumps(header,ensure_ascii=False,separators=(',',':')).encode()
        derived=out/(arm+'-context1024.mkqb');derived.write_bytes(b'MKQBv1\0\0'+struct.pack('<I',len(raw))+raw+payload)
        exporter.export(derived,out/(arm+'-tokenizer.json'),folder/'model.mka','lut')
        results[arm]={'exact_reload':exact,'package_bytes':(folder/'model.mka').stat().st_size,'package_sha256':sha(folder/'model.mka')}
        if arm!='compiler':results[arm].update(changed_rows=changed,all_input_rows_and_unadapted_tensors_bit_identical=True)
    engine=Engine(root,'late');long=set()
    for arm in profiles:
        key='coupled'if arm.endswith('-coupled')else'research'if arm.endswith('-research')else'best';base=arm.removesuffix('-research').removesuffix('-coupled');report=json.loads((root/base/(key+'-fresh.json')).read_text())
        selected=choose(report);cpu=generate(models[arm],tokenizer,[h['prompt']for h in selected]);engine.tool=arm;engine.role=None;details=[]
        for h,c in zip(selected,cpu):
            n=engine.generate(h['prompt']);g=h['generation']
            assert n.get('input_token_ids')==prompt_ids(tokenizer,h['prompt'])
            assert n['generated_token_ids']==c['generated_token_ids']==g['generated_token_ids'],(arm,n,c,g)
            error=abs(n['correctness_margin']-g['correctness_margin']);assert error<.01,(arm,error)
            details.append({'action':g['action'],'tokens_equal_B200':True,'margin_error':error})
        for p in report.values():
            for r in p['details']:
                for h in r['history']:
                    if h.get('prompt')and h.get('generation',{}).get('input_tokens',9999)<1016 and len(h['prompt'].encode())>2048:long.add(h['prompt'])
        results[arm].update(probes=len(details),cpu_matches=len(details),native_matches=len(details),details=details,cache_bytes=engine.lib.mk_ai_cache(),workspace_bytes=engine.lib.mk_ai_workspace())
        runtime=root/'export'/arm/'runtime';runtime.mkdir(exist_ok=True)
        for name in ['aj_native.py','ac_native.py','ab_native.hpp','ab_native_probe.cpp','ac_runtime.py','ac_protocol.py']:shutil.copyfile(HERE/name,runtime/name)
        print(json.dumps({'verified':arm,'probes':len(details),'input_rows_and_unadapted_tensors_protected':True}),flush=True)
    encoded=(C.c_ushort*1024)();used=C.c_uint()
    for text in long:
        assert len(text.encode())<=MAX_INPUT_BYTES
        assert engine.lib.codec_encode(text[:-1].encode(),encoded,1023,C.byref(used))==0
        assert list(encoded[:used.value])+[30]==prompt_ids(tokenizer,text)
    assert engine.lib.codec_encode(b'a'*(MAX_INPUT_BYTES+1),encoded,1023,C.byref(used))!=0
    pre=json.loads((root/'preselected.json').read_text());shutil.copytree(root/'export'/pre['selected_arm'],root/'export/selected-research',dirs_exist_ok=True)
    write(root/'native-verification.json',{'complete':True,'models':results,'parser':parser,'shared_weight_buffer_bytes':engine.capacity,
      'input_rows_and_unadapted_tensors_protected':True,'long_prefixes_checked':len(long),'physical_device_measured':False})


if __name__=='__main__':main()
