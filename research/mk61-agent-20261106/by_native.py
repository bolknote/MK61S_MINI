"""Recheck actual oracle-run actor streams against CPU and the existing C++ engine."""
import torch
from by_common import ROOT,BX_RESULTS,ACTOR,read,write,sha,check_frozen,output_ids,compact_head
from be_model import load
from bu_model import frozen_digest
from bt_decode import generate
from bu_eval import CONFIG
from aq_protocol import prompt_ids
import ay_native as native


def choose(reports):
    histories=[h for r in reports for episode in r['own']['records'] for h in episode['history']
               if h.get('generation',{}).get('profile')=='actor' and not h['generation'].get('codec_error')]
    result=[];seen=set()
    def add(h):
        if h['prompt'] not in seen:result.append(h);seen.add(h['prompt'])
    for action in ['write','run','trace','diag','done','unsure']:
        for h in [v for v in histories if v['generation']['action']==action][:2]:add(h)
    for r in reports:
        for start in [True,False]:
            for e in [v for v in r['own']['records']if v['initially_correct']==start and not v['pass']][:2]:
                valid=[h for h in e['history']if h.get('generation',{}).get('profile')=='actor' and not h['generation'].get('codec_error')]
                if valid:add(valid[-1])
    if histories:
        for h in sorted(histories,key=lambda h:h['generation']['input_tokens'])[-2:]:add(h)
    return result


def main():
    check_frozen();root=ROOT/'server-results';assert read(root/'controller-complete.json')['all_own_workers_joined']
    reports=[read(root/(s+'-gold.json'))for s in ['development','closed']]
    assert sha(ACTOR/'model.mka')==sha(BX_RESULTS/'export/actor/model.mka')
    actor,tok=load(ACTOR,'cpu');compact_head(actor,output_ids(tok));before=frozen_digest(actor)
    assert before==read(root/'complete.json')['actor_digest']
    native.ARMS=['actor'];engine=native.Engine(BX_RESULTS,arm='actor');details=[]
    for probe in choose(reports):
        p=probe['prompt'];gpu=probe['generation'];cpu=generate(actor,tok,[p],CONFIG,None)[0];cpp=engine.generate(p,None)
        assert cpp['input_token_ids']==prompt_ids(tok,p)
        assert cpp['generated_token_ids']==cpu['generated_token_ids']==gpu['generated_token_ids'],(probe,cpu,cpp)
        details.append({'action':gpu['action'],'input_tokens':gpu['input_tokens'],'B200_CPU_CPP_equal':True})
        print({'streams_verified':len(details),'action':gpu['action'],'input_tokens':gpu['input_tokens']},flush=True)
    assert frozen_digest(actor)==before;check_frozen()
    write(root/'native-verification.json',{'complete':True,'streams_verified':len(details),'details':details,
        'actor_mka_sha256':sha(ACTOR/'model.mka'),'actor_digest':before,'one_weight_buffer_bytes':engine.capacity,
        'KV_bytes':engine.lib.mk_ai_cache(),'workspace_bytes':engine.lib.mk_ai_workspace(),'context':1024,'KV':'FP32',
        'oracle_responses_are_not_LM_streams':True,'oracle_codec_checks':read(ROOT/'CPU-preflight.json')['oracle_codec_context_checks'],
        'physical_PicoCalc_measured':False,'optimizer_updates':0,'source_sha256':sha(__file__)})


if __name__=='__main__':torch.set_num_threads(3);main()
