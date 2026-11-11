"""Verify merged actor Q4 exports, frozen translation and portable C++ streams."""
import json
import shutil
import struct
import subprocess
import sys
import torch
from cb_common import ROOT,HERE,ACTOR,PARENT,read,write,sha,check_frozen,output_ids,compact_head
from by_native import choose
from native_verify import verify_export
from native_export import packet
from codec_common import ROOT as CODEC_ROOT
from codec_native import native_tokenizer
from ap_native import prepare_source
from ac_verify import verify_parser
from bt_decode import generate
from bu_eval import CONFIG
from aq_protocol import prompt_ids,header_ids
import ay_native as native


def main():
    check_frozen();root=ROOT/'server-results';assert read(root/'controller-complete.json')['all_own_workers_joined']
    if(ROOT/'extra-protocol.json').exists()and not(root/'extra-complete.json').exists():
        subprocess.run([sys.executable,'-u',str(HERE/'cb_extra_remote.py')],check=True)
    roles=read(root/'audit-roles.json')
    if(root/'extra-complete.json').exists():
        extra=read(root/'extra-complete.json');assert extra['complete']and not extra['used_for_selection']
        assert extra['protocol_sha256']==sha(ROOT/'extra-protocol.json')==sha(root/'extra-protocol.json')
        for role,formats in extra['additional_formats'].items():
            roles['evaluated'][role]=list(dict.fromkeys([*roles['evaluated'][role],*formats]))
        write(root/'analysis-audit-roles.json',roles)
    out=root/'native';out.mkdir(exist_ok=True)
    _,_,exporter=prepare_source(root,out,read(CODEC_ROOT/'codebook-32.json'))
    shutil.copytree(ACTOR/'hf',root/'export/parent/hf',dirs_exist_ok=True)
    shutil.copytree(PARENT,root/'export/translator',dirs_exist_ok=True)
    models={};info={};tok=None
    for role in [*roles['evaluated'],'translator']:
        folder=root/'export'/role;model,exact=verify_export(folder)
        from transformers import AutoTokenizer
        t=AutoTokenizer.from_pretrained(folder/'hf',local_files_only=True)
        if tok is not None:assert tok.get_vocab()==t.get_vocab()
        tok=t;models[role]=model;compact_head(model,output_ids(tok))
        h,payload=packet(folder/'model.mkqb');h['config']['max_position_embeddings']=1024;raw=json.dumps(h,ensure_ascii=False,separators=(',',':')).encode()
        derived=out/(role+'.mkqb');derived.write_bytes(b'MKQBv1\0\0'+struct.pack('<I',len(raw))+raw+payload);assert packet(derived)[1]==payload
        native_tokenizer(folder/'hf',out/(role+'-tokenizer.json'));exporter.export(derived,out/(role+'-tokenizer.json'),folder/'model.mka','lut')
        write(folder/'output-token-ids.json',output_ids(tok));write(folder/'protocol.json',{'neural_headers':{a:header_ids(tok,a)for a in ['write','run','diag']}})
        info[role]={'exact_export':exact,'mka_bytes':(folder/'model.mka').stat().st_size,'mka_sha256':sha(folder/'model.mka')}
    assert sha(root/'export/parent/model.mka')==sha(ACTOR/'model.mka')
    assert sha(root/'export/translator/model.mka')==sha(PARENT/'model.mka')
    reference=dict(models['parent'].named_parameters())
    for role,model in models.items():
        changed=[]
        for name,p in model.named_parameters():
            if torch.equal(p,reference[name]):continue
            assert name.endswith(('.self_attn.q_proj.weight','.self_attn.v_proj.weight','.mlp.gate_proj.weight','.mlp.up_proj.weight','.mlp.down_proj.weight')),(role,name)
            changed.append(name)
        info[role].update(changed_Q4_matrices=changed,embeddings_and_action_rows_unchanged=True)
    parser=verify_parser(out,tok);native.ARMS=list(models);engine=native.Engine(root,arm='parent');details=[];seen=set()
    for role,formats in roles['evaluated'].items():
        reports=[read(root/f'closed-{role}-{format}.json')for format in formats]
        for h in choose(reports):
            key=role,h['prompt'],None
            if key in seen:continue
            seen.add(key);engine.tool=role;gpu=h['generation'];cpu=generate(models[role],tok,[h['prompt']],CONFIG,None)[0];cpp=engine.generate(h['prompt'],None)
            assert cpp['input_token_ids']==prompt_ids(tok,h['prompt'])
            assert cpp['generated_token_ids']==cpu['generated_token_ids']==gpu['generated_token_ids'],(role,h,cpu,cpp)
            details.append({'profile':role,'action':gpu['action'],'input_tokens':gpu['input_tokens'],'B200_CPU_CPP_equal':True})
            print({'streams_verified':len(details),**details[-1]},flush=True)
    reference_report=read(root/'closed-parent-notes.json');probes=[]
    for r in reference_report['primary']['records'][:2]:probes.append({'prompt':r['prompt'],'generation':r['generation']})
    for h in [h for r in reference_report['own']['records']for h in r['history']if h['kind']=='replan'][:2]:probes.append(h)
    for h in probes:
        gpu=h['generation']
        if gpu.get('codec_error'):continue
        engine.tool='translator';cpu=generate(models['translator'],tok,[h['prompt']],CONFIG,'write')[0];cpp=engine.generate(h['prompt'],'write')
        assert cpp['input_token_ids']==prompt_ids(tok,h['prompt'])and cpp['generated_token_ids']==cpu['generated_token_ids']==gpu['generated_token_ids']
        details.append({'profile':'translator','action':'write','input_tokens':gpu['input_tokens'],'B200_CPU_CPP_equal':True})
    for alias,source in roles['aliases'].items():
        while source in roles['aliases']:source=roles['aliases'][source]
        shutil.copytree(root/'export'/source,root/'export'/alias,dirs_exist_ok=True);info[alias]={'same_as':source}
    check_frozen();write(root/'native-verification.json',{'complete':True,'streams_verified':len(details),'details':details,'models':info,'parser':parser,
        'one_weight_buffer_bytes':engine.capacity,'KV_bytes':engine.lib.mk_ai_cache(),'workspace_bytes':engine.lib.mk_ai_workspace(),
        'context':1024,'KV':'FP32','physical_PicoCalc_measured':False,'translator_unchanged':True,'source_sha256':sha(__file__)})


if __name__=='__main__':torch.set_num_threads(3);main()
