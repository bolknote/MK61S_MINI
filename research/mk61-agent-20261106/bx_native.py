"""Verify merged Q4, frozen actor, phase probes and one-buffer native dispatch."""
import json
import shutil
import struct
import torch
from transformers import AutoTokenizer
from bx_common import ROOT,ACTOR,PARENT,read,write,sha,check_frozen,output_ids,compact_head
from bu_native import choose
from bt_decode import generate
from bu_eval import CONFIG
from native_verify import verify_export
from native_export import packet
from codec_common import ROOT as CODEC_ROOT
from codec_native import native_tokenizer
from ap_native import prepare_source
from ac_verify import verify_parser
from aq_protocol import prompt_ids,header_ids
import ay_native as native


def main():
    check_frozen();root=ROOT/'server-results';assert read(root/'controller-complete.json')['all_own_workers_joined']
    out=root/'native';out.mkdir(exist_ok=True);_,_,exporter=prepare_source(root,out,read(CODEC_ROOT/'codebook-32.json'))
    roles=read(root/'audit-roles.json');assert roles['evaluated']==['parent','final']
    shutil.copytree(ACTOR,root/'export/actor',dirs_exist_ok=True)
    shutil.copytree(PARENT/'hf',root/'export/parent/hf',dirs_exist_ok=True)
    models={};info={};tok=None
    for role in ['actor',*roles['evaluated']]:
        folder=root/'export'/role;m,exact=verify_export(folder);t=AutoTokenizer.from_pretrained(folder/'hf',local_files_only=True)
        if tok is not None:assert tok.get_vocab()==t.get_vocab()
        tok=t;models[role]=m;compact_head(m,output_ids(tok))
        h,p=packet(folder/'model.mkqb');h['config']['max_position_embeddings']=1024;raw=json.dumps(h,ensure_ascii=False,separators=(',',':')).encode()
        derived=out/(role+'.mkqb');derived.write_bytes(b'MKQBv1\0\0'+struct.pack('<I',len(raw))+raw+p);assert packet(derived)[1]==p
        native_tokenizer(folder/'hf',out/(role+'-tokenizer.json'));exporter.export(derived,out/(role+'-tokenizer.json'),folder/'model.mka','lut')
        write(folder/'output-token-ids.json',output_ids(tok));write(folder/'protocol.json',{'neural_headers':{a:header_ids(tok,a)for a in ['write','run','diag']}})
        info[role]={'exact_export':exact,'mka_bytes':(folder/'model.mka').stat().st_size,'mka_sha256':sha(folder/'model.mka')}
    assert sha(root/'export/actor/model.mka')==sha(ACTOR/'model.mka')
    assert sha(root/'export/parent/model.mka')==sha(PARENT/'model.mka')
    reference=dict(models['actor'].named_parameters())
    for role,model in models.items():
        changed=[]
        for name,p in model.named_parameters():
            if torch.equal(p,reference[name]):continue
            assert name.endswith(('.self_attn.q_proj.weight','.self_attn.v_proj.weight','.mlp.gate_proj.weight','.mlp.up_proj.weight','.mlp.down_proj.weight')),(role,name)
            changed.append(name)
        info[role].update(changed_Q4_matrices=changed,input_embeddings_and_action_rows_unchanged=True)
    parser=verify_parser(out,tok);native.ARMS=['actor','parent','final'];engine=native.Engine(root,arm='actor');streams=0;sequence=[]
    for role in roles['evaluated']:
        r=read(root/('closed-'+role+'.json'));probes=choose(r)
        for family in ['composition','unary','binary','constant']:
            x=next(v for v in r['paired']['records']if v['family']==family and not v['generation'].get('codec_error'))
            probes.append({'prompt':x['prompt'],'generation':x['generation'],'forced':'write','profile':'translator'})
        details=[]
        for probe in probes:
            profile=role if probe['profile']=='translator'else'actor';engine.tool=profile;p=probe['prompt'];forced=probe['forced'];gpu=probe['generation']
            cpu=generate(models[profile],tok,[p],CONFIG,forced)[0];cpp=engine.generate(p,forced)
            assert cpp['input_token_ids']==prompt_ids(tok,p)
            assert cpp['generated_token_ids']==cpu['generated_token_ids']==gpu['generated_token_ids'],(role,profile,probe,cpp,cpu)
            details.append({'phase':gpu['phase'],'profile':profile,'action':gpu['action'],'input_tokens':gpu['input_tokens'],'B200_CPU_CPP_equal':True});sequence.append(profile)
        info[role]['probes']=len(details);info[role]['details']=details;streams+=len(details)
        print({'role':role,'streams_verified':len(details)},flush=True)
    for alias,source in roles['aliases'].items():
        shutil.copytree(root/'export'/source,root/'export'/alias,dirs_exist_ok=True);info[alias]={'same_as':source}
    check_frozen();write(root/'native-verification.json',{'complete':True,'streams_verified':streams,'models':info,'parser':parser,
        'one_weight_buffer_bytes':engine.capacity,'KV_bytes':engine.lib.mk_ai_cache(),'workspace_bytes':engine.lib.mk_ai_workspace(),
        'profile_loads':engine.loads,'physical_profile_sequence':sequence,'context':1024,'KV':'FP32','physical_PicoCalc_measured':False,
        'post_selection_only':True,'source_sha256':sha(__file__)})


if __name__=='__main__':torch.set_num_threads(3);main()
