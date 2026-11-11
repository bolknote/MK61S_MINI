"""Native Q4 verification against each branch's own untouched parent."""
import argparse
import json
from pathlib import Path
import struct
import torch
from transformers import AutoTokenizer
import ay_native as base
from be_native import choose as original_choose
from bl_common import ROOT,SOURCES,read,write,sha,check_frozen,ACTION_IDS,output_ids,compact_head
from bl_model import parent
from ap_native import prepare_source
from ac_verify import verify_parser
from codec_common import ROOT as CODEC_ROOT
from codec_native import native_tokenizer
from native_export import packet
from native_verify import verify_export
from bk_independent_generate import generate
from aq_protocol import prompt_ids

def choose(report):
    probes=[];seen=set()
    def add(prompt,generation,forced):
        if prompt in seen or generation.get('codec_error'):return
        seen.add(prompt);probes.append({'prompt':prompt,'generation':generation,'forced_action':forced})
    for panel in ['known','novel','editorial','structured']:
        for r in [r for r in report['primary']['records']if r['panel']==panel][:2]:add(r['prompt'],r['generation'],'write')
    for mode in ['self','legacy_self']:
        kinds=set()
        for r in report.get(mode,{}).get('records',[]):
            for h in r['history']:
                if 'prompt'not in h or 'generation'not in h or h['kind']in kinds:continue
                if h['generation'].get('codec_error'):continue
                kinds.add(h['kind']);add(h['prompt'],h['generation'],'write'if h['kind']=='replan'else None)
    return probes

def main(root):
    check_frozen();assert read(root/'complete.json')['complete'];out=root/'native';out.mkdir(exist_ok=True)
    _,_,exporter=prepare_source(root,out,read(CODEC_ROOT/'codebook-32.json'))
    references={};tokenizer=None
    for branch in ['lora','full']:
        model,tok=parent(branch,'cpu');references[branch]={n:p.detach().clone()for n,p in model.named_parameters()};del model
        if tokenizer is not None:assert tokenizer.get_vocab()==tok.get_vocab()
        tokenizer=tok
    parser=verify_parser(out,tokenizer);models={};results={};arms=['parent_lora','lora','fixed3000_lora','parent_full','full','fixed3000_full']
    for arm in arms:
        branch=arm.split('_',1)[-1];reference=references[branch];folder=root/'export'/arm;model,exact=verify_export(folder);models[arm]=model
        assert AutoTokenizer.from_pretrained(folder/'hf',local_files_only=True).get_vocab()==tokenizer.get_vocab()
        assert sum(p.numel()for p in model.parameters())==3022080
        changed=[]
        for name,p in model.named_parameters():
            if not torch.equal(p,reference[name]):changed.append(name)
            if arm.startswith('parent_'):assert torch.equal(p,reference[name]),(arm,name)
            elif branch=='lora':
                if name=='model.embed_tokens.weight':
                    mask=torch.ones(len(p),dtype=torch.bool);mask[ACTION_IDS]=False;assert torch.equal(p[mask],reference[name][mask])
                elif not(name.startswith('model.layers.')and name.endswith(('.self_attn.q_proj.weight','.self_attn.v_proj.weight','.mlp.gate_proj.weight','.mlp.up_proj.weight','.mlp.down_proj.weight'))):
                    assert torch.equal(p,reference[name]),(arm,name)
        compact_head(model,output_ids(tokenizer));native_tokenizer(folder/'hf',out/(arm+'-tokenizer.json'))
        header,payload=packet(folder/'model.mkqb');header['config']['max_position_embeddings']=1024
        data=json.dumps(header,ensure_ascii=False,separators=(',',':')).encode();derived=out/(arm+'-context1024.mkqb')
        derived.write_bytes(b'MKQBv1\0\0'+struct.pack('<I',len(data))+data+payload);assert packet(derived)[1]==payload
        exporter.export(derived,out/(arm+'-tokenizer.json'),folder/'model.mka','lut')
        if arm.startswith('parent_'):assert sha(folder/'model.mka')==sha(SOURCES[branch]/'model.mka')
        results[arm]={'exact_export':exact,'mka_bytes':(folder/'model.mka').stat().st_size,'mka_sha256':sha(folder/'model.mka'),
            'dictionary_token_ids_unchanged':True,'changed_tensors':changed,'input_embedding_weights_changed':'model.embed_tokens.weight'in changed}
        m=read(folder/'manifest.json');m.update(mka_bytes=results[arm]['mka_bytes'],mka_sha256=results[arm]['mka_sha256']);write(folder/'manifest.json',m)
    base.ARMS=arms;engine=base.Engine(root)
    for arm in arms:
        engine.tool=arm;engine.role=None;details=[]
        for probe in choose(read(root/arm/'closed.json')):
            p=probe['prompt'];forced=probe['forced_action'];gpu=probe['generation'];cpu=generate(models[arm],tokenizer,[p],forced_action=forced)[0]
            native=engine.generate(p,forced_action=forced)
            assert native['input_token_ids']==prompt_ids(tokenizer,p)
            assert native['generated_token_ids']==cpu['generated_token_ids']==gpu['generated_token_ids'],(arm,probe,native,cpu)
            details.append({'action':gpu['action'],'input_tokens':len(prompt_ids(tokenizer,p)),'forced_action':forced,'B200_CPU_CPP_streams_identical':True})
        results[arm].update(probes=len(details),details=details,cache_bytes=engine.lib.mk_ai_cache(),workspace_bytes=engine.lib.mk_ai_workspace())
        print(json.dumps({'arm':arm,'probes':len(details),'all_equal':True}),flush=True)
    check_frozen();write(root/'native-verification.json',{'complete':True,'models':results,'parser':parser,'context':1024,
        'host_KV_dtype':'FP32','physical_PicoCalc_measured':False,'native_source_sha256':sha(__file__),'no_model_selection':True})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT/'server-results');a=p.parse_args()
    torch.set_num_threads(4);main(a.root)
