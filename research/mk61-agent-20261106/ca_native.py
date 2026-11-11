"""Check real actor streams for every section and the unchanged translator."""
import torch
from ca_common import ROOT,BX_RESULTS,ACTOR,PARENT,VARIANTS,read,write,sha,check_frozen,output_ids,compact_head
from by_native import choose
from be_model import load
from bu_model import frozen_digest
from bt_decode import generate
from bu_eval import CONFIG
from aq_protocol import prompt_ids
import ay_native as native


def main():
    check_frozen();root=ROOT/'server-results';assert read(root/'controller-complete.json')['all_own_workers_joined']
    roles=read(root/'audit-roles.json');reports={name:read(root/name)for name in roles['evaluated']}
    models={};info={};tok=None
    for role,folder in [('actor',ACTOR),('parent',PARENT)]:
        assert sha(folder/'model.mka')==sha(BX_RESULTS/'export'/role/'model.mka')
        model,t=load(folder,'cpu')
        if tok is not None:assert tok.get_vocab()==t.get_vocab()
        tok=t;compact_head(model,output_ids(tok));models[role]=model
        info[role]={'digest':frozen_digest(model),'mka_sha256':sha(folder/'model.mka')}
    completed=read(root/'complete.json')
    assert info['actor']['digest']==completed['actor_digest']and info['parent']['digest']==completed['translator_digest']
    probes=[]
    for variant in VARIANTS:
        values=[r for r in reports.values()if r['format']==variant]
        for h in choose(values):probes.append({'variant':variant,'profile':'actor','prompt':h['prompt'],'generation':h['generation'],'forced':None})
    own=reports[f"closed-{roles['audit_variant']}-own.json"]
    for r in own['primary']['records'][:2]:
        if not r['generation'].get('codec_error'):probes.append({'variant':None,'profile':'parent','prompt':r['prompt'],'generation':r['generation'],'forced':'write'})
    replans=[h for r in own['own']['records']for h in r['history']if h['kind']=='replan'and not h.get('generation',{}).get('codec_error')]
    for h in replans[:2]:probes.append({'variant':None,'profile':'parent','prompt':h['prompt'],'generation':h['generation'],'forced':'write'})
    native.ARMS=['actor','parent'];engine=native.Engine(BX_RESULTS,arm='actor');details=[];seen=set()
    for p in probes:
        key=p['profile'],p['prompt'],p['forced']
        if key in seen:continue
        seen.add(key);role=p['profile'];engine.tool=role
        gpu=p['generation'];cpu=generate(models[role],tok,[p['prompt']],CONFIG,p['forced'])[0];cpp=engine.generate(p['prompt'],p['forced'])
        assert cpp['input_token_ids']==prompt_ids(tok,p['prompt'])
        assert cpp['generated_token_ids']==cpu['generated_token_ids']==gpu['generated_token_ids'],(p,cpu,cpp)
        details.append({'variant':p['variant'],'profile':role,'action':gpu['action'],'input_tokens':gpu['input_tokens'],'B200_CPU_CPP_equal':True})
        print({'streams_verified':len(details),**details[-1]},flush=True)
    for role,model in models.items():assert frozen_digest(model)==info[role]['digest']
    check_frozen();write(root/'native-verification.json',{'complete':True,'streams_verified':len(details),'details':details,'models':info,
        'all_three_variants_verified':all(any(r['variant']==v for r in details)for v in VARIANTS),
        'one_weight_buffer_bytes':engine.capacity,'KV_bytes':engine.lib.mk_ai_cache(),'workspace_bytes':engine.lib.mk_ai_workspace(),
        'context':1024,'KV':'FP32','physical_PicoCalc_measured':False,'optimizer_updates':0,'source_sha256':sha(__file__)})


if __name__=='__main__':torch.set_num_threads(3);main()
