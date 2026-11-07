#!/usr/bin/env python3
"""Read-only capacity control. Its weights exceed PSRAM; it is NOT a PicoCalc-resident candidate."""
from collections import defaultdict
import inspect
import json
from pathlib import Path
import re
from common import core,quantize
from grade import grade
from rebalance import compact_tokenizer


def main():
    import torch
    from transformers import AutoTokenizer,AutoModelForCausalLM
    torch.set_num_threads(4);torch.manual_seed(84119)
    root=Path('diagnostic');root.mkdir(exist_ok=True)
    source=Path('model');metadata=json.loads((source/'source.json').read_text())
    tokenizer=AutoTokenizer.from_pretrained(source,local_files_only=True,trust_remote_code=False)
    tokenizer.pad_token=tokenizer.eos_token;tokenizer.padding_side='left'
    model=AutoModelForCausalLM.from_pretrained(source,local_files_only=True,trust_remote_code=False,dtype=torch.float32,attn_implementation='eager').to('cuda').eval().requires_grad_(False)
    packed=quantize.export(model,root/'model.ttq4',{'model':metadata['id'],'revision':metadata['sha'],'source_sha256':core.digest(source/'model.safetensors'),
        'purpose':'Capacity diagnostic; weights do not fit resident in 8 MiB'})
    assert packed['file_bytes']>8388608
    quantize.roundtrip(model)
    expected={name:p.detach().clone()for name,p in model.named_parameters()};quantize.restore(model,root/'model.ttq4')
    error=max(float((expected[name]-p).abs().max())for name,p in model.named_parameters());assert error==0
    del expected
    table=compact_tokenizer(tokenizer,root/'tokenizer.ttbpe',allow_missing_bytes=True)
    layers=defaultdict(int)
    for tensor in packed['tensors']:
        match=re.match(r'model\.layers\.(\d+)\.',tensor['name'])
        if match:layers[int(match.group(1))]+=tensor['bytes']
    assert len(layers)==model.config.num_hidden_layers
    largest=max(layers.values());reserve=262144
    profiles=[]
    for context in [64,96,128,160,192,256]:
        kv=2*model.config.num_hidden_layers*model.config.num_key_value_heads*(model.config.hidden_size//model.config.num_attention_heads)*context*2
        total=kv+largest+table['file_bytes']+reserve
        profiles.append({'context':context,'fp16_kv_bytes':kv,'one_layer_bytes':largest,'tokenizer_bytes':table['file_bytes'],
            'reserve_bytes':reserve,'total_design_bytes':total,'fits_8mib_streaming_design':total<8388608})
    context=max(p['context']for p in profiles if p['fits_8mib_streaming_design'])
    context=min(context,192);maximum=48
    system='You are TinyTalk, an AI text chatbot. Answer in under 15 words.'
    def prompt(messages):return tokenizer.apply_chat_template([{'role':'system','content':system}]+messages,tokenize=False,add_generation_prompt=True)
    def decode(cases):
        replies=[]
        with torch.inference_mode():
            for start in range(0,len(cases),8):
                group=cases[start:start+8];texts=[];omissions=[]
                for case in group:
                    messages=[dict(m)for m in case['messages']];omitted=0
                    while len(tokenizer.encode(prompt(messages),add_special_tokens=False))+maximum>context:
                        if len(messages)<3:raise ValueError('Current diagnostic question does not fit')
                        del messages[:2];omitted+=1
                    texts.append(prompt(messages));omissions.append(omitted)
                inputs=tokenizer(texts,padding=True,add_special_tokens=False,return_tensors='pt').to('cuda')
                options={'max_new_tokens':maximum,'do_sample':False,'use_cache':True,'pad_token_id':tokenizer.eos_token_id,'eos_token_id':tokenizer.eos_token_id}
                if'logits_to_keep'in inspect.signature(model.forward).parameters:options['logits_to_keep']=1
                generated=model.generate(**inputs,**options)[:,inputs.input_ids.shape[1]:].tolist()
                for case,tokens,omitted in zip(group,generated,omissions):
                    ended=tokenizer.eos_token_id in tokens
                    if ended:tokens=tokens[:tokens.index(tokenizer.eos_token_id)+1]
                    reply=tokenizer.decode(tokens,skip_special_tokens=True).strip();words=reply.lower().split()
                    triples=[tuple(words[i:i+3])for i in range(len(words)-2)]
                    replies.append({'id':case['id'],'reply':reply,'ended_with_eos':ended,'bad':not ended or not reply or len(triples)!=len(set(triples)),
                        'tokens':len(tokens),'omitted_context_pairs':omitted})
        return replies
    cases=core.read_rows('opened-audit2.jsonl');replies=decode(cases)
    direct=grade(cases,replies,root/'grade-cache')
    scripts=json.loads(Path('opened-audit2-scenarios.json').read_text());rollout_cases=[];rollout_replies=[];transcripts=[]
    for index,steps in enumerate(scripts):
        messages=[]
        for turn,(question,intent)in enumerate(steps):
            messages.append({'role':'user','content':question})
            case={'id':f'capacity:{index}:{turn}','messages':[dict(m)for m in messages],'intent':intent}
            reply=decode([case])[0];rollout_cases.append(case);rollout_replies.append(reply)
            messages.append({'role':'assistant','content':reply['reply']})
        transcripts.append(messages)
    multi=grade(rollout_cases,rollout_replies,root/'grade-cache')
    report={'purpose':'Capacity comparison only; not a resident-PSRAM replacement','repository':metadata['id'],'revision':metadata['sha'],
        'parameters':sum(p.numel()for p in model.parameters()),'packed_bytes':packed['file_bytes'],'packed_sha256':packed['file_sha256'],
        'packed_reload_max_abs_error':error,'weights_fit_resident_in_8mib':False,'streaming_profiles':profiles,
        'ideal_weight_bytes_read_per_generated_token_without_resident_weights':packed['payload_bytes'],
        'runtime_context':context,'maximum_new_tokens':maximum,'system_prompt':system,'native_streaming_runtime_implemented':False,
        'test_sha256':core.digest('opened-audit2.jsonl'),'scenarios_sha256':core.digest('opened-audit2-scenarios.json'),
        'direct':direct,'multi_turn':multi,'replies':replies,'rollout_cases':rollout_cases,'rollouts':transcripts,'rollout_replies':rollout_replies,
        'malformed':sum(r['bad']for r in replies+rollout_replies)}
    core.save(root/'capacity.json',report)
    print(json.dumps({'direct':direct['pass_rate'],'multi_turn':multi['pass_rate'],'packed_bytes':packed['file_bytes'],
                     'runtime_context':context,'resident_weights_fit':False,'streaming_profiles':profiles}),flush=True)


if __name__=='__main__':main()
