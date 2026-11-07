#!/usr/bin/env python3
"""Distill contrasting final requests from the same conversational prefix."""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import random
import re
import time
import urllib.request

from common import core
from grade import grade
from prepare import fingerprint
from prepare_tagged import WORDS


SKILLS = [
    'A concrete hobby recommendation: actual plant, easy song title, book title, craft object, or clear practical first step.',
    'A helpful next suggestion after several ideas are rejected; satisfy all restrictions and give an actual activity.',
    'Differentiate bot capability from friendly speech: cannot physically act, but can offer wishes, welcome future chat, and say greetings.',
    'Keep the bot and person separate: their names, tastes, possessions, and requests for the bot to ask a question.',
    'Keep participants distinct: a friend or relative has an experience, and the person reports its outcome.',
    'React to a development or conclusion rather than restart the task; a positive versus negative outcome changes the response.',
    'A creative suggestion versus a question about a previously stated fact; invent only when asked for a new idea.',
    'Play the next legal move in a naming, rhyming or guessing game, or acknowledge that the game was solved.',
    'Use the latest correction or changed preference, including a new choice expressed without saying the word correction.',
    'Identify the requested type of answer: a title, a genre, a color, a location, a count, a duration, or an explanation.',
]
TOPICS = [
    'pet names and habits','a small garden','a simple drawing','a quiet afternoon','a favorite story',
    'a walk near home','making a paper craft','learning a simple song','a collection of toys','a lost object',
    'a nice thing a friend did','a relative enjoying a gift','a beginner hobby','a rainy afternoon indoors',
    'a short trip','baking a simple treat','choosing clothes','a favorite color','a naming game','a rhyme game',
    'a solved riddle','a tiny make-believe story','a room decoration','a tower of blocks','a puzzle',
    'a friendly greeting','a friendly goodbye','plans for another chat','a change of mind','a helpful kind wish',
    'a picnic','a drink or snack','a bird outside','a family photograph','a short wait','a favorite animal',
    'a board game','a small present','sorting a collection','a bright umbrella','an easy book to read',
    'learning to play an instrument','an easy plant to grow','making a card','a drawing displayed at home',
    'an outdoor activity rejected for an indoor activity','a relaxing break','a choice between two hobbies',
    'a welcome after a trip','a new object with a color and size','a simple craft with a few materials',
    'a chat about the bot and the person','favorite kinds of stories','a game without repeated words',
]
SYSTEM = (
    'Write varied natural English training conversations for TinyTalk, a friendly tiny text chatbot. '
    'For each job create one shared prefix of exactly four alternating messages: user1, answer1, user2, answer2. '
    'Then create FOUR ALTERNATIVE final user messages with their own spoken answers. '
    'All four alternatives follow exactly the SAME prefix, independently. They are not successive turns. '
    'Their requests must differ enough that copying another branch answer would be incorrect. '
    'Keep the supplied everyday theme and skill in mind, but invent wording, facts and details. '
    'Each user message has 3-14 common English words, each answer 1-12 words. '
    'The prefix may include facts, preferences, suggestions, constraints and an experience. '
    'Branch 0: a direct factual question about information explicitly in the prefix. Answer the right fact and speaker. '
    'Branch 1: ask about an unstated fact of the PERSON or their possession, not general world knowledge or the bot preferences. '
    'It must be information that cannot be inferred or known without that person telling it. Say it was not provided. '
    'Branch 2: a concrete request, next move, or practical question fitting the supplied skill. Actually fulfill it. '
    'Branch 3: a new positive or negative development, changed preference, social request, or conclusion. Respond to this new last message. '
    'Give a specific item when a name/title/genre/plant/song is requested. Generic filler does not satisfy it. '
    'Respect all rejections and changes. Keep the user, bot and other people distinct. '
    'The bot name is TinyTalk. It has no body or real family but can converse, have conversational tastes and offer kind wishes. '
    'Do not refuse harmless social speech because the bot lacks a body. '
    'Avoid specialist advice, current events, medicine, law, finance, or complex technical topics. '
    'Answers are LITERAL spoken text, never labels or role names. '
    'Do not put quotation marks inside any field; write song and book titles as plain words. '
    'Each branch includes an act describing its answer, chosen from: '+', '.join(WORDS)+'.'
)


def main():
    from transformers import AutoTokenizer
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',default='branched-data')
    p.add_argument('--model',default='source-model')
    p.add_argument('--contexts',type=int,default=10000)
    p.add_argument('--probe',action='store_true')
    p.add_argument('--workers',type=int,default=12)
    args=p.parse_args()
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    raw=out/'raw';raw.mkdir(exist_ok=True)
    tokenizer=AutoTokenizer.from_pretrained(args.model,local_files_only=True,trust_remote_code=False)
    excluded={fingerprint(r['messages']) for file in ['dev.jsonl','test.jsonl','opened-audit2.jsonl']
        for r in core.read_rows(Path('suite')/file)}
    excluded.update(fingerprint(r['messages']) for r in core.read_rows('reserved-audit3/test.jsonl'))
    rng=random.Random(841936)
    jobs=[]
    for index in range(32 if args.probe else args.contexts):
        jobs.append({'index':index,'theme':rng.choice(TOPICS),
            'skill':SKILLS[index%len(SKILLS)],'variation':rng.randrange(1000000)})
    branch={'type':'object','properties':{'user':{'type':'string'},'answer':{'type':'string'},
        'act':{'type':'string','enum':list(WORDS)}},'required':['user','answer','act'],'additionalProperties':False}
    value={'type':'object','properties':{name:{'type':'string'} for name in ['user1','answer1','user2','answer2']}}
    value['properties']['branches']={'type':'object','properties':{str(i):branch for i in range(4)},
        'required':[str(i) for i in range(4)],'additionalProperties':False}
    value.update(required=list(value['properties']),additionalProperties=False)

    def worker(job):
        key=hashlib.sha256(json.dumps([SYSTEM,job],sort_keys=True).encode()).hexdigest()
        path=raw/(key+'.json')
        if path.exists():
            response=json.loads(path.read_text())['response']
        else:
            payload={'model':'Qwen/Qwen3.8-Flash-Next-FP8','temperature':.65,'seed':job['index']+19627,
                'max_tokens':1300,'chat_template_kwargs':{'enable_thinking':False},
                'response_format':{'type':'json_schema','json_schema':{'name':'branched_chat','strict':True,'schema':value}},
                'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':json.dumps(job)}]}
            req=urllib.request.Request('http://127.0.0.1:8000/v1/chat/completions',json.dumps(payload).encode(),{'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=180) as stream:
                response=json.load(stream)
            path.write_text(json.dumps({'request':payload,'response':response},ensure_ascii=False))
        if response['choices'][0]['finish_reason']=='length':
            return []
        item=json.loads(response['choices'][0]['message']['content'])
        def clean(s):
            return re.sub(r'\s+',' ',s).strip().replace('\u2019',"'")
        history=[{'role':'user' if i%2==0 else 'assistant','content':clean(item[name])}
            for i,name in enumerate(['user1','answer1','user2','answer2'])]
        rows=[]
        for at in range(4):
            branch=item['branches'][str(at)]
            user,answer=clean(branch['user']),clean(branch['answer'])
            messages=[dict(m) for m in history]+[{'role':'user','content':user}]
            if any('<|' in s for s in [user,answer,*[m['content'] for m in history]]):
                continue
            if not 1<=len(answer.split())<=16 or not 1<=len(user.split())<=18:
                continue
            if fingerprint(messages) in excluded or len(tokenizer.encode(core.render(messages),add_special_tokens=False))+40>128:
                continue
            if answer.lower() in ['user','assistant','bot',*WORDS]:
                continue
            act=branch['act']
            rows.append({'id':f'branched:{job["index"]}:{at}','messages':messages,'plain_target':answer,
                'target':f'<|tt_intent:{act}|> '+answer,'intent_label':act,'kind':'branched_dialogue',
                'source':'teacher_counterfactual_final_requests','source_topic':job['theme'],'skill':job['skill'],
                'prefix_id':job['index'],'branch':at,'raw_response':path.name})
        return rows

    started=time.monotonic();rows=[]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures=[pool.submit(worker,job) for job in jobs]
        for count,future in enumerate(as_completed(futures),1):
            rows.extend(future.result())
            if count%100==0 or count==len(jobs):
                print(json.dumps({'contexts_done':count,'contexts':len(jobs),'rows':len(rows),'seconds':round(time.monotonic()-started,1)}),flush=True)
    unique={}
    for row in sorted(rows,key=lambda r:r['id']):
        unique.setdefault(fingerprint(row['messages']),row)
    rows=list(unique.values())
    # Every target is screened by the original detailed rubric, without a gold-answer hint.
    qa=grade(rows,[r['plain_target'] for r in rows],out/'grade-cache',workers=args.workers)
    core.save(out/'teacher-audit.json',qa)
    failed={g['id'] for g in qa['details'] if not g['pass']}
    good=defaultdict(list)
    for row in rows:
        if row['id'] not in failed:
            good[row['prefix_id']].append(row)
    rows=[row for group in good.values() if len(group)>=3 for row in group]
    if args.probe:
        core.save(out/'probe.json',{'rows':len(rows),'pass_rate':qa['pass_rate'],'examples':rows,'raw_target_count':len(unique)})
    else:
        assert len(rows)>=args.contexts*2,'Insufficient vetted contrasted requests'
        path=out/'train.jsonl';path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
        core.save(out/'manifest.json',{'rows':len(rows),'sha256':core.digest(path),'contexts':len({r['prefix_id'] for r in rows}),
            'minimum_branches_per_retained_prefix':3,'all_targets_graded':True,'reference_pass_rate':qa['pass_rate'],
            'failed_targets':len(failed),'skills':dict(Counter(r['skill'] for r in rows)),
            'generation_topics':'Manually curated ordinary conversation topics; no held-out question seeds',
            'closed_audit_opened_for_scoring':False})
    print(json.dumps({'retained_rows':len(rows),'reference_pass_rate':qa['pass_rate'],'probe':args.probe}),flush=True)


if __name__=='__main__':
    main()
