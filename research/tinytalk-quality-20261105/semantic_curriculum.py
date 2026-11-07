#!/usr/bin/env python3
"""Teach compositional factual/creative questions, attributes and speaker roles."""
import argparse
from collections import Counter
import json
from pathlib import Path
import random
import re
from prepare import fingerprint
from common import core


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed-data',default='seed-data')
    parser.add_argument('--broad-data',default='broad-data')
    parser.add_argument('--everyday',default='everyday-data')
    parser.add_argument('--tokenizer',default='/previous')
    parser.add_argument('--output',default='data')
    args=parser.parse_args()
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(args.tokenizer,local_files_only=True)
    rng=random.Random(661728)
    def read(path):return [json.loads(x)for x in Path(path).read_text().splitlines()]
    excluded={fingerprint(r['messages'])for name in ['dev','test','opened-audit2']for r in read(Path('suite')/(name+'.jsonl'))}
    rows=read(Path(args.seed_data)/'train.jsonl')
    rows += [r for r in read(Path(args.broad_data)/'train.jsonl')if r['kind']!='replay']
    public_rows=read(Path(args.everyday)/'train.jsonl')
    public_kept=[];public_filtered=Counter()
    for row in public_rows:
        question=row['messages'][-1]['content'].lower()
        if re.search(r'\b(latest|current|right now|trending|forecast|sunrise|sunset)\b|popular.{0,35}\b(now|today)\b',question):
            public_filtered['time_sensitive_fact']+=1;continue
        if re.search(r'computer|software|internet|technology|programming|video call|career|employment',row.get('source_topic','')):
            public_filtered['technical_or_professional_topic']+=1;continue
        public_kept.append(row)
    rows += public_kept
    sources={str(p):core.digest(p)for p in [Path(args.seed_data)/'train.jsonl',Path(args.broad_data)/'train.jsonl',Path(args.everyday)/'train.jsonl']}
    added=Counter()
    def add(kind,turns,target):
        messages=[{'role':'user'if i%2==0 else'assistant','content':text}for i,text in enumerate(turns)]
        identity=fingerprint(messages)
        if identity in excluded:return
        rows.append({'id':'semantic:'+identity,'messages':messages,'kind':kind,'intent_label':kind,
            'plain_target':target,'target':f'<|tt_intent:{kind}|> '+target,'source':'compositional_semantic_curriculum'})
        added[kind]+=1
    bank=sorted({tokenizer.decode([i]).strip()for i in range(tokenizer.eos_token_id)
                 if re.fullmatch('[a-z]{3,8}',tokenizer.decode([i]).strip())})
    real='Alice Ben Carol David Emma Finn Grace Henry Iris Jack Kate Leo Mia Noah Olivia Peter Rose Sam Tina Will Victor Zoe Amber Basil Clover Felix Hugo Holly Hazel Jasper Luna Molly Nora Oscar Pearl Robin Ruby Theo Toby Walter Willow'.split()
    def name():
        mode=rng.random()
        if mode<.5:return rng.choice(real)
        if mode<.8:return rng.choice(bank).capitalize()
        return ''.join(rng.choice('bcdfghjklmnprstvwz')+rng.choice('aeiou')for _ in range(rng.choice([2,3]))).capitalize()
    colors='red blue green yellow orange purple pink white black brown gray'.split()
    animals=['cat','dog','rabbit','bird','hamster','turtle','fish']
    things=['ball','bag','cup','kite','hat','book','box','boat','flag','balloon']
    places=['table','chair','desk','garden','shelf','window','basket','bed','door']
    ack=['Thanks for telling me.','All right.','I see.','That is interesting.']
    for _ in range(5000):
        n=name();turns=[rng.choice([f'My name is {n}.',f'Hello, I am {n}.',f'Please call me {n}.']),rng.choice(ack)]
        if rng.random()<.55:
            turns += [rng.choice(['What is my name?','What should you call me?','Can you tell me my name?','Who am I in our chat?'])]
            add('remember_user',turns,f'Your name is {n}.')
        else:
            turns += [rng.choice(['What is your name?','What should I call you?','Who are you?','Tell me the name of this bot.'])]
            add('identify',turns,'I am TinyTalk, a small friendly chat bot.')
    for _ in range(15000):
        pet=rng.choice(animals);n=name();color=rng.choice(colors)
        facts=rng.choice([f'My {pet} is {color} and is named {n}.',f'I have a {color} {pet} called {n}.',
                          f'{n} is the name of my {pet}. Its color is {color}.'])
        if rng.random()<.4:turns=[f'My own name is {name()}.',rng.choice(ack),facts,rng.choice(ack)]
        else:turns=[facts,rng.choice(ack)]
        if rng.random()<.5:
            turns += [rng.choice([f'What color is my {pet}?',f'Can you recall the color of my {pet}?',f'Which color did I say my {pet} was?'])]
            target=f'Your {pet} is {color}.'
        else:
            turns += [rng.choice([f'What is my {pet} named?',f'What is the name of my {pet}?',f'Can you tell me what my {pet} is called?',f'What did I call my {pet}?'])]
            target=f'Your {pet} is named {n}.'
        add('remember_other',turns,target)
    for _ in range(10000):
        obj=rng.choice(things);color=rng.choice(colors);place=rng.choice(places)
        turns=[rng.choice([f'My {obj} is {color}. It is on the {place}.',f'I put my {color} {obj} on the {place}.']),rng.choice(ack)]
        if rng.random()<.5:
            turns += [rng.choice([f'What color is my {obj}?',f'Can you recall its color?',f'Which color was the {obj}?'])]
            target=f'Your {obj} is {color}.'
        else:
            turns += [rng.choice([f'Where is my {obj}?',f'Where did I put my {obj}?',f'Can you remind me where the {obj} is?'])]
            target=f'Your {obj} is on the {place}.'
        add('remember_other',turns,target)
    values={'food':['apples','bananas','soup','bread','cake','rice','cookies','cheese','carrots','noodles'],
            'color':colors,'hobby':['reading','drawing','gardening','baking','knitting','writing','music']}
    for _ in range(10000):
        field=rng.choice(list(values));old,new=rng.sample(values[field],2)
        turns=[f'My favorite {field} is {old}.',rng.choice(ack)]
        change=rng.choice([f'Actually, I prefer {new} now.',f'No, change my choice to {new}.',f'I meant {new}, not {old}.'])
        if rng.random()<.5:
            turns += [change+' '+rng.choice(['What is my choice now?',f'What is my favorite {field} now?','Which one do I prefer now?'])]
            kind='correction'
        else:
            turns += [change,rng.choice(ack),rng.choice([f'What is my favorite {field}?','What did I choose in the end?',f'Which {field} do I like best?'])]
            kind='remember_user'
        add(kind,turns,f'Your favorite {field} is {new}.')
    for _ in range(6000):
        pet=rng.choice(animals);actual,other=rng.sample(colors,2);match=rng.random()<.5
        asked=actual if match else other
        question=rng.choice([f'Is my {pet} {asked}?',f'Did I say my {pet} was {asked}?',f'Was {asked} the color I mentioned?'])
        add('remember_other',[f'My {pet} is {actual}.',rng.choice(ack),question],
            ('Yes'if match else'No')+f', your {pet} is {actual}.')
    for _ in range(6000):
        pet=rng.choice(animals);color=rng.choice(colors);n=name();mode=rng.randrange(3)
        if mode==0:
            turns=[f'I have a {color} {pet}.',rng.choice(ack),rng.choice([f'What is my {pet} named?',f'Can you recall my {pet}\'s name?'])]
            target=f'You have not told me your {pet}\'s name.'
        elif mode==1:
            turns=[f'My {pet} is named {n}.',rng.choice(ack),f'What color is my {pet}?']
            target=f'You have not told me your {pet}\'s color.'
        else:
            turns=[f'My {pet} is {color}.',rng.choice(ack),'What name did I give you for myself?']
            target='You have not told me your name.'
        add('clarify',turns,target)
    for _ in range(6000):
        obj=rng.choice(things);color=rng.choice(colors);creative=rng.random()<.5
        if creative:
            turns=[f'I want to draw a {obj}.',rng.choice(ack),rng.choice([f'What color could I make the {obj}?','Which color might look nice on it?',f'Can you suggest a color for my {obj}?'])]
            add('followup',turns,f'You could make the {obj} {color}.')
        else:
            turns=[f'I drew a {color} {obj}.',rng.choice(ack),rng.choice([f'What color is the {obj}?','Which color did I use?',f'Can you remember the color of my {obj}?'])]
            add('remember_other',turns,f'Your {obj} is {color}.')
    preferences={'cats':'Yes, cats can be lovely companions.','dogs':'Yes, dogs can be lovely companions.',
        'books':'Yes, I enjoy talking about books.','quiet music':'Yes, quiet music can be relaxing.',
        'funny stories':'Yes, funny stories can be cheerful.','paper crafts':'Yes, paper crafts can be creative.',
        'gardens':'Yes, gardens can be peaceful.'}
    for _ in range(3000):
        topic=rng.choice(list(preferences))
        add('preference',[f'I like {topic}.',rng.choice(ack),rng.choice([f'Do you like {topic} too?',f'What do you think about {topic}?',f'Would you enjoy chatting about {topic}?'])],
            preferences[topic])
    unique={}
    for row in rows:
        identity=fingerprint(row['messages'])
        if identity not in excluded:unique[identity]=row
    rows=list(unique.values());rng.shuffle(rows)
    output=Path(args.output);assert not output.exists();output.mkdir(parents=True)
    path=output/'train.jsonl';path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n'for r in rows))
    report={'policy':'Vetted varied conversation targets plus public everyday dialogue and compositional field/role binding, not just fixed response prototypes',
        'rows':len(rows),'kinds':dict(Counter(r['kind']for r in rows)),'semantic_rows_before_deduplication':dict(added),
        'source_sha256':sources,'sha256':core.digest(path),'exact_260_open_evaluation_contexts_excluded':len(excluded),'new_final_audit_used':False}
    report['public_dialogues_used']=len(public_kept);report['public_dialogues_filtered']=dict(public_filtered)
    core.save(output/'manifest.json',report);print(json.dumps(report),flush=True)


if __name__=='__main__':main()
