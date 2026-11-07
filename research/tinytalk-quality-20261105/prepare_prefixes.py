#!/usr/bin/env python3
"""Screen earlier teacher replies; keep coherent prefixes and label their learned acts."""
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import urllib.request

from common import core
from grade import grade
from prepare import fingerprint
from prepare_tagged import WORDS
from annotate_intents import SYSTEM as OLD_LABEL_SYSTEM


def main():
    out=Path('prefix-data');out.mkdir(exist_ok=True)
    source=core.read_rows('branched-source/train.jsonl')
    excluded={fingerprint(r['messages']) for name in ['dev','test','opened-audit2']
        for r in core.read_rows(Path('suite')/(name+'.jsonl'))}
    excluded.update(fingerprint(r['messages']) for r in core.read_rows('reserved-audit3/test.jsonl'))
    excluded.update(fingerprint(r['messages']) for r in core.read_rows('babi-probe/test.jsonl'))
    groups=defaultdict(list)
    for row in source:groups[row['prefix_id']].append(row)
    candidates=[];excluded_prefixes=set()
    for prefix,branches in sorted(groups.items()):
        history=branches[0]['messages'][:-1]
        assert len(history)==4 and all(b['messages'][:-1]==history for b in branches)
        rows=[{'id':f'prefix:{prefix}:{turn}','messages':[dict(m) for m in history[:turn]],
            'plain_target':history[turn]['content'],'prefix_id':prefix,'kind':'branched_prefix',
            'source':'fully_screened_earlier_turn_of_contrasted_dialogue'} for turn in [1,3]]
        if any(fingerprint(r['messages']) in excluded for r in rows):
            excluded_prefixes.add(prefix);continue
        candidates.extend(rows)
    print(json.dumps({'phase':'grade_every_prefix_reply','rows':len(candidates),'excluded_prefixes':len(excluded_prefixes)}),flush=True)
    qa=grade(candidates,[r['plain_target'] for r in candidates],out/'grade-cache',workers=12)
    core.save(out/'teacher-audit.json',qa)
    rejected=excluded_prefixes|{r['prefix_id'] for r,g in zip(candidates,qa['details']) if not g['pass']}
    rows=[r for r in candidates if r['prefix_id'] not in rejected]
    branches=[r for r in source if r['prefix_id'] not in rejected]
    assert len(branches)>len(source)*.5 and rows
    system=OLD_LABEL_SYSTEM.split('Also mark ok=true')[0]+(
        'Additional label play_move means actually making the next legal move in an existing game. '
        'Use play for agreeing to start a game or explaining it. '
        'Return one JSON object mapping each input id directly to a label string. Do not judge quality in this labeling pass.')
    cache=out/'label-cache';cache.mkdir(exist_ok=True)
    def label(batch):
        items=[{'id':str(i),'context':r['messages'],'answer':r['plain_target']} for i,r in enumerate(batch)]
        key=hashlib.sha256(json.dumps([system,items],sort_keys=True).encode()).hexdigest();path=cache/(key+'.json')
        if path.exists():response=json.loads(path.read_text())['response']
        else:
            schema={'type':'object','properties':{str(i):{'type':'string','enum':list(WORDS)} for i in range(len(items))},
                'required':[str(i) for i in range(len(items))],'additionalProperties':False}
            payload={'model':'Qwen/Qwen3.8-Flash-Next-FP8','temperature':0,'max_tokens':1200,
                'chat_template_kwargs':{'enable_thinking':False},'response_format':{'type':'json_schema','json_schema':{'name':'prefix_acts','strict':True,'schema':schema}},
                'messages':[{'role':'system','content':system},{'role':'user','content':json.dumps(items)}]}
            req=urllib.request.Request('http://127.0.0.1:8000/v1/chat/completions',json.dumps(payload).encode(),{'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=180) as stream:response=json.load(stream)
            path.write_text(json.dumps({'request':payload,'response':response},ensure_ascii=False))
        parsed=json.loads(response['choices'][0]['message']['content'])
        return {r['id']:parsed[str(i)] for i,r in enumerate(batch)}
    print(json.dumps({'phase':'label_accepted_prefixes','rows':len(rows),'branches':len(branches)}),flush=True)
    with ThreadPoolExecutor(max_workers=12) as pool:
        labels={k:v for group in pool.map(label,[rows[i:i+32] for i in range(0,len(rows),32)]) for k,v in group.items()}
    unique={}
    for row in rows:
        act=labels[row['id']];assert act in WORDS
        row.update(intent_label=act,target=f'<|tt_intent:{act}|> '+row['plain_target'])
        unique.setdefault(fingerprint(row['messages']),row)
    rows=list(unique.values())
    for name,values in [('train',rows),('clean-branches',branches)]:
        (out/(name+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in values))
    core.save(out/'manifest.json',{'rows':len(rows),'sha256':core.digest(out/'train.jsonl'),
        'clean_branch_rows':len(branches),'clean_branches_sha256':core.digest(out/'clean-branches.jsonl'),
        'source_branch_sha256':core.digest('branched-source/train.jsonl'),'all_prefix_targets_graded':True,
        'all_retained_prefixes_passed_both_earlier_reply_checks':True,'source_prefixes':len(groups),
        'retained_prefixes':len({r['prefix_id'] for r in branches}),'excluded_prefixes':len(excluded_prefixes),
        'rejected_or_excluded_prefixes':len(rejected),'reference_pass_rate':qa['pass_rate'],
        'acts':dict(Counter(r['intent_label'] for r in rows)),'reserved_audit3_opened_for_scoring':False})
    print(json.dumps(json.loads((out/'manifest.json').read_text())),flush=True)


if __name__=='__main__':main()
