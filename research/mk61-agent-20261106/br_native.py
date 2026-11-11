"""Post-selection export integrity and B200/CPU/C++ token-stream parity."""
import argparse
import ctypes as C
from pathlib import Path
import json
import shutil
import struct
import torch
from transformers import AutoTokenizer
from br_common import ROOT,read,write,sha,check_frozen,output_ids,compact_head
from native_verify import verify_export
from native_export import packet
from codec_common import ROOT as CODEC_ROOT
from codec_native import native_tokenizer
from ap_native import prepare_source
from ac_verify import verify_parser
from aq_protocol import prompt_ids,header_ids
from bk_independent_generate import generate
import ay_native as base


def choose(report):
    result=[];seen=set()
    def add(prompt,generation,forced):
        if prompt in seen or generation.get('codec_error'):return
        seen.add(prompt);result.append({'prompt':prompt,'generation':generation,'forced_action':forced})
    for r in report['primary']['records'][:2]:add(r['prompt'],r['generation'],'write')
    kinds=set()
    for mode in ['own','gold','wrong']:
        for r in report['modes'][mode]['records']:
            for h in r['history']:
                if 'generation'not in h or 'prompt'not in h or h['kind']in kinds:continue
                if h['generation'].get('codec_error'):continue
                kinds.add(h['kind']);add(h['prompt'],h['generation'],'write'if h['kind']=='replan'else None)
    return result[:16]


def main(root):
    check_frozen();assert read(root/'complete.json')['complete'];out=root/'native-check';out.mkdir(exist_ok=True)
    work=out/'native';work.mkdir(exist_ok=True)
    _,_,exporter=prepare_source(out,work,read(CODEC_ROOT/'codebook-32.json'));models={};results={};reports={};tokenizer=None
    for arm in ['small','large']:
        summary=read(root/arm/'held-out-summary.json')
        for label in summary:
            role=arm+'_'+label;folder=root/'export'/arm/label;model,exact=verify_export(folder)
            tok=AutoTokenizer.from_pretrained(folder/'hf',local_files_only=True)
            if tokenizer is not None:assert tok.get_vocab()==tokenizer.get_vocab()
            tokenizer=tok;compact_head(model,output_ids(tok));models[role]=model
            nativefolder=out/'export'/role;nativefolder.mkdir(parents=True,exist_ok=True)
            native_tokenizer(folder/'hf',work/(role+'-tokenizer.json'))
            header,payload=packet(folder/'model.mkqb');header['config']['max_position_embeddings']=1024
            data=json.dumps(header,ensure_ascii=False,separators=(',',':')).encode();derived=work/(role+'-context1024.mkqb')
            derived.write_bytes(b'MKQBv1\0\0'+struct.pack('<I',len(data))+data+payload)
            assert packet(derived)[1]==payload
            exporter.export(derived,work/(role+'-tokenizer.json'),nativefolder/'model.mka','lut')
            write(nativefolder/'output-token-ids.json',output_ids(tok))
            write(nativefolder/'protocol.json',{'neural_headers':{x:header_ids(tok,x)for x in ['write','run','diag']}})
            shutil.copyfile(nativefolder/'model.mka',folder/'model.mka')
            added={}
            if arm=='large':
                for n,p in model.named_parameters():
                    if n.startswith('model.layers.')and int(n.split('.')[2])%2 and n.endswith(('.self_attn.o_proj.weight','.mlp.down_proj.weight')):
                        added[n]={'nonzero':int(torch.count_nonzero(p)),'l2_norm':float(p.norm())}
                assert len(added)==20 and all(x['nonzero']>0 for x in added.values()),'Larger model blocks did not activate'
            results[role]={'exact_export':exact,'mka_bytes':(folder/'model.mka').stat().st_size,'mka_sha256':sha(folder/'model.mka'),
                           'added_Q4_output_projections':added,'actual_parameter_count':sum(p.numel()for p in model.parameters())}
            reports[role]=read(root/arm/(label+'-new_ast.json'))
    parser=verify_parser(work,tokenizer);base.ARMS=list(models);engine=base.Engine(out);count=0
    for role,model in models.items():
        engine.tool=role;engine.role=None;details=[]
        for probe in choose(reports[role]):
            prompt=probe['prompt'];forced=probe['forced_action'];gpu=probe['generation']
            cpu=generate(model,tokenizer,[prompt],forced)[0];native=engine.generate(prompt,forced)
            assert native['input_token_ids']==prompt_ids(tokenizer,prompt)
            assert native['generated_token_ids']==cpu['generated_token_ids']==gpu['generated_token_ids'],(role,probe,native,cpu)
            details.append({'action':gpu['action'],'input_tokens':len(prompt_ids(tokenizer,prompt)),'forced_action':forced,'B200_CPU_CPP_equal':True})
        results[role].update(probes=len(details),details=details,cache_bytes=engine.lib.mk_ai_cache(),workspace_bytes=engine.lib.mk_ai_workspace())
        count+=len(details);print(json.dumps({'role':role,'probes':len(details),'all_equal':True}),flush=True)
    check_frozen();write(root/'native-verification.json',{'complete':True,'models':results,'parser':parser,'streams_verified':count,
        'context':1024,'host_KV_dtype':'FP32','physical_PicoCalc_measured':False,'no_model_selection':True,'source_sha256':sha(__file__)})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT/'server-results');args=p.parse_args()
    torch.set_num_threads(4);main(args.root)
