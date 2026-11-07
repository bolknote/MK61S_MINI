#!/usr/bin/env python3
"""Prepare a matched ordinary-text decoder without the private conversational-act prefix."""
import argparse
import json
from pathlib import Path
import shutil
from common import core,load_model,quantize
from rebalance import compact_tokenizer

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--model',required=True)
parser.add_argument('--data',required=True)
parser.add_argument('--output-model',required=True)
parser.add_argument('--output-data',required=True)
parser.add_argument('--device',default='cuda')
parser.add_argument('--seed',type=int,default=7731)
args=parser.parse_args()
import torch
from tokenizers import Tokenizer
from transformers import PreTrainedTokenizerFast,AutoTokenizer
model,tokenizer,device=load_model(args);model.eval()
backend=json.loads(tokenizer.backend_tokenizer.to_str());limit=tokenizer.eos_token_id+1
backend['added_tokens']=[item for item in backend['added_tokens']if item['id']<limit]
backend['model']['vocab']={token:index for token,index in backend['model']['vocab'].items()if index<limit}
plain=PreTrainedTokenizerFast(tokenizer_object=Tokenizer.from_str(json.dumps(backend)),
    bos_token=tokenizer.eos_token,eos_token=tokenizer.eos_token,unk_token=tokenizer.eos_token,pad_token=tokenizer.eos_token,
    model_input_names=['input_ids','attention_mask'],model_max_length=256)
plain.model_input_names=['input_ids','attention_mask']
assert len(plain)==limit==16385
assert set(plain('Hello',return_tensors='pt'))=={'input_ids','attention_mask'}
for text in ['User: Hi!\nBot:','My cat is named Rose.','Bot: Hello!<|endoftext|>\nUser: What is my name?\nBot:']:
    assert tokenizer.encode(text,add_special_tokens=False)==plain.encode(text,add_special_tokens=False)
sample=plain('User: What is your name?\nBot:',return_tensors='pt',add_special_tokens=False).to(device)
with torch.no_grad():before=model(**sample,use_cache=False).logits[:,:,:limit].clone()
model.resize_token_embeddings(limit,mean_resizing=False)
model.config.tinytalk_intent_token_ids={}
model.config.tinytalk_output_format='Ordinary visible text; no predicted private act tokens'
model.config.tinytalk_structured_intent_decoding=False
with torch.no_grad():after=model(**sample,use_cache=False).logits
error=float((before-after).abs().max());assert error<.001
output=Path(args.output_model);assert not output.exists();output.mkdir(parents=True)
model.save_pretrained(output,safe_serialization=True);plain.save_pretrained(output);quantize.copy_notices(args.model,output)
reloaded=AutoTokenizer.from_pretrained(output,local_files_only=True,trust_remote_code=False)
assert len(reloaded)==limit and set(reloaded('Hello',return_tensors='pt'))=={'input_ids','attention_mask'}
for name in ['LANGUAGE_DATA.md','BACKBONE_README.md']:
    f=Path(args.model)/name
    if f.exists():shutil.copyfile(f,output/name)
table=compact_tokenizer(plain,output/'tokenizer.ttbpe')
rows=core.read_rows(Path(args.data)/'train.jsonl')
for row in rows:
    assert all('<|tt_intent:'not in m['content']for m in row['messages'])
    row['target']=row['plain_target']
data=Path(args.output_data);assert not data.exists();data.mkdir(parents=True)
path=data/'train.jsonl';path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n'for r in rows))
manifest=json.loads((Path(args.data)/'manifest.json').read_text())
manifest.update(source_tagged_data_sha256=core.digest(Path(args.data)/'train.jsonl'),sha256=core.digest(path),
    act_prefix_removed=True,training_contexts_exactly_unchanged=True,rows=len(rows))
core.save(data/'manifest.json',manifest)
core.save(output/'plain-format.json',{'parent_sha256':core.digest(Path(args.model)/'model.safetensors'),
    'parameters':sum(p.numel()for p in model.parameters()),'retained_logit_max_abs_error':error,'tokenizer_bytes':table['file_bytes'],
    'ordinary_token_ids_unchanged':True,'no_token_type_ids':True,'private_act_tokens':0})
print({'parameters':sum(p.numel()for p in model.parameters()),'retained_logit_error':error,'rows':len(rows),'sha256':manifest['sha256']},flush=True)
