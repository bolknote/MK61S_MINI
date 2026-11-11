"""Verify DIAG-row-only Q4 changes and actual B200/CPU/C++ action streams."""
import json
import shutil
import struct
import torch
from cd_common import ROOT,ACTOR,WORKING,PARENT,read,write,sha,check_frozen,output_ids,compact_head,ACTION_IDS
from cd_model import ROWS
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
    roles=read(root/'audit-roles.json');out=root/'native';out.mkdir(exist_ok=True)
    _,_,exporter=prepare_source(root,out,read(CODEC_ROOT/'codebook-32.json'))
    shutil.copytree(WORKING/'hf',root/'export/working/hf',dirs_exist_ok=True);shutil.copytree(ACTOR/'hf',root/'export/parent/hf',dirs_exist_ok=True);shutil.copytree(PARENT,root/'export/translator',dirs_exist_ok=True)
    models={};info={};tok=None
    for role in [*roles['evaluated'],'translator']:
        folder=root/'export'/role;model,exact=verify_export(folder)
        from transformers import AutoTokenizer
        t=AutoTokenizer.from_pretrained(folder/'hf',local_files_only=True)
        if tok is not None:assert tok.get_vocab()==t.get_vocab()
        tok=t;models[role]=model;compact_head(model,output_ids(tok))
        h,payload=packet(folder/'model.mkqb');h['config']['max_position_embeddings']=1024;raw=json.dumps(h,ensure_ascii=False,separators=(',',':')).encode()
        derived=out/(role+'.mkqb');derived.write_bytes(b'MKQBv1\0\0'+struct.pack('<I',len(raw))+raw+payload)
        assert packet(derived)[1]==payload
        native_tokenizer(folder/'hf',out/(role+'-tokenizer.json'));exporter.export(derived,out/(role+'-tokenizer.json'),folder/'model.mka','lut')
        write(folder/'output-token-ids.json',output_ids(tok));write(folder/'protocol.json',{'neural_headers':{a:header_ids(tok,a)for a in ['write','run','diag']}})
        info[role]={'exact_export':exact,'mka_bytes':(folder/'model.mka').stat().st_size,'mka_sha256':sha(folder/'model.mka')}
    for role,source in [('parent',ACTOR),('working',WORKING),('translator',PARENT)]:assert sha(root/f'export/{role}/model.mka')==sha(source/'model.mka')
    reference=dict(models['parent'].named_parameters())
    for role,model in models.items():
        if role in ['parent','working','translator']:continue
        changed=[]
        for name,p in model.named_parameters():
            q=reference[name]
            if torch.equal(p,q):continue
            assert name=='model.embed_tokens.weight'
            mask=torch.ones(len(p),dtype=torch.bool);mask[[ACTION_IDS[i]for i in ROWS]]=False
            assert torch.equal(p[mask],q[mask]);changed=[i for i in ACTION_IDS if not torch.equal(p[i],q[i])]
        info[role].update(changed_action_token_rows=changed,all_body_and_encoder_weights_exactly_equal=True)
    parser=verify_parser(out,tok);native.ARMS=list(models);engine=native.Engine(root,arm='parent');details=[]
    for role in roles['evaluated']:
        report=read(root/f'closed-{role}.json')
        for h in choose([report]):
            engine.tool=role;gpu=h['generation'];cpu=generate(models[role],tok,[h['prompt']],CONFIG,None)[0];cpp=engine.generate(h['prompt'],None)
            assert cpp['input_token_ids']==prompt_ids(tok,h['prompt'])and cpp['generated_token_ids']==cpu['generated_token_ids']==gpu['generated_token_ids']
            details.append({'profile':role,'action':gpu['action'],'input_tokens':gpu['input_tokens'],'B200_CPU_CPP_equal':True})
            print({'streams_verified':len(details),**details[-1]},flush=True)
    conditional=[]
    trained=[r for r in roles['evaluated']if r not in ['parent','working']]
    if trained:
        model=models[trained[-1]];report=read(root/'closed-parent.json');hist=[h for r in report['own']['records']for h in r['history']if h.get('generation')and not h['generation'].get('codec_error')]
        for action in ['write','run','diag']:
            for h in [h for h in hist if h['generation']['action']==action][:2]:
                a=generate(models['parent'],tok,[h['prompt']],CONFIG,action)[0];b=generate(model,tok,[h['prompt']],CONFIG,action)[0]
                assert a['generated_token_ids']==b['generated_token_ids'];conditional.append({'forced_action':action,'input_tokens':a['input_tokens'],'body_unchanged':True})
    probes=read(root/'closed-parent.json')['primary']['records'][:2]
    for r in probes:
        gpu=r['generation'];engine.tool='translator';cpu=generate(models['translator'],tok,[r['prompt']],CONFIG,'write')[0];cpp=engine.generate(r['prompt'],'write')
        assert cpp['generated_token_ids']==cpu['generated_token_ids']==gpu['generated_token_ids']
        details.append({'profile':'translator','action':'write','input_tokens':gpu['input_tokens'],'B200_CPU_CPP_equal':True})
    for alias,source in roles['aliases'].items():
        while source in roles['aliases']:source=roles['aliases'][source]
        shutil.copytree(root/'export'/source,root/'export'/alias,dirs_exist_ok=True);info[alias]={'same_as':source}
    check_frozen();write(root/'native-verification.json',{'complete':True,'streams_verified':len(details),'details':details,'models':info,'parser':parser,
        'conditional_body_checks':conditional,'one_weight_buffer_bytes':engine.capacity,'KV_bytes':engine.lib.mk_ai_cache(),'workspace_bytes':engine.lib.mk_ai_workspace(),
        'context':1024,'KV':'FP32','physical_PicoCalc_measured':False,'translator_unchanged':True,'source_sha256':sha(__file__)})

if __name__=='__main__':torch.set_num_threads(3);main()
