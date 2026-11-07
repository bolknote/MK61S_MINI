"""Widen only FFNs; duplicate features with zero outgoing weights preserves function."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM,AutoTokenizer

from quantization import export_q4,load_q4
from tasks import BUILD


@torch.no_grad()
def widen(model):
    config=copy.deepcopy(model.config);old=config.intermediate_size;config.intermediate_size=old*2
    grown=AutoModelForCausalLM.from_config(config,trust_remote_code=False).cpu().eval()
    original=dict(model.named_parameters())
    for name,value in grown.named_parameters():
        source=original[name].detach().cpu()
        if value.shape==source.shape:value.copy_(source)
        elif '.mlp.gate_proj.weight'in name or'.mlp.up_proj.weight'in name:
            assert value.shape[0]==2*source.shape[0]and value.shape[1]==source.shape[1]
            value[:old].copy_(source);value[old:].copy_(source)
        elif '.mlp.down_proj.weight'in name:
            assert value.shape[1]==2*source.shape[1]and value.shape[0]==source.shape[0]
            value[:,:old].copy_(source);value[:,old:].zero_()
        else:raise ValueError('Unexpected resized tensor: '+name)
    grown.tie_weights()
    return grown


def main():
    p=argparse.ArgumentParser();p.add_argument('--initial',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    torch.set_num_threads(2);torch.manual_seed(6110700)
    if(args.output/'growth.json').exists():raise SystemExit('Growth artifact already exists')
    args.output.mkdir(parents=True,exist_ok=True)
    model=AutoModelForCausalLM.from_pretrained(args.initial,local_files_only=True,trust_remote_code=False).cpu().eval()
    tokenizer=AutoTokenizer.from_pretrained(args.initial,local_files_only=True,trust_remote_code=False)
    grown=widen(model)
    texts=['Сложи числа из R0 и R1.','Найди модуль значения R2.','Из R3 вычти R0.','Раздели R1 на R2.',
           'Какую сумму дадут очки R0 и R3?','Площадь квадрата со стороной R1.']
    def compare():
        max_error=0.;argmax_equal=True
        with torch.inference_mode():
            for text in texts:
                ids=torch.tensor([tokenizer.encode(text,add_special_tokens=False)])
                a=model(ids).logits;b=grown(ids).logits
                max_error=max(max_error,float((a-b).abs().max()))
                argmax_equal=argmax_equal and bool(torch.equal(a.argmax(-1),b.argmax(-1)))
        return {'max_logit_error':max_error,'all_token_argmax_equal':argmax_equal}
    fp32=compare();assert fp32['max_logit_error']<1e-4 and fp32['all_token_argmax_equal'],fp32
    grown.save_pretrained(args.output/'hf',safe_serialization=True);tokenizer.save_pretrained(args.output/'hf')
    base_pack=export_q4(model,args.output/'base.mkq4');grown_pack=export_q4(grown,args.output/'model.mkq4')
    load_q4(model,args.output/'base.mkq4');load_q4(grown,args.output/'model.mkq4')
    q4=compare();assert q4['max_logit_error']<1e-4 and q4['all_token_argmax_equal'],q4
    report={'initial':str(args.initial),'initial_weights_sha256':hashlib.sha256((args.initial/'model.safetensors').read_bytes()).hexdigest(),
        'base_parameters':sum(x.numel()for x in model.parameters()),'grown_parameters':sum(x.numel()for x in grown.parameters()),
        'old_ffn':model.config.intermediate_size,'new_ffn':grown.config.intermediate_size,
        'unchanged':['layers','attention dimensions','KV heads','head dimension','vocabulary','tokenizer','context'],
        'method':'Append duplicate gate/up features and zero outgoing down columns; nonzero original vs zero new outgoing weights breaks training symmetry',
        'fp32_preservation':fp32,'q4_preservation':q4,'base_pack':base_pack,'grown_pack':grown_pack,
        'fp16_kv_bytes_per_token':2560,'fp16_kv_512_bytes':1310720,'context':512}
    (args.output/'growth.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
