"""Check newly induced oracle-feedback prompts with the existing native Q4 decoder."""
import argparse
import json
import torch
from transformers import AutoTokenizer
import ay_native as base
from bd_common import ROOT,PARENT,MODEL,read,write,rows,sha,check_frozen,compact_head,output_ids
from native_verify import verify_export
from aq_eval import generate
from aq_protocol import prompt_ids


def main(root):
    check_frozen();assert read(root/'complete.json')['complete']
    values=rows(root/'new-generations.jsonl');valid=[r for r in values if not r['generation'].get('codec_error')]
    selected=[];seen=set()
    for action in ['write','run','done','unsure','diag','trace']:
        for r in [r for r in valid if r['generation']['action']==action][:1]:
            if r['prompt']not in seen:selected.append(r);seen.add(r['prompt'])
    if valid:
        r=max(valid,key=lambda x:x['generation']['input_tokens'])
        if r['prompt']not in seen:selected.append(r)
    assert selected,'Expected new oracle-feedback prompts'
    model,receipt=verify_export(MODEL);tokenizer=AutoTokenizer.from_pretrained(MODEL/'hf',local_files_only=True)
    compact_head(model,output_ids(tokenizer));base.ARMS=['spec'];engine=base.Engine(PARENT,'spec')
    assert sha(MODEL/'model.mka')==sha(PARENT/'export/spec/model.mka')
    assert sha(MODEL/'model.mka')==read(PARENT/'native-verification.json')['models']['spec']['mka_sha256']
    details=[]
    for row in selected:
        p=row['prompt'];gpu=row['generation'];cpu=generate(model,tokenizer,[p])[0];native=engine.generate(p)
        assert native['input_token_ids']==prompt_ids(tokenizer,p)
        assert native['generated_token_ids']==cpu['generated_token_ids']==gpu['generated_token_ids']
        details.append({'action':gpu['action'],'input_tokens':gpu['input_tokens'],
            'prompt_sha256':__import__('hashlib').sha256(p.encode()).hexdigest(),'B200_CPU_CPP_tokens_identical':True})
    check_frozen();write(root/'native-verification.json',{'complete':True,'fresh_feedback_probes':len(details),
        'details':details,'exact_Q4_load':receipt,'MKA_identical_to_previously_verified_profile':True,
        'mka_bytes':(MODEL/'model.mka').stat().st_size,'model_sha256':sha(MODEL/'model.mkqb'),
        'native_probe_source_sha256':sha(__file__),'physical_PicoCalc_measured':False})
    print(json.dumps({'native_feedback_probes':len(details),'all_equal':True}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=__import__('pathlib').Path,default=ROOT/'server-results');a=p.parse_args()
    torch.set_num_threads(4);main(a.root)
