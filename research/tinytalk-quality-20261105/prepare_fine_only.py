#!/usr/bin/env python3
"""Keep one learned answer-form tag, without the overlapping coarse-act tag."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import shutil
from common import core, load_model, quantize


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',default='before-fine');p.add_argument('--output-model',default='fine-init')
    p.add_argument('--output-data',default='data');p.add_argument('--model-only',action='store_true')
    p.add_argument('--device',default='cpu');p.add_argument('--seed',type=int,default=517903)
    args=p.parse_args();out=Path(args.output_model)
    if not out.exists():
        assert json.loads((Path(args.model)/'config.json').read_text()).get('tinytalk_answer_focus_separator_id')is not None
        shutil.copytree(args.model,out)
        cfg=json.loads((out/'config.json').read_text());cfg['tinytalk_emit_intent_token']=False
        (out/'config.json').write_text(json.dumps(cfg,indent=2)+'\n')
        model,tok,_=load_model(args,out);model.eval().requires_grad_(False)
        packed=quantize.export(model,out/'model.ttq4',{'recipe':'One fine answer-form tag; answer keywords and spoken targets unchanged',
            'source_sha256':core.digest(Path(args.model)/'model.safetensors')})
        assert core.digest(out/'model.safetensors')==core.digest(Path(args.model)/'model.safetensors')
        from rebalance import compact_tokenizer
        table=compact_tokenizer(tok,out/'tokenizer.ttbpe')
        total=packed['file_bytes']+table['file_bytes']+1048576+262144;assert total<8388608
        core.save(out/'fine-model.json',{'raw_weights_unchanged':True,
            'source_sha256':core.digest(Path(args.model)/'model.safetensors'),
            'parameters':sum(v.numel()for v in model.parameters()),'total_design_bytes':total,
            'remaining_from_8mib':8388608-total,'native_runtime_measured':False})
    if args.model_only:return
    data=Path(args.output_data);assert not data.exists();data.mkdir()
    source=Path('base-data/train.jsonl');rows=core.read_rows(source)
    for row in rows:
        if row['kind']=='replay':continue
        target,n=re.subn(r'^<\|tt_intent:\w+\|>','',row['target']);assert n==1 and target.startswith('<|tt_type:')
        row['target']=target
    path=data/'train.jsonl';path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n'for r in rows))
    core.save(data/'manifest.json',{'rows':len(rows),'sha256':core.digest(path),'source_sha256':core.digest(source),
        'kinds':dict(Counter(r['kind']for r in rows)),
        'contexts_spoken_targets_and_answer_keywords_unchanged':True,
        'change':'Remove only the emitted coarse-act tag; keep the finer learned answer-form tag',
        'reserved_audit3_opened':False})
    print(json.dumps({'rows':len(rows),'model':str(out)}),flush=True)


if __name__=='__main__':main()
