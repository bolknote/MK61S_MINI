#!/usr/bin/env python3
"""Prune a fully pretrained 256-wide TinyStories backbone into the existing device budget."""
import argparse
import copy
import json
from pathlib import Path
import shutil
from common import core
from prepare_tagged import WORDS
from rebalance import compact_tokenizer


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True)
    parser.add_argument('--tokenizer',required=True)
    parser.add_argument('--data',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--device',default='cuda')
    args=parser.parse_args()
    import torch
    from transformers import AutoModelForCausalLM,AutoTokenizer,GPTNeoForCausalLM
    torch.set_num_threads(4);torch.manual_seed(617281)
    source=Path(args.source);output=Path(args.output);assert not output.exists()
    metadata=json.loads((source/'source.json').read_text())
    old=AutoModelForCausalLM.from_pretrained(source,local_files_only=True,trust_remote_code=False,
             weights_only=True,dtype=torch.float32,attn_implementation='eager').to(args.device).eval()
    tokenizer=AutoTokenizer.from_pretrained(args.tokenizer,local_files_only=True,trust_remote_code=False)
    tokenizer.pad_token=tokenizer.eos_token
    previous=json.loads((Path(args.tokenizer)/'config.json').read_text())
    intents=previous['tinytalk_intent_token_ids'];special=set(intents.values())
    old_vocab=json.loads((source/'vocab.json').read_text());new_vocab=tokenizer.get_vocab()
    normal=sorted(set(range(len(tokenizer)))-special)
    new_to_old={index:old_vocab[token]for token,index in new_vocab.items()if index in normal}
    assert len(new_to_old)==len(normal)and old.config.hidden_size==256 and old.config.num_layers==8
    config=copy.deepcopy(old.config)
    config.vocab_size=len(tokenizer);config.max_position_embeddings=256;config.intermediate_size=1024
    config.eos_token_id=tokenizer.eos_token_id;config.bos_token_id=tokenizer.eos_token_id;config.pad_token_id=tokenizer.eos_token_id
    config.tinytalk_runtime_context=128;config.tinytalk_intent_token_ids=intents
    config.tinytalk_structured_intent_decoding=False
    config.tinytalk_backbone={'repository':metadata['id'],'revision':metadata['sha'],'full_pretrained_core':True}
    config._attn_implementation='eager'
    model=GPTNeoForCausalLM(config).to(args.device).eval()
    original=dict(old.named_parameters())
    with torch.no_grad():
        for name,parameter in model.named_parameters():
            if name=='transformer.wte.weight':
                parameter[normal]=original[name][[new_to_old[i]for i in normal]]
            elif name=='transformer.wpe.weight':parameter.copy_(original[name][:256])
            else:
                assert parameter.shape==original[name].shape,name
                parameter.copy_(original[name])
        for kind,index in intents.items():
            anchors=tokenizer.encode(' '+WORDS[kind],add_special_tokens=False)
            assert not set(anchors)&special
            model.transformer.wte.weight[index].copy_(model.transformer.wte.weight[anchors].mean(0))
    assert model.lm_head.weight is model.transformer.wte.weight
    rows=core.read_rows(Path(args.data)/'train.jsonl')
    examples=[]
    for row in rows:
        ids=tokenizer.encode(core.render(row['messages']),add_special_tokens=False)
        if len(ids)<=80 and not set(ids)&special:examples.append(ids)
        if len(examples)==4:break
    errors=[]
    with torch.inference_mode():
        for ids in examples:
            inputs=torch.tensor([ids],device=args.device)
            translated=torch.tensor([[new_to_old[i]for i in ids]],device=args.device)
            expected=old(input_ids=translated,use_cache=False).logits[:,:,[new_to_old[i]for i in normal]]
            actual=model(input_ids=inputs,use_cache=False).logits[:,:,normal]
            errors.append(float((expected-actual).abs().max()))
    assert max(errors)<.001,errors
    output.mkdir(parents=True)
    model.save_pretrained(output,safe_serialization=True);tokenizer.save_pretrained(output)
    table=compact_tokenizer(tokenizer,output/'tokenizer.ttbpe')
    if(source/'readme.md').exists():shutil.copyfile(source/'readme.md',output/'BACKBONE_README.md')
    (output/'NOTICE.md').write_text('Pretrained language backbone: https://huggingface.co/'+metadata['id']+'\nRevision: '+metadata['sha']+
        '\nVocabulary/position pruning preserves the retained-token FP32 function; private learned act tags are new.\n'+
        'No new license is asserted for the pretrained weights. Source model metadata did not specify a license at retrieval.\n')
    report={'repository':metadata['id'],'revision':metadata['sha'],'source_weight_sha256':core.digest(source/'pytorch_model.bin'),
        'original_parameters':sum(p.numel()for p in old.parameters()),'parameters':sum(p.numel()for p in model.parameters()),
        'retained_logit_max_abs_error':max(errors),'tokenizer_bytes':table['file_bytes'],'runtime_context':128,
        'initial_sha256':core.digest(output/'model.safetensors'),'evaluation_contexts_used':False}
    core.save(output/'backbone-transplant.json',report);print(json.dumps(report),flush=True)


if __name__=='__main__':main()
