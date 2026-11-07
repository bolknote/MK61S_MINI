#!/usr/bin/env python3
"""Annotate already vetted training targets with private answer-form supervision."""
from concurrent.futures import ThreadPoolExecutor,as_completed
from collections import Counter
import hashlib
import json
from pathlib import Path
import time
import urllib.request
from common import core
from reply_types import ANCHORS,SYSTEM


def main():
    out=Path('type-labels');raw=out/'raw';raw.mkdir(parents=True,exist_ok=True)
    rows=[r for r in core.read_rows('base-data/train.jsonl') if r['kind'] in ['natural_dialogue','branched_dialogue','branched_prefix']]
    rows.sort(key=lambda r:r['id']);groups=[rows[i:i+32] for i in range(0,len(rows),32)]
    def label(group):
        items=[{'id':str(i),'context':r['messages'],'answer':r.get('plain_target',r['target'])} for i,r in enumerate(group)]
        key=hashlib.sha256(json.dumps([SYSTEM,items],sort_keys=True).encode()).hexdigest();path=raw/(key+'.json')
        schema={'type':'object','properties':{str(i):{'type':'string','enum':list(ANCHORS)} for i in range(len(items))},
            'required':[str(i) for i in range(len(items))],'additionalProperties':False}
        for attempt in range(3):
            cache=path if not attempt else path.with_name(path.stem+f'-retry{attempt}.json')
            if cache.exists():response=json.loads(cache.read_text())['response']
            else:
                payload={'model':'Qwen/Qwen3.8-Flash-Next-FP8','temperature':0,'max_tokens':1200,
                    'chat_template_kwargs':{'enable_thinking':False},'response_format':{'type':'json_schema','json_schema':{'name':'answer_types','strict':True,'schema':schema}},
                    'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':json.dumps(items)}]}
                req=urllib.request.Request('http://127.0.0.1:8000/v1/chat/completions',json.dumps(payload).encode(),{'Content-Type':'application/json'})
                with urllib.request.urlopen(req,timeout=180) as stream:response=json.load(stream)
                cache.write_text(json.dumps({'request':payload,'response':response},ensure_ascii=False))
            try:
                parsed=json.loads(response['choices'][0]['message']['content'])
                assert response['choices'][0]['finish_reason']!='length'
                assert set(parsed)=={str(i) for i in range(len(items))} and all(v in ANCHORS for v in parsed.values())
                return [{'id':r['id'],'answer_type':parsed[str(i)]} for i,r in enumerate(group)]
            except (ValueError,AssertionError):
                if attempt==2:raise
    labels=[];started=time.monotonic()
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures=[pool.submit(label,g) for g in groups]
        for count,f in enumerate(as_completed(futures),1):
            labels.extend(f.result())
            if count%100==0 or count==len(groups):print(json.dumps({'batches':count,'total':len(groups),'rows':len(labels),'seconds':round(time.monotonic()-started,1)}),flush=True)
    labels.sort(key=lambda r:r['id']);assert len(labels)==len(rows)
    path=out/'labels.jsonl';path.write_text(''.join(json.dumps(r)+'\n' for r in labels))
    core.save(out/'manifest.json',{'rows':len(labels),'source_sha256':core.digest('base-data/train.jsonl'),
        'labels_sha256':core.digest(path),'types':dict(Counter(r['answer_type'] for r in labels)),
        'scope':'Answer-form labels only; accepted target text and original quality grades unchanged',
        'reserved_audit3_opened_for_scoring':False})


if __name__=='__main__':main()
