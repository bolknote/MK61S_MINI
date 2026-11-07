"""Training-fit and register-renaming probes from an exact completed dev packet."""
import argparse
import collections
import hashlib
import json
import random
import struct

import torch
from transformers import AutoConfig,AutoModelForCausalLM,AutoTokenizer

from compose_common import ROOT,read,rename_task
from native_eval import language_cases,summary
from lowbit import load


def main():
    p=argparse.ArgumentParser();p.add_argument('--arm',choices=['champion','small'],required=True);p.add_argument('--phase',type=int,required=True);a=p.parse_args()
    folder=ROOT/f'{a.arm}-phase{a.phase}';source=folder/'development.mkqb';data=source.read_bytes();digest=hashlib.sha256(data).hexdigest()
    matching=[]
    for f in folder.glob('development-*.json'):
        record=json.loads(f.read_text())
        if record['packet']['sha256']==digest:matching.append(record)
    if not matching:raise RuntimeError('Snapshot packet is still being evaluated; retry after dev completes')
    record=matching[-1];out=ROOT/'diagnostics';out.mkdir(exist_ok=True);packet=out/f'{a.arm}-phase{a.phase}-step{record["step"]}.mkqb';packet.write_bytes(data)
    n=struct.unpack('<I',data[8:12])[0];header=json.loads(data[12:12+n]);c=dict(header['config']);kind=c.pop('model_type')
    torch.set_num_threads(2);torch.cuda.set_per_process_memory_fraction(.025)
    model=AutoModelForCausalLM.from_config(AutoConfig.for_model(kind,**c),trust_remote_code=False);load(model,packet);model.to('cuda').eval()
    tokenizer=AutoTokenizer.from_pretrained(ROOT/'initial'/a.arm,local_files_only=True,trust_remote_code=False)
    pool=read(ROOT/'course/train.jsonl');extra=ROOT/f'phase{a.phase}-extra-train.jsonl'
    if extra.exists():pool+=read(extra)
    groups=collections.defaultdict(list)
    for t in pool:
        source='procedural'if t.get('source')=='procedural'or'procedural'in t.get('origin','')else'language'
        groups[(t['level'],source)].append(t)
    rng=random.Random(6113501);results={}
    for (level,source),tasks in sorted(groups.items()):
        selected=rng.sample(tasks,min(24,len(tasks)))
        results[f'level{level}-{source}-seen']=language_cases(model,tokenizer,selected)
        changed=[{**rename_task(t,('R3','R0','R1','R2')),'id':t['id']+':renamed'}for t in selected]
        results[f'level{level}-{source}-renamed']=language_cases(model,tokenizer,changed)
    report={'arm':a.arm,'phase':a.phase,'step':record['step'],'source_packet_sha256':digest,
      'training_fit':summary(results),'development':record['summary'],'all_probes_from_training_only':True,
      'no_gradient_updates':True,'fresh_conditions_opened':False}
    (out/f'{a.arm}-phase{a.phase}-step{record["step"]}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
