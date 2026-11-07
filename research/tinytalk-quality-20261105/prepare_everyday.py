#!/usr/bin/env python3
"""Adapt an independently published everyday dialogue corpus to short TinyTalk replies."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import urllib.request
from prepare import fingerprint
from grade import grade
from prepare_tagged import WORDS
from common import core


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',default='everyday.parquet')
    parser.add_argument('--tokenizer',default='/previous')
    parser.add_argument('--output',default='everyday-data')
    parser.add_argument('--probe',action='store_true',help='Verify four batches before generating the full corpus')
    args=parser.parse_args()
    sys.path.insert(0,str(Path('pydeps').resolve()))
    import pyarrow.parquet as pq
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(args.tokenizer,local_files_only=True)
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    raw=output/'raw';raw.mkdir(exist_ok=True)
    excluded={fingerprint(json.loads(line)['messages'])for name in ['dev','test','opened-audit2']for line in(Path('suite')/(name+'.jsonl')).read_text().splitlines()}
    rows={};skipped=Counter()
    for index,row in enumerate(pq.read_table(args.source).to_pylist()):
        topic=' '.join(str(row.get(k,''))for k in ['topic','subtopic','subsubtopic']).lower()
        if re.search(r'budget|financ|invest|medic|disease|diagnos|prescri|insurance|politic|religion',topic):skipped['outside_casual_scope']+=1;continue
        messages=row['messages']
        for at,message in enumerate(messages):
            if message['role']!='assistant' or at==0:continue
            history=[{'role':m['role'],'content':re.sub(r'\s+',' ',m['content']).strip().replace('\u2019',"'")}for m in messages[:at]]
            if any(m['role']!=('user'if i%2==0 else'assistant')for i,m in enumerate(history)):continue
            while len(history)>1 and len(tokenizer.encode(core.render(history),add_special_tokens=False))+40>128:del history[:2]
            if len(tokenizer.encode(core.render(history),add_special_tokens=False))+40>128:skipped['long_question']+=1;continue
            identity=fingerprint(history)
            if identity in excluded:continue
            rows[identity]={'id':identity,'messages':history,'draft':message['content'],'topic':topic}
    rows=sorted(rows.values(),key=lambda r:r['id'])
    groups=[rows[start:start+8]for start in range(0,len(rows),8)]
    if args.probe:groups=groups[:4]
    system=('Rewrite final answers for TinyTalk, a small friendly English text chatbot. Read the entire supplied context. '
      'The supplied draft is guidance, not ground truth. Produce a coherent useful answer to the LAST user in only 2-15 simple words. '
      'Preserve actual facts, names, objects, roles and corrections. Answer factual questions directly when the fact was given; '
      'ask a specific clarification only when information is missing. Do not invent facts found only in the draft. '
      'Give a concrete idea when asked for one, a real requested question, or an actual valid game move. '
      'For a statement, use a relevant brief acknowledgment or follow-up. No irrelevant stock phrase. '
      'TinyTalk has no human body, family or physical personal experiences. It can discuss preferences conversationally. '
      'Set ok=false for complex specialist, medical, financial or otherwise unsuitable non-casual requests. '
      'Return kind, answer, ok for each input id. kind is a conversational act; answer is the LITERAL SPOKEN REPLY TEXT to display to the user, '
      'not a topic, label, role, or intended speaker. Never put user or assistant in answer. '
      'For example, a greeting can yield {"kind":"greet","answer":"Hello! How are you?","ok":true}. '
      'Choose one conversational act from: '+', '.join(WORDS)+'. '
      'remember_user/remember_other mean recalling provided facts; ask_question means the user wants THE BOT to ask a question. '
      'identify means the bot identity; do not confuse my/your names. alternative means a rejected suggestion; followup concerns an established topic.')
    def worker(group):
        items=[{'id':str(i),'context':r['messages'],'draft':r['draft']}for i,r in enumerate(group)]
        key=hashlib.sha256(json.dumps([system,items],sort_keys=True).encode()).hexdigest();path=raw/(key+'.json')
        if path.exists():response=json.loads(path.read_text())['response']
        else:
            value={'type':'object','properties':{'kind':{'type':'string','enum':list(WORDS)},'answer':{'type':'string'},'ok':{'type':'boolean'}},
                'required':['kind','answer','ok'],'additionalProperties':False}
            schema={'type':'object','properties':{str(i):value for i in range(len(group))},'required':[str(i)for i in range(len(group))],'additionalProperties':False}
            payload={'model':'Qwen/Qwen3.8-Flash-Next-FP8','temperature':0,'max_tokens':1700,'chat_template_kwargs':{'enable_thinking':False},
                'response_format':{'type':'json_schema','json_schema':{'name':'short_dialogue','strict':True,'schema':schema}},
                'messages':[{'role':'system','content':system},{'role':'user','content':json.dumps(items)}]}
            request=urllib.request.Request('http://127.0.0.1:8000/v1/chat/completions',json.dumps(payload).encode(),{'Content-Type':'application/json'})
            with urllib.request.urlopen(request,timeout=180)as stream:response=json.load(stream)
            path.write_text(json.dumps({'request':payload,'response':response}))
        parsed=json.loads(response['choices'][0]['message']['content']);accepted=[]
        for i,row in enumerate(group):
            result=parsed[str(i)];target=re.sub(r'\s+',' ',result['answer']).strip().replace('\u2019',"'")
            if not result['ok']or not 1<=len(target.split())<=18 or'<|'in target or target.lower()in ['user','assistant','bot',*WORDS]:continue
            kind=result['kind']
            accepted.append({'id':'everyday:'+row['id'],'messages':row['messages'],'kind':kind,'intent_label':kind,'plain_target':target,
              'target':f'<|tt_intent:{kind}|> '+target,'source':'HuggingFaceTB/everyday-conversations-llama3.1-2k; short target adapted by local Qwen',
              'source_topic':row['topic'],'raw_response':path.name})
        return accepted
    accepted=[];start=time.monotonic()
    with ThreadPoolExecutor(max_workers=12)as pool:
        jobs=[pool.submit(worker,g)for g in groups]
        for done,job in enumerate(as_completed(jobs),1):
            accepted+=job.result()
            if done%64==0 or done==len(jobs):print(json.dumps({'done':done,'batches':len(groups),'rows':len(accepted),'seconds':round(time.monotonic()-start,1)}),flush=True)
    accepted.sort(key=lambda r:r['id']);sample=sorted(accepted,key=lambda r:hashlib.sha256(('qa:'+r['id']).encode()).hexdigest())[:200]
    qa=grade(sample,[r['plain_target']for r in sample],output/'grade-cache')
    (output/'teacher-audit.json').write_text(json.dumps(qa,indent=2))
    if args.probe:
        core.save(output/'probe.json',{'rows':len(accepted),'pass_rate':qa['pass_rate'],'grades':qa,'examples':accepted})
        print(json.dumps({'probe_rows':len(accepted),'pass_rate':qa['pass_rate']}),flush=True)
        return
    sample_pass_rate=qa['pass_rate'];full_audit=False
    if sample_pass_rate<.95:
        print(json.dumps({'phase':'full_reference_audit','rows':len(accepted),'sample_pass_rate':sample_pass_rate}),flush=True)
        qa=grade(accepted,[r['plain_target']for r in accepted],output/'full-grade-cache',workers=12)
        (output/'full-teacher-audit.json').write_text(json.dumps(qa,indent=2));full_audit=True
    bad={r['id']for r in qa['details']if not r['pass']};accepted=[r for r in accepted if r['id']not in bad]
    assert len(accepted)>=1000
    path=output/'train.jsonl';path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n'for r in accepted))
    report={'rows':len(accepted),'kinds':dict(Counter(r['kind']for r in accepted)),'teacher_audit':qa['pass_rate'],
       'sample_pass_rate':sample_pass_rate,'all_retained_reference_answers_checked':full_audit,'skipped':dict(skipped),
       'source':json.loads(Path('everyday-source.json').read_text()),'sha256':core.digest(path),'all_260_open_contexts_excluded':True,
       'new_final_audit_used':False,'seconds':time.monotonic()-start}
    core.save(output/'manifest.json',report);print(json.dumps(report),flush=True)


if __name__=='__main__':main()
