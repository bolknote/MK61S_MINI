#!/usr/bin/env python3
"""Fictional conversational state, corrections, query binding and simple games.

Answers follow generated state rather than teacher guessing. Identical prefixes
receive present and absent attribute queries; state can span multiple turns.
No held-out student outputs or answer keys are used to construct examples.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random

from common import core
from prepare import fingerprint


NAMES = 'Ada Alice Anna Ben Bella Carl Dan Ella Emma Eva Felix Finn Grace Henry Iris Jack James Jane Jasper Kate Leo Liam Lily Lisa Lucy Luna Max Mia Milo Molly Nick Nina Nora Oliver Oscar Owen Paul Pearl Rose Ruby Sam Sara Theo Tina Toby Tom Will Willow Zoe'.split()
COLORS = 'red blue green yellow orange purple pink white black brown gray'.split()
NUMBERS = 'two three four five six seven eight nine ten'.split()
ACKS = ['Okay.', 'Got it.', 'Thanks for telling me.', 'I see.', 'All right.', 'Thank you.', 'Tell me more.']
UNKNOWN = ['You have not told me.', 'I do not know yet.', 'You did not mention that.', 'I do not have that information yet.']
LOCATIONS = ['on the table', 'under the chair', 'on the shelf', 'by the window', 'on the desk', 'beside the bed', 'in the basket', 'near the door']
RHYMES = ['cat bat hat mat rat sat', 'dog frog log fog', 'red bed head said', 'blue true shoe new', 'light night bright kite white', 'sun fun run bun', 'cake lake make bake', 'tree bee see three', 'boat coat goat float', 'star car far jar', 'book look cook hook', 'ring sing king wing', 'mouse house louse', 'rain train chain', 'bear chair pear', 'fox box socks', 'day play say gray', 'snow grow show toe', 'fish dish wish', 'pen ten hen then']


def main():
    from transformers import AutoTokenizer
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', required=True)
    p.add_argument('--suite', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--pairs', type=int, default=60000)
    p.add_argument('--seed', type=int, default=731825)
    args = p.parse_args()
    assert all(len(group.split()) >= 3 for group in RHYMES)
    out = Path(args.output)
    assert not out.exists()
    out.mkdir(parents=True)
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True, trust_remote_code=False)
    excluded = {fingerprint(r['messages']) for file in ['dev.jsonl','test.jsonl','opened-audit2.jsonl']
        for r in core.read_rows(Path(args.suite)/file)}
    rng = random.Random(args.seed)
    rows, seen, stats = [], set(), Counter()

    def pick(values):
        return rng.choice(values)

    def name():
        if rng.random() < .15:
            return ''.join(pick('bcdfghjklmnprstvwz') + pick('aeiou') for _ in range(pick([2,3]))).capitalize()
        return pick(NAMES)

    # Entries: possible values, affirmative facts, questions. Placeholders are
    # expanded before storage; no task metadata reaches model input.
    def subject(domain):
        noun = None
        if domain == 'pet':
            noun = pick('cat dog rabbit bird hamster turtle fish horse parrot'.split())
            r, s = 'my '+noun, 'my '+noun+"'s"
            fields = {
                'name': (NAMES, ['{r} is named {v}.','I call {r} {v}.','The name of {r} is {v}.','{r} is {v}.'],
                    ['What is {s} name?','What is {r} called?','Please repeat {s} name.','Can you recall the name of {r}?']),
                'color': (COLORS, ['{r} is {v}.','The color of {r} is {v}.','I have a {v} '+noun+'.'],
                    ['What color is {r}?','What is {s} color?','Which color did I give for {r}?']),
                'age': (['one year','two years','three years','four years','five years','six years'],
                    ['{r} is {v} old.','The age of {r} is {v}.'],
                    ['How old is {r}?','What is {s} age?','Can you remind me how old {r} is?'])}
        elif domain == 'object':
            noun = pick('ball cup doll hat bag kite book bottle scarf shoe brush coat toy pencil box shirt'.split())
            r, s = 'my '+noun, 'my '+noun+"'s"
            fields = {
                'color': (COLORS,['{r} is {v}.','I have a {v} '+noun+'.','The color of {r} is {v}.',
                    'I bought a {v} '+noun+'.','I lost {r}. It was {v}.'],
                    ['What color is {r}?','What is {s} color?','What color was the '+noun+' I mentioned?',
                     'Do you remember the color of {r}?','Which color did I say {r} was?']),
                'location': (LOCATIONS,['{r} is {v}.','I left {r} {v}.','I put {r} {v}.'],
                    ['Where is {r}?','Where did I leave {r}?','What is the location of {r}?','Can you remind me where {r} is?']),
                'size': (['small','big','tiny','large'],['{r} is {v}.','The size of {r} is {v}.'],
                    ['How big is {r}?','What is {s} size?','Did I say {r} was big or small?'])}
        elif domain == 'collection':
            noun = pick('books balls cats dogs birds dolls toys pens hats cups stones flowers shells'.split())
            r, s = 'my '+noun, 'my '+noun+"'"
            fields = {
                'number': (NUMBERS,['I have {v} '+noun+'.','I own {v} '+noun+'.','There are {v} '+noun+' in my collection.'],
                    ['How many '+noun+' do I have?','What is the number of {r}?','How many '+noun+' did I say I own?',
                     'Can you recall how many '+noun+' I have?']),
                'color': (COLORS,['{r} are {v}.','The color of {r} is {v}.'],
                    ['What color are {r}?','What is the color of {r}?','Which color did I mention for {r}?']),
                'location': (LOCATIONS,['{r} are {v}.','I left {r} {v}.'],
                    ['Where are {r}?','Where did I leave {r}?','Can you recall the location of {r}?'])}
        elif domain in ['user','person']:
            r = 'me' if domain == 'user' else 'my '+pick(['sister','brother','friend','cousin','neighbor'])
            s = 'my' if domain == 'user' else r+"'s"
            if domain == 'user':
                fields = {
                    'name': (NAMES,['My name is {v}.','People call me {v}.','I am {v}.'],
                        ['What is my name?','What should you call me?','Which name did I give for myself?']),
                    'city': ('London Rome Paris Boston York Oslo Berlin Tokyo Madrid Dublin'.split(),
                        ['I live in {v}.','My home city is {v}.'],['What city do I live in?','Where do I live?','Please recall my city.']),
                    'age': (['seven','eight','nine','ten','eleven','twelve','twenty','thirty'],
                        ['I am {v} years old.','My age is {v}.'],['How old am I?','What is my age?']),
                    'preference': (COLORS,['My favorite color is {v}.','The color I like best is {v}.'],
                        ['What is my favorite color?','Which color do I like best?','What color did I say I prefer?'])}
            else:
                fields = {
                    'name': (NAMES,['{r} is named {v}.','{r} is called {v}.','The name of {r} is {v}.'],
                        ['What is {s} name?','What is {r} called?','What is the name of {r}?']),
                    'city': ('London Rome Paris Boston York Oslo Berlin Tokyo Madrid Dublin'.split(),
                        ['{r} lives in {v}.','The home city of {r} is {v}.'],['Where does {r} live?','What is {s} city?']),
                    'age': (['seven','eight','nine','ten','eleven','twelve','twenty','thirty'],
                        ['{r} is {v} years old.','The age of {r} is {v}.'],['How old is {r}?','What is {s} age?'])}
        elif domain == 'food':
            noun = pick(['ice cream','cake','cookie','candy','milkshake','pudding'])
            r, s = 'my '+noun, 'my '+noun+"'s"
            fields = {
                'flavor': (['vanilla','chocolate','strawberry','lemon','banana','mint'],
                    ['{r} has a {v} flavor.','The flavor of {r} is {v}.','{r} tastes of {v}.'],
                    ['What flavor is {r}?','Which flavor did I mention?','Do you remember {s} flavor?']),
                'color': (COLORS,['{r} is {v}.','The color of {r} is {v}.'],
                    ['What color is {r}?','Which color did I mention for {r}?']),
                'location': (LOCATIONS,['{r} is {v}.','I left {r} {v}.'],
                    ['Where is {r}?','Where did I leave {r}?'])}
        elif domain == 'wait':
            r, s = 'my wait', "my wait's"
            fields = {
                'duration': (['a minute','two minutes','five minutes','ten minutes','half an hour','an hour','two hours'],
                    ['I waited for {v}.','My wait lasted {v}.','I had to wait {v}.'],
                    ['How long did I wait?','How much time did I spend waiting?','What was the length of my wait?']),
                'place': (['the park','the station','the library','the shop','the school','the bus stop'],
                    ['I waited at {v}.','The place where I waited was {v}.'],
                    ['Where did I wait?','At which place did I wait?']),
                'day': ('Monday Tuesday Wednesday Thursday Friday Saturday Sunday'.split(),
                    ['I waited on {v}.','My wait happened on {v}.'],['Which day did I wait?','On what day did I wait?'])}
        elif domain == 'weather':
            r, s = 'the weather', "the weather's"
            fields = {
                'condition': (['sunny','rainy','cloudy','snowy','windy','foggy','cold','warm','hot','cool'],
                    ['It is {v} outside.','The weather outside is {v}.'],
                    ['What is the weather outside?','How is the weather here?','What did I say the weather was like?']),
                'day': ('Monday Tuesday Wednesday Thursday Friday Saturday Sunday'.split(),
                    ['Today is {v}.','The day today is {v}.'],['What day is it?','Which day did I say it is?']),
                'season': (['winter','spring','summer','autumn'],['It is {v} here.','The season here is {v}.'],
                    ['What season is it here?','Which season did I mention?'])}
        else:
            raise ValueError(domain)
        return r, s, fields

    def text(template, r, s, v):
        value = template.format(r=r,s=s,v=v)
        for vowel in ['a','e','i','o','u']:
            value = value.replace(' a '+vowel, ' an '+vowel)
        return value[0].upper()+value[1:]

    def accept(batch):
        keys = [fingerprint(row['messages']) for row in batch]
        if len(set(keys)) != len(keys) or any(k in seen or k in excluded for k in keys):
            stats['duplicate_pair_dropped'] += 1
            return
        if any(len(tokenizer.encode(core.render(row['messages']),add_special_tokens=False))+40 > 128 for row in batch):
            stats['long_pair_dropped'] += 1
            return
        rows.extend(batch)
        seen.update(keys)

    for index in range(args.pairs):
        domain = pick(['pet','object','collection','user','person','food','wait','weather'])
        r,s,fields = subject(domain)
        known,absent = rng.sample(list(fields),2)
        present = [known]
        other = [f for f in fields if f not in [known,absent]]
        if other and rng.random() < .6:
            present.append(pick(other))
        values = {f:(name() if f=='name' else pick(fields[f][0])) for f in present}
        facts = [text(pick(fields[f][1]),r,s,values[f]) for f in present]
        rng.shuffle(facts)
        corrected = rng.random() < .35
        if corrected:
            old_values = [v for v in fields[known][0] if v != values[known]]
            old = pick(old_values)
            correction = text(pick(fields[known][1]),r,s,values[known])
            facts = [text(pick(fields[known][1]),r,s,old)] + [text(pick(fields[f][1]),r,s,values[f]) for f in present if f != known]
        split = len(facts)>1 and rng.random()<.6
        history=[]
        if split:
            for fact in facts:
                history += [{'role':'user','content':fact},{'role':'assistant','content':pick(ACKS)}]
        else:
            history += [{'role':'user','content':' '.join(facts)},{'role':'assistant','content':pick(ACKS)}]
        if corrected:
            history += [{'role':'user','content':pick(['Actually, ','Sorry, I meant this: ','Let me correct that. '])+correction},
                {'role':'assistant','content':pick(['Thanks for correcting me.','Got it.','Okay, I understand.'])}]
        elif len(history)==2 and rng.random()<.5:
            history += [{'role':'user','content':pick(['I thought I would tell you.','I wanted to mention that.','That is what happened.'])},
                {'role':'assistant','content':pick(ACKS)}]
        pair=[]
        for available,field in [(True,known),(False,absent)]:
            question = text(pick(fields[field][2]),r,s,'')
            question = pick(['','','','Quick question: ','Please tell me, '])+question
            answer = values[field]+'.' if available else pick(UNKNOWN)
            answer = answer[0].upper()+answer[1:]
            act = ('remember_user' if domain=='user' else 'remember_other') if available else 'clarify'
            pair.append({'id':f'stateful:{index}:{int(available)}','messages':history+[{'role':'user','content':question}],
                'target':f'<|tt_intent:{act}|> '+answer,'plain_target':answer,'kind':'contrastive_facts',
                'intent_label':act,'source':'generated_fictional_state_v1','domain':domain,'field':field,
                'known':available,'corrected':corrected,'pair_id':index})
        accept(pair)
        stats[domain]+=1

    # Explicit turn-taking exercises train a move that respects prior moves.
    for index in range(args.pairs//6):
        rhyming = rng.random()<.5
        words = pick(RHYMES).split() if rhyming else pick([
            'cat dog rabbit bird horse sheep cow duck pig goat',
            'red blue green yellow orange purple pink white black brown',
            'apple banana pear peach plum cherry lemon grape mango melon',
            'rose lily daisy tulip violet sunflower orchid poppy']).split()
        rng.shuffle(words)
        if rhyming:
            opening = pick([f'Let us rhyme with {words[0]}.',f'Can we take turns saying words that rhyme with {words[0]}?',
                f'Rhyming game: I start with {words[0]}.'])
        else:
            category = ('animals' if 'cat' in words else 'colors' if 'red' in words else 'fruit' if 'apple' in words else 'flowers')
            opening = pick([f'Let us name {category}. I say {words[0]}.',f'Take turns naming {category}, without repeats. I start: {words[0]}.'])
        count=pick([1,2]) if len(words)>3 else 1
        history=[{'role':'user','content':opening},{'role':'assistant','content':words[1].capitalize()+'.'}]
        if count==2:
            history += [{'role':'user','content':words[2].capitalize()+'. Your turn.'}]
            answer = words[3].capitalize()+'.'
        else:
            history += [{'role':'user','content':pick(['Now say another one.','One more word, please.','Your turn again.'])}]
            answer=words[2].capitalize()+'.'
        accept([{'id':f'state-game:{index}','messages':history,'target':'<|tt_intent:play_move|> '+answer,
            'plain_target':answer,'kind':'contrastive_facts','intent_label':'play_move',
            'source':'generated_fictional_state_v1','domain':'rhyme' if rhyming else 'category','known':True}])
    rng.shuffle(rows)
    path=out/'train.jsonl'
    path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
    sample=sorted(rows,key=lambda r:hashlib.sha256(('state-qa:'+r['id']).encode()).hexdigest())[:512]
    (out/'qa-sample.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in sample))
    core.save(out/'manifest.json',{'rows':len(rows),'sha256':core.digest(path),'counts':dict(stats),
        'domains':dict(Counter(r['domain'] for r in rows)),
        'corrected_rows':sum(r.get('corrected',False) for r in rows),'seed':args.seed,
        'policy':'Canonical targets from fictional state; paired present/absent questions; corrections and turn-taking',
        'source':'Deterministic generated examples; no student test answers used'})
    print(json.dumps(json.loads((out/'manifest.json').read_text())),flush=True)


if __name__=='__main__':
    main()
