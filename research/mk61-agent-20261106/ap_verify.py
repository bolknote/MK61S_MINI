"""Verify merged Q4 packets, frozen input rows and six-action native outputs."""
import argparse
import ctypes as C
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import torch
from ap_common import HERE,INITIAL,INITIAL_PACKET,ARMS,ACTION_IDS,CORRECT_IDS,read,write,sha,output_ids,compact_head
from ap_model import load
from ap_eval import generate
from ap_native import Engine,prepare_source,MAX_INPUT_BYTES
from ap_protocol import prompt_ids,Grammar
from ac_verify import verify_parser
from codec_native import native_tokenizer
from codec_common import ROOT as CODEC_ROOT
from native_export import packet
from native_verify import verify_export
from ha_protocol import bytes_text


def choose(report):
    values=[h for n in ['known','novel','scratch']for r in report[n]['details']for h in r['history']if'prompt'in h and'generation'in h and not h['generation'].get('codec_error')]
    result=[];seen=set()
    for action in ['write','run','trace','diag','done','unsure']:
        for h in[h for h in values if h['generation'].get('action')==action][:2]:
            if h['prompt']not in seen:result.append({**h,'forced_action':None});seen.add(h['prompt'])
    for panel in report['diagnosis'].values():
        for kind in ['correct','operation','argument','order']:
            h=next(r for r in panel['details']if r['class']==kind)
            result.append({**h,'forced_action':'diag'})
    longest=max(values,key=lambda h:len(h['prompt'].encode()))
    if longest['prompt']not in seen:result.append({**longest,'forced_action':None})
    return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);root=ap.parse_args().root.resolve();out=root/'native';out.mkdir(exist_ok=True)
    torch.set_num_threads(4)
    for name in ['data-frozen.json','prepared.json']:
        for n,d in json.loads((root/name).read_text())['files'].items():assert sha(root/n)==d,n
    for n,d in json.loads((root/'prepared.json').read_text())['source_hashes'].items():assert sha(HERE/n)==d,n
    prepare_source(root,out,json.loads((CODEC_ROOT/'codebook-32.json').read_text()))
    spec=importlib.util.spec_from_file_location('ap_exporter',out/'source/export_model.py');exporter=importlib.util.module_from_spec(spec);spec.loader.exec_module(exporter)
    source,tokenizer=load('cpu');reference={n:p.detach().clone()for n,p in source.named_parameters()};del source
    parser=verify_parser(out,tokenizer)
    library=C.CDLL(str(out/'action-probe.dylib'));library.ab_accept.argtypes=[C.c_ushort,C.c_char_p];library.ab_body.argtypes=[C.POINTER(C.c_ubyte)]
    for i in range(256):
        body=[i%4,0,i,i,255-i];tokens=[8196,*tokenizer.encode(bytes_text(body),add_special_tokens=False),30];library.ab_reset()
        for t in tokens:assert library.ab_accept(t,tokenizer.decode([t],clean_up_tokenization_spaces=False).encode())
        assert library.ab_complete();actual=(C.c_ubyte*512)();n=library.ab_body(actual);assert list(actual[:n])==body
    parser['localized_diagnostic_roundtrips']=256
    models={};results={};profiles=[*ARMS,*[a+'-terminal'for a in ARMS if(root/'export'/(a+'-terminal')/'manifest.json').exists()]]
    for arm in profiles:
        folder=root/'export'/arm;model,exact=verify_export(folder);models[arm]=model
        for name,p in model.named_parameters():
            if name=='model.embed_tokens.weight':
                mask=torch.ones(len(p),dtype=torch.bool);mask[ACTION_IDS+CORRECT_IDS]=False;assert torch.equal(p[mask],reference[name][mask])
            else:
                adapted=name.startswith('model.layers.')and name.endswith(('.self_attn.q_proj.weight','.self_attn.v_proj.weight','.mlp.gate_proj.weight','.mlp.up_proj.weight','.mlp.down_proj.weight'))
                if not adapted:assert torch.equal(p,reference[name]),(arm,name)
        assert sum(p.numel()for p in model.parameters())==3022080
        compact_head(model,output_ids(tokenizer));native_tokenizer(folder/'hf',out/(arm+'-tokenizer.json'))
        header,payload=packet(folder/'model.mkqb');header['config']['max_position_embeddings']=1024;raw=json.dumps(header,ensure_ascii=False,separators=(',',':')).encode()
        derived=out/(arm+'-context1024.mkqb');derived.write_bytes(b'MKQBv1\0\0'+struct.pack('<I',len(raw))+raw+payload)
        exporter.export(derived,out/(arm+'-tokenizer.json'),folder/'model.mka','lut')
        results[arm]={'exact_reload':exact,'package_bytes':(folder/'model.mka').stat().st_size,'package_sha256':sha(folder/'model.mka'),
          'all_input_rows_and_unadapted_tensors_bit_identical':True}
    engine=Engine(root);long=0
    for arm in profiles:
        base=arm.removesuffix('-terminal');file='terminal-fresh.json'if arm.endswith('-terminal')else'fresh.json'
        report=json.loads((root/base/file).read_text());selected=choose(report);engine.tool=arm;engine.role=None;details=[]
        for h in selected:
            forced=h['forced_action'];p=h['prompt'];cpu=generate(models[arm],tokenizer,[p],forced_action=forced)[0]
            native=engine.generate(p,forced_action=forced);gpu=h['generation']
            assert native.get('input_token_ids')==prompt_ids(tokenizer,p)
            assert native['generated_token_ids']==cpu['generated_token_ids']==gpu['generated_token_ids'],(arm,native,cpu,gpu)
            error=abs(native['correctness_margin']-gpu['correctness_margin']);assert error<.01,(arm,error)
            if len(p.encode())>2048:long+=1
            details.append({'action':gpu['action'],'forced_action':forced,'tokens_equal_B200':True,'margin_error':error,'input_tokens':len(prompt_ids(tokenizer,p))})
        results[arm].update(probes=len(details),cpu_matches=len(details),native_matches=len(details),details=details,
          cache_bytes=engine.lib.mk_ai_cache(),workspace_bytes=engine.lib.mk_ai_workspace())
        print(json.dumps({'verified':arm,'probes':len(details),'maximum_margin_error':max(r['margin_error']for r in details)}),flush=True)
    pre=json.loads((root/'preselected.json').read_text());shutil.copytree(root/'export'/pre['selected_arm'],root/'export/selected-research',dirs_exist_ok=True)
    write(root/'native-verification.json',{'complete':True,'models':results,'parser':parser,'shared_weight_buffer_bytes':engine.capacity,
      'input_rows_and_unadapted_tensors_protected':True,'long_utf8_prefixes_checked':long,'physical_device_measured':False})


if __name__=='__main__':main()
