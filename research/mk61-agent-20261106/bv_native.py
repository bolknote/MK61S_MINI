"""Post-selection Q4 export and one-buffer native checks for the recovery."""
import json
import shutil
import struct
import torch
from transformers import AutoTokenizer
from bv_common import ROOT,SOURCE,PARENT,read,write,sha,check_frozen,output_ids,compact_head
from bv_eval import CONFIG
from bu_native import choose
from bt_decode import generate
from native_verify import verify_export
from native_export import packet
from codec_common import ROOT as CODEC_ROOT
from codec_native import native_tokenizer
from ap_native import prepare_source
from ac_verify import verify_parser
from aq_protocol import prompt_ids,header_ids
import ay_native as native


def main():
    check_frozen();root=ROOT/'server-results'
    assert read(root/'controller-complete.json')['all_own_workers_joined']
    out=root/'native';out.mkdir(exist_ok=True)
    _,_,exporter=prepare_source(root,out,read(CODEC_ROOT/'codebook-32.json'))
    roles=read(root/'audit-roles.json');assert roles['evaluated']==['original','parent','final']
    models={};info={};tok=None
    for role in roles['evaluated']:
        folder=root/'export'/role;m,exact=verify_export(folder)
        t=AutoTokenizer.from_pretrained(folder/'hf',local_files_only=True)
        if tok is not None:assert tok.get_vocab()==t.get_vocab()
        tok=t;models[role]=m;compact_head(m,output_ids(tok))
        h,p=packet(folder/'model.mkqb');h['config']['max_position_embeddings']=1024
        raw=json.dumps(h,ensure_ascii=False,separators=(',',':')).encode()
        derived=out/(role+'.mkqb')
        derived.write_bytes(b'MKQBv1\0\0'+struct.pack('<I',len(raw))+raw+p)
        assert packet(derived)[1]==p
        native_tokenizer(folder/'hf',out/(role+'-tokenizer.json'))
        exporter.export(derived,out/(role+'-tokenizer.json'),folder/'model.mka','lut')
        write(folder/'output-token-ids.json',output_ids(tok))
        write(folder/'protocol.json',{'neural_headers':{a:header_ids(tok,a)for a in ['write','run','diag']}})
        info[role]={'export':exact,'mka_bytes':(folder/'model.mka').stat().st_size,'mka_sha256':sha(folder/'model.mka')}
    assert sha(root/'export/original/model.mka')==sha(SOURCE/'model.mka')
    assert sha(root/'export/parent/model.mka')==sha(PARENT/'model.mka')
    reference=dict(models['original'].named_parameters())
    for role,m in models.items():
        changed=[]
        for name,param in m.named_parameters():
            if torch.equal(param,reference[name]):continue
            assert name.endswith(('.self_attn.q_proj.weight','.self_attn.v_proj.weight','.mlp.gate_proj.weight','.mlp.up_proj.weight','.mlp.down_proj.weight')),(role,name)
            changed.append(name)
        info[role]['changed_Q4_matrices']=changed
        info[role]['input_embeddings_and_action_rows_unchanged']=True
    parser=verify_parser(out,tok);native.ARMS=roles['evaluated']
    engine=native.Engine(root,arm='original');streams=0;allprofiles=[]
    for role in roles['evaluated']:
        details=[]
        for probe in choose(read(root/('closed-'+role+'.json'))):
            profile=role if probe['profile']=='translator'else'original'
            engine.tool=profile;p=probe['prompt'];forced=probe['forced'];gpu=probe['generation']
            cpu=generate(models[profile],tok,[p],CONFIG,forced)[0];cpp=engine.generate(p,forced)
            assert cpp['input_token_ids']==prompt_ids(tok,p)
            assert cpp['generated_token_ids']==cpu['generated_token_ids']==gpu['generated_token_ids'],(role,profile,probe,cpp,cpu)
            details.append({'phase':probe['profile'],'physical_profile':profile,'action':gpu['action'],
                'input_tokens':len(prompt_ids(tok,p)),'B200_CPU_CPP_equal':True})
            allprofiles.append(profile)
        info[role].update(probes=len(details),details=details,KV_bytes=engine.lib.mk_ai_cache(),workspace_bytes=engine.lib.mk_ai_workspace())
        streams+=len(details);print({'role':role,'verified_streams':len(details)},flush=True)
    for alias,source in roles['aliases'].items():
        info[alias]={'same_profile_as':source}
        shutil.copytree(root/'export'/source,root/'export'/alias,dirs_exist_ok=True)
    check_frozen()
    write(root/'native-verification.json',{'complete':True,'streams_verified':streams,'models':info,'parser':parser,
        'one_weight_buffer_bytes':engine.capacity,'profile_loads':engine.loads,'physical_profile_sequence':allprofiles,
        'context':1024,'KV':'FP32','physical_PicoCalc_measured':False,'post_selection_only':True,'source_sha256':sha(__file__)})


if __name__=='__main__':torch.set_num_threads(3);main()
