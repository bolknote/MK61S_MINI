#!/usr/bin/env python3
"""Follow eight independent early A-mask sources across the whole five-chip ring.

This is a CONDITIONAL audit: firstF4 R23=0 has no keyboard constructor.
Replacing initial A0..A7 by free tetras tracks provenance, not native input.
The reference still receives only the existing public digit1/STORE controls.
"""
import json
from pathlib import Path
import runpy

from z3 import BitVec, simplify
from z3.z3util import get_vars

root = Path(__file__).resolve().parent
early = runpy.run_path(str(root / 'cache-input-mask-early-exit.py'))
engine, w, q = (early[name] for name in ('engine', 'w', 'q'))


def fields(state, tags, phase):
    yield 'phase', str(phase)
    for name in engine['names']:
        for field in ('input', 'output'):
            yield f'{name}.{field}', simplify(state['_wire'][name][field]).sexpr()
        if name.startswith('ir'):
            for index, value in enumerate(state[name]):
                yield f'{name}.m[{index}]', simplify(value).sexpr()
        else:
            for field in ('r', 'st', 'm'):
                for index, value in enumerate(getattr(state[name], field)):
                    yield f'{name}.{field}[{index}]', simplify(value).sexpr()
            for field in ('s', 's1', 'l', 't', 'carry'):
                yield f'{name}.{field}', simplify(getattr(state[name], field)).sexpr()
        yield f'{name}.tags', str(tags[name])


def dependence(state):
    """Syntactic free-source occurrences; semantic assertions are made separately."""
    result = {}
    for name in engine['names']:
        values = [(field, value) for field, value in state['_wire'][name].items()]
        if name.startswith('ir'):
            values += [(f'm[{index}]', value) for index, value in enumerate(state[name])]
        else:
            for field in ('r', 'st', 'm'):
                values += [(f'{field}[{index}]', value)
                           for index, value in enumerate(getattr(state[name], field))]
            values += [(field, getattr(state[name], field))
                       for field in ('s', 's1', 'l', 't', 'carry')]
        for field, value in values:
            if get_vars(value):
                result[f'{name}.{field}'] = simplify(value).sexpr()
    return result


def audit():
    early['validate_native']()
    entry = next(value for value in early['native']['prefix'] if value['ip'] == 0xF4)
    state, tags, phase = engine['make'](entry)
    assert entry['command'] == 59
    assert entry['state']['ik1302']['r'][23] == 15
    state['ik1302'].r[23] = q['N4'](0)  # Counterfactual, not a reference mutation.
    sources = [BitVec(f'early_A_source{index}', 4) for index in range(8)]
    for index, source in enumerate(sources):
        assert entry['state']['ik1302']['r'][3*index] == 15
        state['ik1302'].r[3*index] = source
    p = w['base'](state['ik1302'], 0xF4)
    pins = {name: (entry['state'][name]['keyX'], entry['state'][name]['keyY'])
            for name in engine['models']}
    initial_ring = engine['ring'](state, tags)
    command = entry['command']
    checkpoints, writers, exchanges = [], [], []
    executed = skipped = 0
    vanished = None
    first_idle = None
    # Same absolute public-key schedule as the preceding conditional STORE test.
    for end, primary_pins, label in (
        (560, (3, 1), 'digit1 held'),
        (3360, (0, 0), 'digit1 released'),
        (3920, (6, 9), 'STORE prefix held'),
        (4480, (0, 0), 'STORE prefix released'),
        (5040, (9, 8), 'registerC held'),
        (6720, (0, 0), 'STORE final release')):
        pins['ik1302'] = primary_pins
        seen = {}
        while command < end:
            signature = tuple(fields(state, tags, phase))
            if signature in seen:
                previous, old_writers, old_exchanges = seen[signature]
                period = command - previous
                repeats = (end-command)//period
                if repeats and old_writers == len(writers) and old_exchanges == len(exchanges):
                    command += repeats*period
                    skipped += repeats*period
                    print(f'PASS {label}: exact symbolic ALL5/wires/phase/tags '
                          f'period{period}; skip{repeats*period}', flush=True)
                    seen.clear()
                    continue
            seen[signature] = command, len(writers), len(exchanges)
            code = engine['boundary_ip'](state['ik1302'], p)
            if first_idle is None and command >= 560 and code == 0x35:
                first_idle = state['ik1302'].copy()
                assert command == 561
            before = dependence(state)
            if command < 63 or code in (0xEE, 0xD4):
                checkpoints.append({'command': command, 'ip': f'{code:02X}',
                                    'sourceOccurrences': before})
                print('CHECKPOINT', json.dumps(checkpoints[-1]), flush=True)
            primary_before = state['ik1302']
            if code == 0xD4:
                writers.append({'command': command, 'slot': tags['ik1302'][0][0],
                                'sourceA7': simplify(primary_before.r[21]).sexpr()})
            phase, emitted = engine['step'](state, tags, phase, pins, p)
            # This assertion covers all eight arbitrary sources, not just F.
            w['prove'](p, w['eq'](
                [value for slot in engine['slots']
                 for value in engine['ring'](state, tags)[slot]],
                [value for slot in engine['slots'] for value in initial_ring[slot]]),
                f'command{command}/{code:02X}: all630 physical ring tetras held', False)
            if code == 0xEE:
                exchanges.append({'command': command, 'after': dependence(state)})
                print('AFTER EE', json.dumps(exchanges[-1]), flush=True)
            if before and not dependence(state) and vanished is None:
                vanished = {'command': command, 'ip': f'{code:02X}'}
                print('ALL SOURCE OCCURRENCES LOST', json.dumps(vanished), flush=True)
            command += 1
            executed += 1
            if executed % 100 == 0:
                print(f'provenance: {executed} executed five-chip transitions; '
                      f'absolute command{command}', flush=True)
        print('SEGMENT END', label, command, json.dumps(dependence(state)), flush=True)
    assert vanished == {'command': 4514, 'ip': 'EE'}
    assert exchanges[0] == {'command': 4514, 'after': {}}
    assert writers == [{'command': 4545, 'slot': 'Y', 'sourceA7': '#x0'}]
    assert dependence(state) == {}
    assert first_idle is not None
    assert executed + skipped == 6720-59
    print('CONDITIONAL provenance report:', json.dumps({
        'native': False, 'freeSourceTetras': 8,
        'hypothesis': 'firstF4 R23=0 only; initial A0..A7 free for provenance',
        'executedFiveChipTransitions': executed, 'skippedByExactPeriods': skipped,
        'all630RingTetrasHeldForAllSources': True,
        'firstGlobalSourceLoss': vanished, 'D4': writers,
        'remainingSourceOccurrences': dependence(state),
        'partialK2': False}), flush=True)
    frontier = runpy.run_path(str(root / 'cache-input-sign-frontier.py'))
    frontier['concrete_idle_fe_filter'](first_idle)
    return checkpoints, exchanges, writers, vanished


if __name__ == '__main__':
    audit()
