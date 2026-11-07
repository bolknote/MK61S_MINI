#!/usr/bin/env python3
"""Teach recovery and factual consistency in histories produced by the actual Q4 student."""
import argparse
from collections import Counter
import json
from pathlib import Path
import random
import re
import time
from common import core, load_model, actual_q4, decode
from prepare import fingerprint

ITEMS = {
    'animals': ['cat', 'dog', 'bear', 'fox', 'rabbit', 'duck', 'frog', 'owl', 'mouse', 'deer'],
    'foods': ['apple', 'bread', 'rice', 'banana', 'carrot', 'soup', 'cheese', 'pear', 'cake', 'bean'],
    'colors': ['blue', 'red', 'green', 'yellow', 'purple', 'orange', 'pink', 'white', 'brown', 'gray'],
}
ACTIVITIES = [('music', 'song', 'You could listen to a gentle song.'),
              ('reading', 'read', 'You could read a short poem.'),
              ('drawing', 'draw', 'You could draw a little flower.'),
              ('a puzzle', 'puzzle', 'You could try a small puzzle.'),
              ('writing', 'write', 'You could write a tiny story.'),
              ('paper crafts', 'fold', 'You could fold a little paper boat.')]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True)
    parser.add_argument('--source-data', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--suite', default='suite')
    parser.add_argument('--per-family', type=int, default=800)
    parser.add_argument('--device', default='cuda')
    parser.add_argument('--seed', type=int, default=817262)
    args = parser.parse_args()
    rng = random.Random(args.seed)
    output = Path(args.output);assert not output.exists();output.mkdir(parents=True)
    model, tokenizer, device = load_model(args)
    def read(path):return [json.loads(line) for line in Path(path).read_text().splitlines()]
    excluded = {fingerprint(row['messages']) for split in ['dev', 'test'] for row in read(Path(args.suite) / (split + '.jsonl'))}
    scenarios = []
    def name():return ''.join(rng.choice('bcdfghjklmnprstvwz') + rng.choice('aeiou') for _ in range(rng.choice([2, 3]))).capitalize()
    for family in ['pet', 'drawing', 'rest', 'color', 'game', 'relief']:
        for _ in range(args.per_family):
            state = {'family': family, 'history': [], 'user': name(), 'pet_name': name(),
                     'pet': rng.choice(['cat', 'dog', 'rabbit', 'bird', 'hamster']),
                     'animal': rng.choice(ITEMS['animals']), 'object': rng.choice(['hat', 'kite', 'boat', 'flag', 'balloon']),
                     'color': rng.choice(ITEMS['colors']), 'old': rng.choice(ITEMS['colors']),
                     'category': rng.choice(list(ITEMS)), 'rejected': rng.sample(ACTIVITIES, 2)}
            scenarios.append(state)
    rng.shuffle(scenarios)
    def prompt(state, turn):
        f = state['family'];h = state['history']
        if f == 'pet':
            if turn == 0:return rng.choice([f'Hello, you can call me {state["user"]}.', f'Hi! My friends call me {state["user"]}.']), 'greet', f'Hello, {state["user"]}! Nice to meet you.'
            if turn == 1:return rng.choice([f'I have a {state["pet"]}. Its name is {state["pet_name"]}.', f'My pet {state["pet"]} is called {state["pet_name"]}.']), 'sharing', f'That is a lovely name for your {state["pet"]}.'
            return rng.choice([f'Which name belongs to my {state["pet"]}?', f'What did I call my {state["pet"]}?', f'Can you recall what my {state["pet"]} is called?']), 'remember_other', f'Your {state["pet"]} is named {state["pet_name"]}.'
        if f == 'drawing':
            if turn == 0:return rng.choice([f'I want to draw a {state["animal"]}. Give me an idea.', f'What is a cute way to draw a {state["animal"]}?']), 'suggest', f'Draw a {state["animal"]} wearing a little hat.'
            if turn == 1:return rng.choice([f'How could I make this {state["animal"]} look funny?', f'What silly detail could this {state["animal"]} have?', 'Could you suggest a funny detail for that animal?']), 'followup', f'Give the {state["animal"]} big boots.'
            return rng.choice([f'I will add a {state["object"]}. What color would suit it?', f'It could have a {state["object"]}. A color idea?', f'Which color could I use for its {state["object"]}?']), 'followup', f'You could make the {state["object"]} {state["color"]}.'
        if f == 'rest':
            if turn == 0:return rng.choice(['I would enjoy a calm little activity.', 'I need something simple and quiet for a while.', 'What is an easy relaxing activity?']), 'suggest', 'You could read a short poem.'
            if turn == 1:
                a,b = state['rejected'];text = ' '.join(m['content'] for m in h if m['role'] == 'assistant').lower()
                allowed = [a for a in ACTIVITIES if a not in state['rejected'] and a[1] not in text]
                answer = rng.choice(allowed or [a for a in ACTIVITIES if a not in state['rejected']])[2]
                return rng.choice([f'I would rather avoid {a[0]} and {b[0]}. A different idea?', f'No {a[0]} or {b[0]} for me. What else?', f'Can you think of something besides {a[0]} and {b[0]}?']), 'alternative', answer
            return rng.choice(['Could we try an activity using only words here?', 'I would like a little text game with you instead.', 'Let us do something entirely in our conversation. Any idea?']), 'play', "Let's take turns naming foods. I will start: apple."
        if f == 'color':
            if turn == 0:return rng.choice([f'For my picture I choose {state["old"]}.', f'My preferred color is {state["old"]}.']), 'preference', f'{state["old"].capitalize()} is a lovely color.'
            if turn == 1:return rng.choice([f'On second thought, I choose {state["color"]} instead.', f'I changed my mind. Make it {state["color"]}.']), 'correction', f'Okay, your choice is {state["color"]}.'
            return rng.choice(['Can you recall my final color choice?', 'Which color am I using after the change?', 'What color did I end up choosing?']), 'remember_user', f'You chose {state["color"]}.'
        if f == 'game':
            if turn == 0:question = rng.choice([f'Can we name {state["category"]}? Start the game.', f'Let us take turns with {state["category"]}. You begin.'])
            elif turn == 1:question = rng.choice([f'My choice is {rng.choice(ITEMS[state["category"]])}. Now you.', f'I choose {rng.choice(ITEMS[state["category"]])}. What is your next one?'])
            else:question = rng.choice([f'Can you name one more of those {state["category"]}?', f'Give another example of {state["category"]}.', 'Another one that we have not named yet?'])
            text = ' '.join([m['content'] for m in h] + [question]).lower()
            used = set(re.findall(r'\b[a-z]+\b', text))
            answer = next(item for item in ITEMS[state['category']] if item not in used)
            return question, 'play_move', answer.capitalize() + '.'
        if turn == 0:return rng.choice(['I dropped my cup and made a mess. How annoying.', 'I lost the page I was writing. I feel upset.', 'My little craft broke after all that work.']), 'negative', 'Oh no. That sounds frustrating.'
        if turn == 1:return rng.choice(['Maybe a short rest would help. An easy idea?', 'I want a little break from that. What could I do?', 'Could you suggest something simple to help me relax?']), 'suggest', 'You could listen to a gentle song.'
        return rng.choice(['Talking helped. I feel better now, thank you.', 'I am less upset now. Thanks for listening.', 'Thanks. My mood is much better after our chat.']), 'positive', 'I am glad you are feeling better.'
    added = [];rollouts = [];start = time.monotonic()
    with actual_q4(model, None):
        for turn in range(3):
            cases, targets = [], []
            for index, state in enumerate(scenarios):
                question, kind, target = prompt(state, turn)
                state['history'].append({'role': 'user', 'content': question})
                messages = [dict(m) for m in state['history']]
                cases.append({'id': f'on-policy:{index}:{turn}', 'messages': messages})
                targets.append((kind, target))
            replies = decode(model, tokenizer, cases, device, batch_size=64)
            for state, case, reply, (kind, target) in zip(scenarios, cases, replies, targets):
                state['history'].append({'role': 'assistant', 'content': reply['reply']})
                identity = fingerprint(case['messages'])
                if identity in excluded:continue
                added.append({'id': 'on-policy:' + identity, 'kind': kind, 'intent_label': kind, 'messages': case['messages'],
                              'target': f'<|tt_intent:{kind}|> ' + target, 'plain_target': target, 'source': 'on_policy_curriculum',
                              'student_reply': reply['reply'], 'scenario_family': state['family']})
            print(json.dumps({'turn': turn, 'scenarios': len(scenarios), 'training_rows': len(added), 'seconds': round(time.monotonic() - start, 1)}), flush=True)
    original = read(Path(args.source_data) / 'train.jsonl')
    rows = {fingerprint(row['messages']): row for row in original + added if fingerprint(row['messages']) not in excluded}
    path = output / 'train.jsonl';path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows.values()))
    (output / 'rollouts.jsonl').write_text(''.join(json.dumps({'family': state['family'], 'messages': state['history']}, ensure_ascii=False) + '\n' for state in scenarios))
    report = {'policy': 'Consistent response corpus plus variable-value conversations using actual Q4 student histories, including incorrect bot details',
              'rows': len(rows), 'on_policy_rows_before_deduplication': len(added), 'kinds': dict(Counter(r['kind'] for r in rows.values())),
              'sha256': core.digest(path), 'source_model_sha256': core.digest(Path(args.model) / 'model.safetensors'),
              'source_data_sha256': core.digest(Path(args.source_data) / 'train.jsonl'), 'source_code_sha256': core.digest(__file__),
              'exact_reserved_contexts_excluded': len(excluded), 'reserved_audit_evaluated': False, 'seconds': time.monotonic() - start}
    core.save(output / 'manifest.json', report);print(json.dumps(report), flush=True)


if __name__ == '__main__':main()
