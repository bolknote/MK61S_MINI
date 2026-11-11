"""Post-exam CPU/MKQB/native checks; never used to select a checkpoint."""
import argparse
import ctypes as C
import importlib.util
import json
from pathlib import Path
import struct
import torch
from transformers import AutoTokenizer
from ay_common import ARMS,INITIAL,ACTION_IDS,write,sha,output_ids,compact_head
from ay_model import load
from aq_eval import generate
from aq_protocol import prompt_ids
from ap_native import Engine as Parent,prepare_source
from ac_verify import verify_parser
from codec_common import ROOT as CODEC_ROOT
from codec_native import native_tokenizer
from native_export import packet
from native_verify import verify_export


class Engine(Parent):
    def __init__(self,root,arm='hex'):
        self.root=Path(root);self.tool=arm;self.role=None;self.forced_action=None
        self.lib=C.CDLL(str(self.root/'native/codec-probe.dylib'))
        self.parser=C.CDLL(str(self.root/'native/action-probe.dylib'));l=self.lib;p=self.parser
        l.mk_ai_open.argtypes=[C.c_void_p,C.c_uint];l.codec_set_mask.argtypes=[C.POINTER(C.c_ushort),C.c_uint]
        l.codec_forward.argtypes=[C.c_ushort,C.c_int,C.POINTER(C.c_ushort),C.POINTER(C.c_float)]
        l.codec_encode.argtypes=[C.c_char_p,C.POINTER(C.c_ushort),C.c_uint,C.POINTER(C.c_uint)]
        l.mk_ai_decode.argtypes=[C.c_ushort,C.c_char_p,C.c_uint,C.POINTER(C.c_uint)]
        p.ab_allows.argtypes=[C.c_ushort,C.c_char_p];p.ab_accept.argtypes=[C.c_ushort,C.c_char_p];p.ab_body.argtypes=[C.POINTER(C.c_ubyte)]
        self.capacity=max((self.root/'export'/a/'model.mka').stat().st_size for a in ARMS)
        self.buffer=C.create_string_buffer(self.capacity);self.loads=0


def choose(report):
    result=[];seen=set()
    def add(prompt,generation,forced=None):
        if generation.get('codec_error')or prompt in seen:return
        result.append({'prompt':prompt,'generation':generation,'forced_action':forced});seen.add(prompt)
    for panel in ['known','novel']:
        values=[r for r in report['primary']['records']if r['panel']==panel and not r['generation'].get('codec_error')]
        for row in values[:2]:add(row['prompt'],row['generation'],'write')
    histories=[h for r in report['raw']['records']for h in r['history']if'generation'in h]
    for action in ['write','run','trace','diag','done','unsure']:
        for h in[h for h in histories if h['generation'].get('action')==action][:2]:add(h['prompt'],h['generation'])
    valid=[h for h in histories if not h['generation'].get('codec_error')]
    if valid:
        h=max(valid,key=lambda x:len(x['prompt'].encode()));add(h['prompt'],h['generation'])
    return result


def main(root):
    assert(root/'complete.json').exists();out=root/'native';out.mkdir(exist_ok=True)
    torch.set_num_threads(4)
    book=json.loads((CODEC_ROOT/'codebook-32.json').read_text());_,_,exporter=prepare_source(root,out,book)
    source,tokenizer=load('cpu');reference={n:p.detach().clone()for n,p in source.named_parameters()};del source
    parser=verify_parser(out,tokenizer);models={};results={}
    for arm in ARMS:
        folder=root/'export'/arm;model,exact=verify_export(folder);models[arm]=model
        for name,p in model.named_parameters():
            if name=='model.embed_tokens.weight':
                keep=torch.ones(len(p),dtype=torch.bool);keep[ACTION_IDS]=False
                assert torch.equal(p[keep],reference[name][keep]),(arm,name)
            elif not(name.startswith('model.layers.')and name.endswith(('.self_attn.q_proj.weight','.self_attn.v_proj.weight','.mlp.gate_proj.weight','.mlp.up_proj.weight','.mlp.down_proj.weight'))):
                assert torch.equal(p,reference[name]),(arm,name)
        assert sum(p.numel()for p in model.parameters())==3022080
        compact_head(model,output_ids(tokenizer));native_tokenizer(folder/'hf',out/(arm+'-tokenizer.json'))
        header,payload=packet(folder/'model.mkqb');header['config']['max_position_embeddings']=1024
        raw=json.dumps(header,ensure_ascii=False,separators=(',',':')).encode();derived=out/(arm+'-context1024.mkqb')
        derived.write_bytes(b'MKQBv1\0\0'+struct.pack('<I',len(raw))+raw+payload)
        assert packet(derived)[1]==payload
        exporter.export(derived,out/(arm+'-tokenizer.json'),folder/'model.mka','lut')
        results[arm]={'exact_export':exact,'mka_bytes':(folder/'model.mka').stat().st_size,'mka_sha256':sha(folder/'model.mka'),
                      'input_dictionary_and_unadapted_tensors_bit_identical':True}
        manifest=json.loads((folder/'manifest.json').read_text());manifest.update(mka_bytes=results[arm]['mka_bytes'],mka_sha256=results[arm]['mka_sha256'])
        write(folder/'manifest.json',manifest)
    engine=Engine(root)
    for arm in ARMS:
        report=json.loads((root/arm/'closed.json').read_text());engine.tool=arm;engine.role=None;details=[]
        for probe in choose(report):
            prompt=probe['prompt'];forced=probe['forced_action'];gpu=probe['generation']
            cpu=generate(models[arm],tokenizer,[prompt],forced_action=forced)[0]
            native=engine.generate(prompt,forced_action=forced)
            assert native.get('input_token_ids')==prompt_ids(tokenizer,prompt)
            assert native['generated_token_ids']==cpu['generated_token_ids']==gpu['generated_token_ids'],(arm,probe,native,cpu)
            details.append({'action':gpu['action'],'forced_action':forced,'input_tokens':len(prompt_ids(tokenizer,prompt)),
                            'CPU_B200_native_streams_identical':True})
        results[arm].update(probes=len(details),details=details,cache_bytes=engine.lib.mk_ai_cache(),workspace_bytes=engine.lib.mk_ai_workspace())
        print(json.dumps({'arm':arm,'native_probes':len(details),'all_equal':True}),flush=True)
    write(root/'native-verification.json',{'complete':True,'models':results,'parser':parser,'context':1024,
             'host_KV_dtype':'FP32','physical_PicoCalc_measured':False,'decoder_source_sha256':sha(Path(__file__)),
             'verification_did_not_select_weights':True})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();main(a.root.resolve())
