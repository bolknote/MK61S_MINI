#!/usr/bin/env python3
"""Development-only factorial probe for echoes, pronouns and reverse entity queries."""
import argparse
import json
from pathlib import Path
import random
from common import core


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--output', required=True)
    p.add_argument('--question-variants', action='store_true')
    args = p.parse_args(); out = Path(args.output); assert not out.exists(); out.mkdir(parents=True)
    rng = random.Random(823719); rows = []
    names = 'Arlo Bea Cora Dax Eden Flora Gus Hana Ivo June Kira Lyle Mara Nico Otto Pia Remy Suki Vera Wren'.split()
    colors = 'red blue green yellow purple orange pink white black brown gray'.split()
    pets = 'cat dog rabbit hamster turtle parrot'.split()
    objects = 'scarf hat kite cup bag ball notebook bottle toy'.split()
    for i in range(32):
        field = 'name' if i % 2 else 'color'; noun = rng.choice(pets if field == 'name' else objects)
        old, new = rng.sample(names if field == 'name' else colors, 2)
        initial = f'My {noun} is called {old}.' if field == 'name' else f'My {noun} is {old}.'
        explicit = f'Actually, my {noun} is called {new} now.' if field == 'name' else f'Actually, my {noun} is {new} now.'
        pronoun = f'Actually, it is called {new} now.' if field == 'name' else f'Actually, it is {new} now.'
        echo = f'{old} is a lovely name for your {noun}.' if field == 'name' else f'Your {noun} is {old}.'
        question = f'What name does my {noun} have now?' if field == 'name' else f'Which color is my {noun} now?'
        answer = f'Your {noun} is called {new}.' if field == 'name' else f'Your {noun} is {new}.'
        for echoing in [False, True]:
            for elliptical in [False, True]:
                history = [{'role': 'user', 'content': initial},
                    {'role': 'assistant', 'content': echo if echoing else 'Thanks for telling me.'},
                    {'role': 'user', 'content': pronoun if elliptical else explicit},
                    {'role': 'assistant', 'content': 'Okay, thanks for correcting me.'}]
                for known in [True, False]:
                    q = question if known else f'Where did I say my {noun} is?'
                    intent = f'Recall the latest {field}: {new}, not {old}.' if known else 'The location was never provided. Acknowledge missing information.'
                    rows.append({'id': f'factorial:{i}:{int(echoing)}:{int(elliptical)}:{int(known)}',
                        'messages': history + [{'role': 'user', 'content': q}], 'intent': intent,
                        'reference': answer if known else f'You have not told me where your {noun} is.',
                        'family': 'state_factorial', 'field': field, 'known': known,
                        'echo': echoing, 'pronoun_update': elliptical, 'expected_value': new if known else None,
                        'obsolete_value': old if known else None, 'base_case': i})
        if field == 'name':
            rows.append({'id': f'reverse:{i}', 'messages': [{'role': 'user', 'content': initial},
                {'role': 'assistant', 'content': echo}, {'role': 'user', 'content': f'Who is {old}?'}],
                'intent': f'{old} is the user\'s {noun}. Do not invent another name or take the pet as the bot.',
                'reference': f'{old} is your {noun}.', 'expected_value': noun, 'family': 'reverse_entity', 'base_case': i})
    if args.question_variants:
        variants = []
        for row in rows:
            if row['family'] != 'state_factorial' or not row['known']: continue
            variant = dict(row, id=row['id'] + ':plain-question', temporal_question=False,
                messages=[dict(m) for m in row['messages']])
            variant['messages'][-1]['content'] = variant['messages'][-1]['content'].replace(' now?', '?')
            row['temporal_question'] = True; variants.append(variant)
        rows += variants
    path = out / 'cases.jsonl'; path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
    core.save(out / 'manifest.json', {'rows': len(rows), 'sha256': core.digest(path), 'seed': 823719,
        'purpose': 'Observed development diagnostic only; no training, no independent audit, no new quality gate',
        'factorial_matched_base_cases': 32, 'reverse_entity_cases': 16,
        'matched_questions_with_and_without_now': args.question_variants, 'reserved_audit3_opened': False})
    print(json.dumps({'rows': len(rows), 'output': str(out)}))


if __name__ == '__main__': main()
