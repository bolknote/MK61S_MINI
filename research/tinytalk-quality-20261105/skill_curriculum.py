#!/usr/bin/env python3
"""Add diverse variable-value conversation exercises, excluding exact audit contexts."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import re
from prepare import fingerprint

NAME_QUERIES = ["What did I say my name was?", "Which name did I give you?", "Please remind me of my name.",
                "What name should you use for me?", "Can you repeat my name?", "How should you address me?",
                "Tell me the name I shared earlier.", "Which name belongs to me?", "Can you remember my name?",
                "What do people call me?", "What name am I using here?", "Could you say my name again?",
                "Do you know which name I use?", "What should I be called in our chat?",
                "Please tell me how I introduced myself.", "Remind me which name I asked you to use."]
PROJECTS = {
    'painting': ['Paint a small flower.', 'Paint a sky with two colors.', 'Try painting a little bowl of fruit.'],
    'chess': ['Practice moving a pawn.', 'Try learning how one piece moves.', 'Play a short practice game.'],
    'knitting': ['Try knitting a small square.', 'Start with a tiny scarf.', 'Practice one simple row of stitches.'],
    'gardening': ['Plant a bean in a small pot.', 'Try growing a little herb.', 'Put some seeds in a cup of soil.'],
    'baking': ['Make a few simple cookies.', 'Try baking a small cake.', 'Start with a few plain muffins.'],
    'paper crafts': ['Fold a little paper boat.', 'Make a simple bookmark.', 'Cut a small paper star.'],
    'drawing': ['Draw a little flower.', 'Try drawing a funny cat.', 'Draw a simple house.'],
    'reading': ['Start with a short story.', 'Read one short poem.', 'Pick a small chapter to read.'],
    'music': ['Try tapping a simple rhythm.', 'Learn a short tune.', 'Listen to a gentle song.'],
    'writing': ['Write a tiny story about a pet.', 'Write a four-line poem.', 'Start with a short happy scene.'],
    'sewing': ['Try stitching a little cloth square.', 'Sew a small pouch.', 'Practice one straight line.'],
    'origami': ['Fold a simple paper boat.', 'Try a little paper hat.', 'Start with a paper plane.'],
    'photography': ['Take a photo of one leaf.', 'Try a picture of a simple shadow.', 'Photograph a small flower.'],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--suite', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--seed', type=int, default=78129)
    args = parser.parse_args()
    rng = random.Random(args.seed)
    output = Path(args.output);assert not output.exists();output.mkdir(parents=True)
    excluded = {fingerprint(json.loads(line)['messages']) for name in ['dev', 'test']
                for line in (Path(args.suite) / (name + '.jsonl')).read_text().splitlines()}
    rows = [json.loads(line) for line in (Path(args.source) / 'train.jsonl').read_text().splitlines()]
    # Short social replies avoid appending an unnecessary, guessed follow-up question.
    shortened = 0
    for row in rows:
        if row['kind'] == 'play':
            question = row['messages'][-1]['content'].lower()
            if re.search(r'your turn|you start|you go first|now you|one more|another animal|take turns naming|let.s name|rhymes with', question):
                row['kind'] = row['intent_label'] = 'play_move'
                row['target'] = '<|tt_intent:play_move|> ' + row['plain_target']
        if row['kind'] in ['positive', 'negative', 'greet', 'thanks', 'goodbye', 'tired']:
            target = row['plain_target']
            first = re.split(r'(?<=[.!?])\s+', target, maxsplit=1)[0]
            if len(first.split()) >= 2 and not first.endswith('?') and first != target:
                row['plain_target'] = first;row['target'] = f"<|tt_intent:{row['intent_label']}|> " + first;shortened += 1
    added = Counter()
    def value():
        return ''.join(rng.choice('bcdfghjklmnprstvwz') + rng.choice('aeiou') for _ in range(rng.choice([2, 3]))).capitalize()
    def add(kind, turns, target):
        messages = [{'role': 'user' if i % 2 == 0 else 'assistant', 'content': text} for i, text in enumerate(turns)]
        identity = fingerprint(messages)
        if identity in excluded:return
        rows.append({'id': 'curriculum:' + identity + ':' + str(sum(added.values())), 'kind': kind, 'messages': messages,
                     'target': f'<|tt_intent:{kind}|> ' + target, 'plain_target': target, 'intent_label': kind,
                     'source': 'variable_value_skill_curriculum'})
        added[kind] += 1
    for _ in range(10000):
        name, other = value(), value()
        intro = rng.choice([f'My name is {name}.', f"I'm {name}.", f'Please call me {name}.',
                            f'Hello, people know me as {name}.', f'I use the name {name} here.'])
        if rng.random() < .3:intro += f' My friend is named {other}.'
        turns = [intro, rng.choice(['Nice to meet you.', 'Hello! I am TinyTalk.', 'Glad to chat with you.'])]
        if rng.random() < .25:
            turns += [f'Actually, please use {other} for my name.', 'All right.'];name = other
        turns += [rng.choice(NAME_QUERIES)]
        add('remember_user', turns, f'Your name is {name}.')
    for _ in range(5000):
        name, owner = value(), value();pet = rng.choice(['cat', 'dog', 'rabbit', 'bird', 'hamster'])
        turns = [f'My name is {owner}. My {pet} is called {name}.', 'Thanks for telling me.',
                 rng.choice([f'What is my {pet} called?', f'Can you recall the name of my {pet}?',
                             f'Which name belongs to my {pet}?', f'What did I name my {pet}?'])]
        add('remember_other', turns, f'Your {pet} is named {name}.')
    for _ in range(5000):
        animal = rng.choice(['fox', 'rabbit', 'bear', 'cat', 'dog', 'duck', 'mouse', 'frog', 'bird'])
        container = rng.choice(['box', 'bag', 'basket', 'chest', 'jar', 'pouch'])
        place = rng.choice(['tree', 'pond', 'house', 'path', 'garden'])
        obj = rng.choice(['tiny key', 'little toy', 'small coin', 'shiny button', 'soft feather', 'red ribbon', 'small note', 'smooth stone'])
        turns = [f"Let's imagine a story about a little {animal}.", f'The {animal} found a {container} near a {place}.']
        mode = rng.random()
        if mode < .5:
            turns += [rng.choice([f'What might be inside the {container}?', 'What could it hold?', f'Give one idea for something in the {container}.', 'What might our friend find inside?'])]
            target = f'A {obj} could be inside.'
        elif mode < .75:
            turns += [rng.choice(['What could happen next?', 'What might our friend do now?', 'How could the story continue?'])]
            target = f'The {animal} could open the {container} carefully.'
        else:
            turns = [rng.choice([f'Tell me a tiny story about a {animal}.', f'Can we start a little story about a {animal}?'])]
            target = f'A little {animal} found a {container} one day.'
        add('story', turns, target)
    project_queries = ['What would be an easy first project?', 'Can you suggest a small project to begin with?',
                       'I need a simple starting idea. Any suggestion?', 'What could I try first?',
                       'Could you name one little beginner project?', 'How could I make a small start?']
    for _ in range(5000):
        hobby = rng.choice(list(PROJECTS))
        turns = [rng.choice([f"I'd like to try {hobby}.", f'I am interested in {hobby}.', f'I have been thinking about {hobby}.',
                             f'I want to learn a little {hobby}.']),
                 rng.choice(['That could be fun.', 'A small start can help.', 'It sounds interesting.']), rng.choice(project_queries)]
        add('followup', turns, rng.choice(PROJECTS[hobby]))
    unknown = [
        (['Can you help me pick one?', 'Which of them should I choose?', 'I cannot decide between them.', 'Help me decide what to pick.', 'Which choice seems best?'],
         ['What are the choices?', 'What are you choosing between?']),
        (['Can you help me do it?', 'Could you show me how to do that?', 'What is the best way to do it?', 'I need a better way to do this.', 'How can I get this done?'],
         ['What are you trying to do?', 'What task do you need help with?']),
        (['Is that a smart plan?', 'Does that idea sound good?', 'Would that be worth trying?', 'What do you think about the idea?'],
         ['What idea are you thinking of?', 'What is the plan?']),
        (['Can you tell me about it?', 'What do you think of that?', 'Would you like that?', 'Can you explain this to me?'],
         ['What are you referring to?', 'What do you mean?']),
    ]
    for _ in range(2000):
        questions, answers = rng.choice(unknown)
        question = rng.choice(['', 'Please help. ', 'I am a bit unsure. ', 'One question: ']) + rng.choice(questions)
        add('clarify', [question], rng.choice(answers))
    categories = {
        'animals': ['cat', 'dog', 'fox', 'bear', 'mouse', 'rabbit', 'duck', 'goat', 'horse', 'sheep', 'frog', 'wolf', 'deer', 'lion', 'tiger', 'owl', 'ant', 'bee', 'bat', 'fish'],
        'foods': ['apple', 'bread', 'rice', 'soup', 'cheese', 'cake', 'banana', 'pear', 'bean', 'carrot', 'corn', 'orange', 'peach', 'plum', 'potato', 'egg', 'fish', 'melon', 'grape', 'cookie'],
    }
    for _ in range(5000):
        category = rng.choice(list(categories));a, b, c, d = rng.sample(categories[category], 4)
        turns = [rng.choice([f"Let's name {category}. You go first.", f"Let's take turns naming {category}.", f'Start a game of naming {category} with me.'])]
        stage = rng.randrange(3);target = a
        if stage >= 1:
            turns += [a + '.', rng.choice([f'My turn: {b}. Now you.', f"I'll say {b}. Your turn.", f'{b}! What is your next one?'])];target = c
        if stage == 2:
            turns += [c + '.', rng.choice(['One more, please.', f'Can you name another of those {category}?', 'Give a different one now.'])];target = d
        add('play', turns, target + '.')
    for _ in range(1000):
        activity = rng.choice(['reading', 'drawing', 'a puzzle', 'music', 'folding paper'])
        turns = [rng.choice(['I want something quiet to do.', 'I would enjoy an easy activity.', 'I need a little break.']),
                 f'You could try {activity}.',
                 rng.choice(['Could we do something with just words?', 'Can we try a game just in this chat?',
                             'I would rather do something by talking here.', 'Could we play a little text game instead?'])]
        add('play', turns, rng.choice(["Let's name animals. Cat!", "Let's name foods. Apple!", "Let's name colors. Blue!"]))
    categories = {
        'animals': ['cat', 'dog', 'fox', 'bear', 'mouse', 'rabbit', 'duck', 'goat', 'horse', 'sheep', 'frog', 'wolf', 'deer', 'lion', 'tiger', 'owl', 'ant', 'bee', 'bat', 'fish'],
        'foods': ['apple', 'bread', 'rice', 'soup', 'cheese', 'cake', 'banana', 'pear', 'bean', 'carrot', 'corn', 'orange', 'peach', 'plum', 'potato', 'egg', 'fish', 'melon', 'grape', 'cookie'],
        'colors': ['red', 'blue', 'green', 'yellow', 'orange', 'purple', 'pink', 'white', 'black', 'brown', 'gray', 'gold'],
    }
    for _ in range(5000):
        category = rng.choice(list(categories));a, b, c, d = rng.sample(categories[category], 4)
        turns = [rng.choice([f'Let us name {category}. You go first.', f"Let's take turns naming {category}. Start us off.", f'Name one of the {category} to begin our game.'])]
        stage = rng.randrange(3)
        if stage == 0:target = a
        else:
            turns += [a + '.', rng.choice([f'I say {b}. Your turn.', f'My turn: {b}. Now you.', f'I choose {b}. Name a different one.'])]
            target = c
            if stage == 2:
                turns += [c + '.', rng.choice(['One more, please.', f'Another one of the {category}, please.', 'Name one that we have not used.'])]
                target = d
        add('play_move', turns, target + '.')
    for _ in range(1000):
        category = rng.choice(list(categories));item = rng.choice(categories[category])
        turns = ['I would like a quiet activity.', rng.choice(['You could try drawing.', 'You could read a little.', 'Try a small puzzle.']),
                 rng.choice(['Could we do something just with words?', 'Can we do something only by chatting?',
                             'I want an activity in this chat.', 'Could you suggest a simple text game instead?',
                             'I would rather do something just by talking. Any idea?'])]
        add('play', turns, f"Let's name {category}. {item.capitalize()}!")
    path = output / 'train.jsonl'
    path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))
    manifest = {'policy': 'Original vetted teacher targets plus variable-value factual recall, story binding, missing-detail clarification, and contextual hobby projects',
                'source_sha256': hashlib.sha256((Path(args.source) / 'train.jsonl').read_bytes()).hexdigest(),
                'seed': args.seed, 'rows': len(rows), 'new_curriculum_counts': dict(added), 'social_targets_shortened': shortened,
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'kinds': dict(Counter(row['kind'] for row in rows)),
                'exact_development_and_audit_contexts_excluded': len(excluded), 'reserved_audit_evaluated': False}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest), flush=True)


if __name__ == '__main__':
    main()
