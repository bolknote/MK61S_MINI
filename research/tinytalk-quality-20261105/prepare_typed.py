#!/usr/bin/env python3
"""Add private answer-form tokens without changing ordinary embeddings or contexts."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import shutil
from common import core,load_model,quantize
from rebalance import compact_tokenizer
from reply_types import ANCHORS,ACT_TYPES,FIELD_TYPES


def main():
    import torch
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',default='before-types')
    p.add_argument('--output-model',default='typed-init')
    p.add_argument('--output-data',default='data')
    p.add_argument('--model-only',action='store_true')
    p.add_argument('--device',default='cpu')
    p.add_argument('--seed',type=int,default=421753)
    args=p.parse_args()
    out=Path(args.output_model)
    if not out.exists():
        model,tok,device=load_model(args);model.eval().requires_grad_(False)
        old_vocab=len(tok);old=model.transformer.wte.weight.detach().clone()
        intents=dict(model.config.tinytalk_intent_token_ids)
        tokens=[f'<|tt_type:{name}|>' for name in ANCHORS]
        complete=[f'<|tt_intent:{name}|>' for name in intents]+tokens
        added=tok.add_special_tokens({'additional_special_tokens':complete});assert added==len(ANCHORS)
        model.resize_token_embeddings(len(tok),mean_resizing=False)
        assert model.lm_head.weight is model.transformer.wte.weight
        types={name:tok.convert_tokens_to_ids(f'<|tt_type:{name}|>') for name in ANCHORS}
        with torch.no_grad():
            for name,index in types.items():
                ids=tok.encode(' '+ANCHORS[name],add_special_tokens=False);assert all(i<old_vocab for i in ids)
                model.transformer.wte.weight[index].copy_(quantize.dequantized(old[ids]).mean(0))
        assert torch.equal(old,model.transformer.wte.weight[:old_vocab])
        model.config.tinytalk_answer_type_token_ids=types
        model.config.tinytalk_answer_type_base_vocab_size=old_vocab
        model.config.tinytalk_structured_intent_decoding=True
        model.config.tinytalk_no_repeat_ngram_size=3
        out.mkdir();model.save_pretrained(out,safe_serialization=True);tok.save_pretrained(out)
        quantize.copy_notices(args.model,out)
        for name in ['LANGUAGE_DATA.md']:
            path=Path(args.model)/name
            if path.exists():shutil.copyfile(path,out/name)
        table=compact_tokenizer(tok,out/'tokenizer.ttbpe')
        backbone=getattr(model.config,'tinytalk_backbone',{})
        packed=quantize.export(model,out/'model.ttq4',{'model':backbone.get('repository'),
            'revision':backbone.get('revision'),'source_sha256':core.digest(Path(args.model)/'model.safetensors'),
            'recipe':'Private answer-form token initializer; ordinary word embeddings unchanged'})
        total=packed['file_bytes']+table['file_bytes']+1048576+262144;assert total<8388608
        core.save(out/'type-model.json',{'source_sha256':core.digest(Path(args.model)/'model.safetensors'),
            'ordinary_embeddings_exact':True,'old_vocab':old_vocab,'new_vocab':len(tok),'added_types':len(types),
            'parameters':sum(v.numel() for v in model.parameters()),'total_design_bytes':total,
            'remaining_from_8mib':8388608-total,'reserve_bytes':262144,'native_runtime_measured':False})
    if args.model_only:return
    data=Path(args.output_data);assert not data.exists();data.mkdir()
    manifest=json.loads(Path('type-labels/manifest.json').read_text())
    assert manifest['source_sha256']==core.digest('base-data/train.jsonl')
    labels={r['id']:r['answer_type'] for r in core.read_rows('type-labels/labels.jsonl')}
    assert manifest['labels_sha256']==core.digest('type-labels/labels.jsonl')
    rows=[];counts=Counter();used=set()
    for source in core.read_rows('base-data/train.jsonl'):
        row=dict(source)
        if row['kind']=='replay':rows.append(row);continue
        match=re.fullmatch(r'<\|tt_intent:(\w+)\|>\s*(.*)',row['target'],flags=re.S);assert match,row['id']
        act,body=match.groups()
        if row['id'] in labels:
            answer_type=labels[row['id']];used.add(row['id'])
        elif row['kind']=='contrastive_facts':
            if row.get('known') is False:answer_type='unknown'
            elif row.get('domain')=='rhyme':answer_type='game_rhyme'
            elif row.get('domain')=='category':answer_type='game_name'
            else:answer_type=FIELD_TYPES.get(row.get('field',row.get('requested_field')),'fact')
        elif row['kind']=='grounded_qa':answer_type='fact'
        else:answer_type=ACT_TYPES[act]
        assert answer_type in ANCHORS
        row.update(target=f'<|tt_intent:{act}|><|tt_type:{answer_type}|> '+body,
            plain_target=body,answer_type=answer_type)
        rows.append(row);counts[answer_type]+=1
    assert used==set(labels),'Every annotated example must belong to this unchanged corpus'
    path=data/'train.jsonl';path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
    core.save(data/'manifest.json',{'rows':len(rows),'sha256':core.digest(path),
        'source_sha256':core.digest('base-data/train.jsonl'),'labels':manifest,'answer_types':dict(counts),
        'kinds':dict(Counter(r['kind'] for r in rows)),'contexts_and_spoken_targets_unchanged':True,
        'format':'One learned intent, one learned answer form, then ordinary spoken text',
        'reserved_audit3_opened_for_scoring':False})
    print(json.dumps({'rows':len(rows),'types':dict(counts),'model':str(out)}),flush=True)


if __name__=='__main__':main()
