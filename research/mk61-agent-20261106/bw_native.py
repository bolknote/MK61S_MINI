"""Verify phase dispatch using existing immutable Q4 packages and one buffer."""
import torch
from bw_common import ROOT,BV_RESULTS,MODELS,ROUTES,read,write,sha,check_frozen,output_ids,compact_head
from be_model import load
from bt_decode import generate
from bu_eval import CONFIG
from native_export import packet
from aq_protocol import prompt_ids
import ay_native as native

PHYSICAL={'actor':'original','U':'parent','N':'final'}


def probes(report):
    values=[];seen=set()
    def add(prompt,g):
        if g.get('codec_error'):return
        forced='write'if g['phase']in ['initial','replan']else None
        key=(prompt,g['profile'],forced)
        if key not in seen:seen.add(key);values.append((prompt,g,forced))
    for family in ['composition','unary','binary','constant']:
        row=next(r for r in report['primary']['records']if r['family']==family and not r['generation'].get('codec_error'))
        add(row['prompt'],row['generation'])
    history=[h for panel in ['own','wrong']for r in report[panel]['records']for h in r['history']if'generation'in h and not h['generation'].get('codec_error')]
    for phase in ['replan']:
        for h in [h for h in history if h['generation']['phase']==phase][:2]:add(h['prompt'],h['generation'])
    for action in ['write','run','diag','done','unsure']:
        candidates=[h for h in history if h['generation']['phase']=='actor'and h['generation']['action']==action]
        if candidates:add(candidates[0]['prompt'],candidates[0]['generation'])
    if history:
        h=max(history,key=lambda h:h['generation']['input_tokens']);add(h['prompt'],h['generation'])
    return values


def main():
    check_frozen();root=ROOT/'server-results';assert read(root/'controller-complete.json')['all_own_workers_joined']
    previous=read(BV_RESULTS/'native-verification.json');assert previous['complete']
    models={};tok=None;packages={}
    for profile,folder in MODELS.items():
        model,t=load(folder,'cpu')
        if tok is not None:assert tok.get_vocab()==t.get_vocab()
        tok=t;compact_head(model,output_ids(tok));models[profile]=model
        role=PHYSICAL[profile];native_folder=BV_RESULTS/'export'/role
        assert packet(folder/'model.mkqb')[1]==packet(native_folder/'model.mkqb')[1]
        assert sha(native_folder/'model.mka')==previous['models'][role]['mka_sha256']
        packages[profile]={'physical_profile':role,'mka_sha256':sha(native_folder/'model.mka'),'mka_bytes':(native_folder/'model.mka').stat().st_size}
    native.ARMS=['original','parent','final'];engine=native.Engine(BV_RESULTS,arm='original')
    results={};streams=0;sequence=[]
    for route in ROUTES:
        report=read(root/('closed-'+route+'.json'));details=[]
        for prompt,g,forced in probes(report):
            profile=g['profile'];phase=g['phase'];initial,replan=ROUTES[route]
            assert profile==(initial if phase=='initial'else replan if phase=='replan'else'actor')
            engine.tool=PHYSICAL[profile];cpu=generate(models[profile],tok,[prompt],CONFIG,forced)[0];cpp=engine.generate(prompt,forced)
            assert cpp['input_token_ids']==prompt_ids(tok,prompt)
            assert cpp['generated_token_ids']==cpu['generated_token_ids']==g['generated_token_ids'],(route,phase,profile,cpp,cpu,g)
            details.append({'phase':phase,'profile':profile,'action':g['action'],'input_tokens':g['input_tokens'],'B200_CPU_CPP_equal':True,'cache_hit':g.get('cache_hit')})
            sequence.append(profile)
        results[route]=details;streams+=len(details)
        print({'route':route,'streams_verified':len(details)},flush=True)
    check_frozen()
    write(root/'native-verification.json',{'complete':True,'streams_verified':streams,'routes':results,'packages':packages,
        'physical_profile_sequence':sequence,'profile_loads':engine.loads,'one_weight_buffer_bytes':engine.capacity,
        'KV_bytes':engine.lib.mk_ai_cache(),'workspace_bytes':engine.lib.mk_ai_workspace(),
        'reuses_previously_verified_unchanged_Q4_packages':True,'context':1024,'KV':'FP32',
        'physical_PicoCalc_measured':False,'post_selection_only':True,'source_sha256':sha(__file__)})


if __name__=='__main__':torch.set_num_threads(3);main()
