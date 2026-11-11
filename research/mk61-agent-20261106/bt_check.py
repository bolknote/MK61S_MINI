"""Pre-freeze CPU parity and observation integration; no new exam inference."""
import collections
import time
import torch
from bt_common import ROOT,BS_ROOT,CONFIGS,read,rows,write,compact_head,output_ids
from bs_model import parent
from bk_independent_generate import generate as old_generate
from bt_decode import generate
import bt_eval


def main():
    torch.set_num_threads(3);model,tok=parent('cpu');compact_head(model,output_ids(tok));started=time.monotonic()
    report=read(BS_ROOT/'server-results/closed-parent_long.json');candidates=[];seen=set()
    for row in report['primary']['records'][:3]:candidates.append((row['prompt'],'write'))
    histories=[h for r in report['own']['records']for h in r['history']if 'generation'in h]
    for action in ['write','run','trace','diag','done','unsure']:
        for h in [h for h in histories if h['generation'].get('action')==action][:2]:candidates.append((h['prompt'],None))
    valid=[h for h in histories if not h['generation'].get('codec_error')]
    for h in sorted(valid,key=lambda h:h['generation'].get('input_tokens',0))[-2:]:candidates.append((h['prompt'],None))
    details=[]
    for prompt,forced in candidates:
        if (prompt,forced)in seen:continue
        seen.add((prompt,forced));old=old_generate(model,tok,[prompt],forced)[0]
        new=generate(model,tok,[prompt],CONFIGS['baseline'],forced)[0]
        assert old['generated_token_ids']==new['generated_token_ids'],(old,new)
        half=generate(model,tok,[prompt],CONFIGS['half1024'],forced)[0]
        details.append({'action':old['action'],'forced':forced,'input_tokens':new['input_tokens'],
           'baseline_exact':True,'half_cache':half.get('cache'),'FP16_same_stream':new['generated_token_ids']==half['generated_token_ids']})
    # Exercise full primary + tools + injected SPEC modes on two opened goals.
    original=bt_eval.rows;small=rows(ROOT/'diagnostic.jsonl');small=[next(g for g in small if g['family']==f)for f in ['unary','composition']]
    bt_eval.rows=lambda p:small
    try:
        smoke=bt_eval.evaluate(model,tok,'diagnostic','combined1536',{'GPU_duty_fraction':1.,'minimum_free_MiB':0})
    finally:bt_eval.rows=original
    write(ROOT/'decoder-smoke.json',{'complete':True,'optimizer_updates':0,'old_FP32_decoder_parity':details,
         'integration':bt_eval.brief(smoke),'seconds':time.monotonic()-started,'new_closed_generations_seen':False})
    print({'complete':True,'parity_probes':len(details),'integration_calls':smoke['calls']['count']},flush=True)


if __name__=='__main__':
    # CPU integration must not inspect a CUDA device.
    bt_eval.headroom=lambda *a,**k:None
    main()
