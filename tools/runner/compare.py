#!/usr/bin/env python3
"""Compare two Runner bundles with identical real-ROM inputs and step costs."""
import argparse
import json
from pathlib import Path
import random
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def hole_cell(state):
    value = state['regs'][11]
    return value if value <= 36 else (value-16*112-12)//28 + 1


def compare(runner, baseline, candidate, frames=1200, seed=97):
    rng = random.Random(seed)
    commands = []
    for _ in range(frames):
        for _ in range(rng.randrange(4)):
            key = rng.choice((0, 2, 4, 6, 7, 8, 9, 0x13))
            kind = rng.choice(('tap', 'down', 'up')) if key in (2, 4, 6, 8) else 'tap'
            commands.append(f'{kind} {key:X}')
        commands.append('frame')
    commands += ['tap 14', 'frame']
    outputs = []
    for bundle in (baseline, candidate):
        result = subprocess.run([str(runner.resolve()), str(bundle)],
                                input='\n'.join(commands)+'\n', text=True,
                                capture_output=True, check=True, timeout=120)
        states = [json.loads(row) for row in result.stdout.splitlines()]
        assert len(states) == len(commands)+1, result.stdout[-1000:]
        outputs.append(states)
    costs = [0, 0]
    faster = equal = slower = 0
    for i, (old, new) in enumerate(zip(*outputs)):
        context = (i, commands[max(0, i-4):i], old, new)
        for key in ('frame', 'active', 'segmented', 'auto', 'lcd_rows', 'manuals'):
            assert old[key] == new[key], (key, context)
        assert old['regs'][4:10] == new['regs'][4:10], context
        assert hole_cell(old) == hole_cell(new) and old['regs'][13] == new['regs'][13], context
        if not old['active']:
            assert not old['running'] and not new['running'], context
        costs[0] += old['steps']; costs[1] += new['steps']
        if new['steps'] < old['steps']: faster += 1
        elif new['steps'] == old['steps']: equal += 1
        else: slower += 1
    return dict(seed=seed, frames=frames, states=len(outputs[0]), equal_gameplay=True,
                baseline_steps=costs[0], optimized_steps=costs[1],
                faster_states=faster, equal_states=equal, slower_states=slower)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runner', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, default=ROOT/'programs/games/Runner')
    parser.add_argument('--frames', type=int, default=1200)
    parser.add_argument('--seed', type=int, default=97)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = compare(args.runner, args.baseline, args.candidate, args.frames, args.seed)
    text = json.dumps(result, indent=2)+'\n'
    if args.output:
        args.output.write_text(text)
    print(text, end='')


if __name__ == '__main__':
    main()
