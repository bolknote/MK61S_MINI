#!/usr/bin/env python3
"""Balance known/unknown questions within the exact same factual dialogue history."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
from common import core
from prepare import fingerprint


NAMES = 'Alice Anna Ben Bella Carl Daisy Dan Ella Emma Eva Felix Finn Grace Henry Iris Jack James Jane Jasper Kate Leo Liam Lily Lisa Lucy Luna Max Mia Milo Molly Nick Nina Nora Oliver Oscar Owen Paul Pearl Rose Ruby Sam Sara Theo Tina Toby Tom Will Willow Zoe'.split()
COLORS = 'red blue green yellow orange purple pink white black brown gray'.split()
PETS = 'cat dog rabbit bird hamster turtle fish'.split()
OBJECTS = 'ball cup doll hat bag kite book bottle scarf shoe brush'.split()
CITIES = 'London Rome Paris Boston York Oslo Berlin Tokyo Madrid Dublin'.split()
LOCATIONS = ['on the table','under the chair','on the shelf','by the window','on the desk','beside the bed','in the basket','near the door']
NUMBERS = 'two three four five six'.split()
ACK = ['Okay.','Got it.','Thanks for telling me.','I see.','That sounds interesting.','All right.','Thank you.','Tell me more.']


def main():
    from transformers import AutoTokenizer
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--suite', required=True)
    p.add_argument('--pairs', type=int, default=20000)
    args = p.parse_args()
    out = Path(args.output)
    assert not out.exists()
    out.mkdir(parents=True)
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True, trust_remote_code=False)
    excluded = {fingerprint(r['messages']) for name in ['dev','test','opened-audit2']
        for r in core.read_rows(Path(args.suite) / (name + '.jsonl'))}
    rng = random.Random(620391)
    def name():
        if rng.random() < .25:
            return ''.join(rng.choice('bcdfghjklmnprstvwz') + rng.choice('aeiou')
                           for _ in range(rng.choice([2,3]))).capitalize()
        return rng.choice(NAMES)
    def entity(domain, avoid=None):
        if domain == 'pet':
            noun = rng.choice([n for n in PETS if n != avoid])
            return {'domain':domain,'noun':noun,'ref':'my ' + noun,'plural':False,
                'values':{'name':name(),'color':rng.choice(COLORS)}}
        if domain == 'object':
            noun = rng.choice([n for n in OBJECTS if n != avoid])
            return {'domain':domain,'noun':noun,'ref':'my ' + noun,'plural':False,
                'values':{'color':rng.choice(COLORS),'location':rng.choice(LOCATIONS)}}
        if domain == 'collection':
            noun = rng.choice([n for n in ['cats','dogs','birds','rabbits','turtles'] if n != avoid])
            return {'domain':domain,'noun':noun,'ref':'my ' + noun,'plural':True,
                'values':{'color':rng.choice(COLORS),'number':rng.choice(NUMBERS)}}
        friend = domain == 'friend'
        return {'domain':domain,'noun':'friend' if friend else 'myself',
            'ref':'my friend' if friend else 'me','plural':False,
            'values':{'name':name(),'city':rng.choice(CITIES)}}
    def fact(e, field, value):
        ref = e['ref']
        if e['domain'] == 'user':
            options = ([f'My name is {value}.',f'People call me {value}.',f'I am called {value}.'] if field == 'name' else
                       [f'I live in {value}.',f'My home is in {value}.',f'The city I live in is {value}.'])
        elif field == 'name':
            options = [f'The name of {ref} is {value}.',f'I call {ref} {value}.',f'{ref.capitalize()} is named {value}.',f'{ref.capitalize()} is called {value}.']
        elif field == 'color':
            verb = 'are' if e['plural'] else 'is'
            options = [f'{ref.capitalize()} {verb} {value}.',f'The color of {ref} is {value}.']
            if not e['plural'] and e['domain'] in ['pet','object']:
                article = 'an' if value[0] in 'aeiou' else 'a'
                options += [f'I have {article} {value} {e["noun"]}.']
                if e['domain'] == 'object':
                    options += [f'I lost my {value} {e["noun"]}.',f'I bought {article} {value} {e["noun"]}.']
        elif field == 'location':
            options = [f'{ref.capitalize()} is {value}.',f'I left {ref} {value}.',f'I put {ref} {value}.']
        elif field == 'number':
            options = [f'I have {value} {e["noun"]}.',f'I own {value} {e["noun"]}.',f'{value.capitalize()} {e["noun"]} live with me.']
        else:
            options = [f'{ref.capitalize()} lives in {value}.',f'The city where {ref} lives is {value}.']
        return rng.choice(options)
    def question(e, field):
        ref = e['ref']
        if e['domain'] == 'user':
            options = (['What is my name?','What should you call me?','Can you recall my name?',
                'Which name did I give for myself?','Please remind me what I am called.'] if field == 'name' else
                ['Where do I live?','What city is my home in?','Can you recall where I live?',
                 'Which city did I mention as my home?','Please remind me of my city.'])
        elif field == 'name':
            options = [f'What is {ref} called?',f'What is the name of {ref}?',f'What did I call {ref}?',
                f'Can you recall the name of {ref}?',f'Please remind me what {ref} is named.',
                f'Which name belongs to {ref}?',f'Do you remember what {ref} is called?']
        elif field == 'color':
            verb = 'are' if e['plural'] else 'is'
            options = [f'What color {verb} {ref}?',f'What is the color of {ref}?',
                f'Can you recall the color of {ref}?',f'Please remind me of the color of {ref}.',
                f'Which color did I mention for {ref}?',f'Do you remember the color of {ref}?']
        elif field == 'location':
            options = [f'Where is {ref}?',f'Where did I put {ref}?',f'Can you recall where {ref} is?',
                f'Please remind me where {ref} is.',f'Do you remember the location of {ref}?']
        elif field == 'number':
            options = [f'How many {e["noun"]} do I have?',f'What is the number of {ref}?',
                f'Can you recall how many {e["noun"]} I have?',f'Please tell me the number of {ref}.']
        else:
            options = [f'Where does {ref} live?',f'What city does {ref} live in?',
                f'Can you recall the city where {ref} lives?',f'Please remind me where {ref} lives.']
        value = rng.choice(options)
        prefix = rng.choice(['','','','Quick question: ','One more thing: ','I forgot: '])
        return prefix + value
    def unknown(e, field):
        if e['domain'] == 'user':
            return 'You have not told me your ' + ('name.' if field == 'name' else 'city.')
        referent = e['ref'].replace('my ', 'your ', 1)
        if field in ['name','color']:
            return 'You have not told me the ' + field + ' of ' + referent + '.'
        if field == 'number':
            return 'You have not told me how many you have.'
        return 'You have not told me where ' + referent + (' lives.' if field == 'city' else ' is.')
    rows = []
    stats = Counter()
    seen = set()
    for index in range(args.pairs):
        domain = rng.choice(['pet','object','collection','user','friend'])
        target = entity(domain)
        known, absent = rng.sample(list(target['values']),2)
        first = fact(target, known, target['values'][known])
        other_domain = ('friend' if domain == 'user' else 'user' if domain == 'friend' else domain)
        other = entity(other_domain, target['noun'])
        distraction_field = rng.choice(list(other['values']))
        texts = [first]
        if rng.random() < .5:
            texts.append(fact(other, distraction_field, other['values'][distraction_field]))
        rng.shuffle(texts)
        ack = rng.choice(ACK)
        if known == 'name' and domain in ['pet','user'] and rng.random() < .5:
            ack = rng.choice([f'Hello, {target["values"][known]}!',f'{target["values"][known]} is a nice name.'])
        if rng.random() < .5:
            history = [{'role':'user','content':' '.join(texts)}, {'role':'assistant','content':ack}]
        elif len(texts) > 1:
            history = [{'role':'user','content':texts[0]}, {'role':'assistant','content':rng.choice(ACK)},
                {'role':'user','content':texts[1]}, {'role':'assistant','content':ack}]
        else:
            history = [{'role':'user','content':texts[0]}, {'role':'assistant','content':ack},
                {'role':'user','content':rng.choice(['I wanted to mention it.','I thought you might like to know.',
                                                  'That is what I wanted to tell you.'])},
                {'role':'assistant','content':rng.choice(ACK)}]
        pair = []
        for present, field in [(True,known),(False,absent)]:
            messages = [dict(m) for m in history] + [{'role':'user','content':question(target,field)}]
            answer = target['values'][field].capitalize() + '.' if present else unknown(target,field)
            act = ('remember_user' if domain == 'user' else 'remember_other') if present else 'clarify'
            pair.append({'id':f'contrastive:{index}:{int(present)}','messages':messages,
                'target':f'<|tt_intent:{act}|> ' + answer,'plain_target':answer,
                'kind':'contrastive_facts','intent_label':act,'source':'paired_attribute_presence_curriculum',
                'pair_id':index,'domain':domain,'requested_field':field,'known':present,
                'present_field':known,'given_fact_count':len(texts)})
        # Reject both members together, preserving exact class balance in each prefix.
        keys = [fingerprint(r['messages']) for r in pair]
        if any(key in excluded or key in seen for key in keys) or any(len(tokenizer.encode(core.render(r['messages']),add_special_tokens=False)) + 40 > 128 for r in pair):
            stats['pair_excluded'] += 1
            continue
        assert pair[0]['messages'][:-1] == pair[1]['messages'][:-1]
        assert pair[0]['requested_field'] != pair[1]['requested_field']
        rows.extend(pair)
        seen.update(keys)
        stats[domain] += 1
    identities = [fingerprint(r['messages']) for r in rows]
    assert len(set(identities)) == len(identities), 'Use a new seed or drop whole duplicate pairs'
    assert sum(r['known'] for r in rows) * 2 == len(rows)
    for count in [1,2]:
        group = [r for r in rows if r['given_fact_count'] == count]
        assert group and sum(r['known'] for r in group) * 2 == len(group)
    rng.shuffle(rows)
    path = out / 'train.jsonl'
    path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
    sample = sorted(rows,key=lambda r:hashlib.sha256(('qa-paired:' + r['id']).encode()).hexdigest())[:240]
    (out/'qa-sample.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in sample))
    core.save(out/'manifest.json',{'rows':len(rows),'pairs':len(rows)//2,'sha256':core.digest(path),
        'known':sum(r['known'] for r in rows),'unknown':sum(not r['known'] for r in rows),
        'same_history_for_known_unknown_queries':True,'query_status_independent_of_history':True,
        'question_status_balance':dict(stats),'exact_observed_contexts_excluded':True,
        'fact_count_status_balance':{str(n):{'known':sum(r['known'] for r in rows if r['given_fact_count']==n),
            'unknown':sum(not r['known'] for r in rows if r['given_fact_count']==n)} for n in [1,2]},
        'nonce_names_fraction':.25,'ambiguous_object_aliases_avoided':True,
        'source':'Deterministic fictional facts with balanced paired questions; no test answers used'})
    print(json.dumps(json.loads((out/'manifest.json').read_text())),flush=True)


if __name__ == '__main__':
    main()
