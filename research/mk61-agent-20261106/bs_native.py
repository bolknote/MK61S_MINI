"""Post-exam exact exports and token-stream parity; no checkpoint selection."""
import argparse
import json
from pathlib import Path
import shutil
import struct
import torch
from transformers import AutoTokenizer
from bs_common import ROOT,read,write,sha,output_ids,compact_head,check_frozen
from br_native import choose
from native_verify import verify_export
from native_export import packet
from codec_common import ROOT as CODEC_ROOT
from codec_native import native_tokenizer
from ap_native import prepare_source
from ac_verify import verify_parser
from aq_protocol import prompt_ids,header_ids
from bk_independent_generate import generate
import ay_native as base


def main(root):
    check_frozen();assert read(root/'controller-complete.json')['all_own_workers_joined'];out=root/'native';out.mkdir(exist_ok=True)
    _,_,exporter=prepare_source(root,out,read(CODEC_ROOT/'codebook-32.json'));roles=read(root/'audit-roles.json');models={};results={};tok=None
    for role in roles['evaluated']:
        folder=root/'export'/role;m,exact=verify_export(folder);t=AutoTokenizer.from_pretrained(folder/'hf',local_files_only=True)
        if tok is not None:assert t.get_vocab()==tok.get_vocab()
        tok=t;compact_head(m,output_ids(tok));models[role]=m
        native_tokenizer(folder/'hf',out/(role+'-tokenizer.json'));h,p=packet(folder/'model.mkqb');h['config']['max_position_embeddings']=1024
        data=json.dumps(h,ensure_ascii=False,separators=(',',':')).encode();derived=out/(role+'-1024.mkqb')
        derived.write_bytes(b'MKQBv1\0\0'+struct.pack('<I',len(data))+data+p);assert packet(derived)[1]==p
        exporter.export(derived,out/(role+'-tokenizer.json'),folder/'model.mka','lut')
        profile=read(folder/'manifest.json')['profile']
        write(folder/'output-token-ids.json',output_ids(tok));write(folder/'protocol.json',{
            'kind':'spec-intent-recovery-v1'if profile=='long'else'spec-compact-own-errors-v1','output_arm':'spec','codec':'ay_codec.py',
            'context':1024,'max_actions':12,'reserve':160 if profile=='compact'else None,
            'missing_public_RUNs_deterministic':True,'uncompleted_candidates_rolled_back':True,
            'neural_headers':{x:header_ids(tok,x)for x in ['write','run','diag']}})
        results[role]={'exact_export':exact,'mka_bytes':(folder/'model.mka').stat().st_size,'mka_sha256':sha(folder/'model.mka')}
    parser=verify_parser(out,tok);base.ARMS=roles['evaluated'];engine=base.Engine(root);total=0
    for role,m in models.items():
        engine.tool=role;engine.role=None;r=read(root/('closed-'+role+'.json'))
        probes=choose({'primary':r['primary'],'modes':{'own':r['own'],'wrong':r['wrong'],'gold':r['recovery']or{'records':[]}}});details=[]
        for probe in probes:
            p=probe['prompt'];forced=probe['forced_action'];gpu=probe['generation'];cpu=generate(m,tok,[p],forced)[0];native=engine.generate(p,forced)
            assert native['input_token_ids']==prompt_ids(tok,p)
            assert native['generated_token_ids']==cpu['generated_token_ids']==gpu['generated_token_ids'],(role,probe,native,cpu)
            details.append({'action':gpu['action'],'input_tokens':len(prompt_ids(tok,p)),'B200_CPU_CPP_equal':True})
        total+=len(details);results[role].update(probes=len(details),details=details,KV_bytes=engine.lib.mk_ai_cache(),workspace_bytes=engine.lib.mk_ai_workspace())
        print(json.dumps({'role':role,'probes':len(details),'all_equal':True}),flush=True)
    for role,source in roles['aliases'].items():
        for filename in ['model.mka','output-token-ids.json','protocol.json']:
            shutil.copyfile(root/'export'/source/filename,root/'export'/role/filename)
        results[role]={'same_weights_runtime_and_probes_as':source}
    check_frozen();write(root/'native-verification.json',{'complete':True,'models':results,'streams_verified':total,'parser':parser,
        'physical_PicoCalc_measured':False,'context':1024,'KV_dtype':'host FP32','selection_changed':False,'source_sha256':sha(__file__)})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT/'server-results');args=p.parse_args();torch.set_num_threads(3);main(args.root)
