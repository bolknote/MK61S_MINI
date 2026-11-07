#!/usr/bin/env python3
"""Combine inverse-distilled speech with deterministic variable-value skills."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import re
from prepare import fingerprint
from grade import grade


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--consistent', default='consistent')
    parser.add_argument('--skills', required=True)
    parser.add_argument('--suite', default='suite')
    parser.add_argument('--output', default='data')
    args = parser.parse_args()
    output = Path(args.output);assert not output.exists();output.mkdir(parents=True)
    def read(path):return [json.loads(line) for line in Path(path).read_text().splitlines()]
    excluded = {fingerprint(row['messages']) for split in ['dev', 'test'] for row in read(Path(args.suite) / (split + '.jsonl'))}
    consistent = read(Path(args.consistent) / 'train.jsonl')
    # Check fixed-answer appropriateness on a stable stratified training sample.
    groups = {kind: [r for r in consistent if r['kind'] == kind] for kind in {r['kind'] for r in consistent}}
    sample = []
    for kind in sorted(groups):
        group = sorted(groups[kind], key=lambda r: hashlib.sha256(('audit:' + r['id']).encode()).hexdigest())
        sample += group[:20]
    result = grade([dict(row, intent=row['plan']) for row in sample], [r['plain_target'] for r in sample], output / 'teacher-audit-cache')
    (output / 'teacher-audit.json').write_text(json.dumps({'grades': result, 'examples': sample}, ensure_ascii=False, indent=2))
    print('teacher_audit', result['pass_rate'], len(sample), flush=True)
    assert result['pass_rate'] >= .95, 'Fixed replies need better input compatibility'
    rejected = {row['id'] for row in result['details'] if not row['pass']}
    rows = [r for r in consistent if r['id'] not in rejected]
    skills = read(Path(args.skills) / 'train.jsonl')
    categories = {
        'animals': ['cat', 'dog', 'bear', 'fox', 'rabbit', 'duck', 'frog', 'owl'],
        'foods': ['apple', 'bread', 'rice', 'banana', 'carrot', 'soup', 'cheese', 'pear'],
        'colors': ['blue', 'red', 'green', 'yellow', 'purple', 'orange', 'pink', 'white'],
    }
    rewritten = 0
    for original in skills:
        row = dict(original)
        if row['kind'] == 'replay':rows.append(row);continue
        if row.get('source') != 'variable_value_skill_curriculum':continue
        # Random equally valid game targets invite a copy shortcut. A stable first
        # unused item is learnable and never requires copying the user's last move.
        if row['kind'] == 'play_move' or (row['kind'] == 'play' and re.fullmatch(r'[A-Za-z]+[.!]?', row['plain_target'])):
            text = ' '.join(m['content'] for m in row['messages']).lower()
            category = next((key for key in categories if key in row['messages'][0]['content'].lower()), None)
            if category is None:continue
            words = set(re.findall(r'\b[a-z]+\b', text))
            target = next((item for item in categories[category] if item not in words), None)
            if target is None:continue
            row.update(kind='play_move', intent_label='play_move', plain_target=target.capitalize() + '.',
                       target='<|tt_intent:play_move|> ' + target.capitalize() + '.')
            rewritten += 1
        rows.append(row)
    rng = random.Random(718290)
    def add(kind, turns, target):
        messages = [{'role': 'user' if i % 2 == 0 else 'assistant', 'content': text} for i, text in enumerate(turns)]
        identity = fingerprint(messages)
        if identity in excluded:return
        rows.append({'id': 'consistent-skill:' + identity, 'messages': messages, 'kind': kind, 'intent_label': kind,
                     'plain_target': target, 'target': f'<|tt_intent:{kind}|> ' + target, 'source': 'consistent_variable_curriculum'})
    colors = 'red blue green yellow orange purple pink white black brown gray'.split()
    for _ in range(6000):
        old, new = rng.sample(colors, 2)
        opening = rng.choice([f'My favorite color is {old}.', f'I like {old} best.', f'I would choose {old}.', f'{old.capitalize()} is the color I prefer.'])
        turns = [opening, rng.choice(['That is a nice color.', 'Thanks for telling me.', 'All right.'])]
        update = rng.choice([f'Actually, I prefer {new}.', f'Please change that to {new}.', f'I meant {new}, not {old}.', f'On second thought, {new} is my choice.'])
        turns += [update]
        if rng.random() < .5:
            add('correction', turns, f'Okay, your choice is {new}.')
        else:
            turns += ['Okay.', rng.choice(['Which color did I choose?', 'What color do I like now?', 'Can you recall my final color choice?', 'What is my preferred color?'])]
            add('remember_user', turns, f'You chose {new}.')
    # General category games, including mixed histories and several preceding moves.
    for _ in range(6000):
        category = rng.choice(list(categories));items = rng.sample(categories[category], 5)
        opening = rng.choice([f'Can we name {category}? You start.', f'Let us take turns with {category}.', f'Start a naming game about {category}.'])
        turns = [opening]
        for step in range(rng.randrange(3)):
            turns += [items[2 * step].capitalize() + '.', rng.choice([f'I say {items[2 * step + 1]}. Now you.', f'My choice is {items[2 * step + 1]}. Name another one.'])]
        words = set(re.findall(r'\b[a-z]+\b', ' '.join(turns).lower()))
        answer = next(item for item in categories[category] if item not in words)
        add('play_move', turns, answer.capitalize() + '.')
    unique = {}
    for row in rows:
        identity = fingerprint(row['messages'])
        if identity not in excluded:unique[identity] = row
    rows = list(unique.values());rng.shuffle(rows)
    path = output / 'train.jsonl';path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))
    manifest = {'policy': 'Consistent short teacher replies plus variable-value skills; no old teacher prose except unused replay',
                'rows': len(rows), 'kinds': dict(Counter(row['kind'] for row in rows)), 'rewritten_game_targets': rewritten,
                'source_consistent_sha256': hashlib.sha256((Path(args.consistent) / 'train.jsonl').read_bytes()).hexdigest(),
                'source_skills_sha256': hashlib.sha256((Path(args.skills) / 'train.jsonl').read_bytes()).hexdigest(),
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'teacher_audit_pass_rate': result['pass_rate'],
                'reserved_contexts_excluded': len(excluded), 'reserved_audit_evaluated': False}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2));print(json.dumps(manifest), flush=True)


if __name__ == '__main__':main()
