#!/usr/bin/env python3
"""Test the early F4 exit BEFORE searching for a native counter constructor.

The reference receives only the existing native digit1 protocol. Its original
all-five-chip snapshots are replayed exactly. Only a separate ROM/ring model
gets the counterfactual R23=0 at the first F4; it is NOT a key recipe.
Local contracts allow arbitrary per-tick keys and future serial pages.
"""
import hashlib
import json
from pathlib import Path
import runpy
import subprocess

from z3 import And, Or, UGE, simplify

root = Path(__file__).resolve().parent
w = runpy.run_path(str(root / 'cache46-writer-contracts.py'))
q = w['q']
engine = runpy.run_path(str(root / 'cache-stack-lift-ring.py'))
native = json.loads(subprocess.check_output([
    'node', str(root / 'cache-control-f-transfer-native.cjs'), '--proof-input'], text=True))


def number(value):
    return simplify(value).as_long()


def word(values, lane=0):
    return ''.join(f'{number(v):X}' for v in values[lane:36:3])


def complete_fingerprint(state, tags, phase):
    """Equality here includes every modeled field, wire, phase and ring tag."""
    values = [phase]
    for name in engine['names']:
        values.extend(number(state['_wire'][name][field]) for field in ('input', 'output'))
        if name.startswith('ir'):
            values.extend(number(v) for v in state[name])
        else:
            for field in ('r', 'm', 'st'):
                values.extend(number(v) for v in getattr(state[name], field))
            values.extend(number(getattr(state[name], field))
                          for field in ('s', 's1', 'l', 't', 'carry'))
        values.extend(tags[name])
    return tuple(values)


def advance_fixed(state, tags, phase, command, end, pins, *, events=None,
                  losses=None, label='quiet'):
    """Skip only a PROVED full-state deterministic period with fixed pins.

    Each period is executed in full first. D4-containing cycles are not skipped,
    so numeric writer events are never hidden by the acceleration.
    """
    assert command <= end
    seen, d4_count, loss_count = {}, 0, 0
    while command < end:
        signature = complete_fingerprint(state, tags, phase)
        if signature in seen:
            previous, old_d4_count, old_loss_count = seen[signature]
            period = command-previous
            repeats = (end-command)//period
            if repeats and d4_count == old_d4_count and loss_count == old_loss_count:
                command += repeats*period
                print(f'PASS {label}: complete ALL5/wires/phase/tags period{period}; '
                      f'skipped{repeats} repetitions at constant pins, noD4/A7F-loss', flush=True)
                seen.clear()
                continue
        seen[signature] = command, d4_count, loss_count
        code = engine['boundary_ip'](state['ik1302'])
        before = state['ik1302']
        event = None
        if code == 0xD4:
            d4_count += 1
            event = {'command': command, 'slot': tags['ik1302'][0][0],
                     'A': word(before.r), 'sourceA7': number(before.r[21])}
        old_a7 = number(before.r[21])
        old_m2 = word(before.m, 1)
        phase, emitted = engine['step'](state, tags, phase, pins)
        if losses is not None and old_a7 == 15 and number(state['ik1302'].r[21]) != 15:
            loss_count += 1
            losses.append({'command': command, 'ip': f'{code:02X}',
                           'beforeA': word(before.r), 'oldM2': old_m2,
                           'afterA': word(state['ik1302'].r)})
        if event is not None:
            event['outgoingSign'] = number(emitted['ik1302'][24])
            if events is not None:
                events.append(event)
        command += 1
    return phase, command


def snapshot_matches(state, phase, target):
    for name in engine['names']:
        for field in ('input', 'output'):
            assert number(state['_wire'][name][field]) == target[name][field], (name, field)
        if name.startswith('ir'):
            assert [number(v) for v in state[name]] == target[name]['m'], name
            assert phase == target[name]['tick'], name
        else:
            for field in ('r', 'm', 'st'):
                assert [number(v) for v in getattr(state[name], field)] == target[name][field], (name, field)
            for field in ('s', 's1', 'l', 't', 'carry'):
                assert number(getattr(state[name], field)) == target[name][field], (name, field)


def validate_native():
    assert native['report']['observerIndependent'] is True
    assert native['report']['ordinaryCSignFCreated'] is False
    for name, expected in (
        ('mk61.cjs', 'b15bc586ac3804eb5622b8072e88f35bcd2081abbe2195fcefa5a718e56ece0c'),
        ('rom.cjs', '6c3f85b3e942cdd4d4191e46e98a50829eb850011b8b7a3cc01b12e5e2a31a33')):
        assert hashlib.sha256((q['ROM_PATH'].parent / name).read_bytes()).hexdigest() == expected, name
    entries = native['prefix']
    state, tags, phase = engine['make'](entries[0])
    snapshot_matches(state, phase, entries[0]['state'])
    for entry, following in zip(entries, entries[1:]):
        assert engine['boundary_ip'](state['ik1302']) == entry['ip']
        pins = {name: (entry['state'][name]['keyX'], entry['state'][name]['keyY'])
                for name in engine['models']}
        phase, _ = engine['step'](state, tags, phase, pins)
        snapshot_matches(state, phase, following['state'])
    assert len(entries)-1 == 60
    print('PASS native control: ALL60 consecutive five-chip boundaries, wires and IR phase; '
          'fresh unobserved mirror; reference/ROM hashes unchanged.', flush=True)


def known_formatter_prefix():
    entries = native['prefix']
    start = next(i for i, entry in enumerate(entries) if entry['ip'] == 0xF2)
    end = next(i for i in range(start+1, len(entries)) if entries[i]['ip'] == 0xF4)
    state, _, _ = engine['make'](entries[start])
    a = state['ik1302']
    p = w['base'](a, 0xF2)
    for offset, entry in enumerate(entries[start:end]):
        code = entry['ip']
        w['prove'](p, w['ip'](a) == code, f'native-shaped formatter forces{code:02X}', False)
        before = a
        out = []
        a = w['ex'](a, code, *q['arbitrary_keys'](f'early_mask_prefix_keys{offset}'),
                    emitted_outputs=out)
        w['prove'](p, w['eq'](out, before.m),
                   f'formatter prefix{offset}/{code:02X} no outgoing write', False)
    w['prove'](p, And(w['ip'](a) == 0xF4, a.r[23] == 15,
                     a.r[21] == 15, a.r[24] == 15, a.r[25] == 1),
               'known digit1 F2 inlet forces firstF4 with R23=F/A7=F/A8=F/B8=1; '
               'arbitrary per-tick keys/future serial pages cannot repair its counter')
    assert end-start == 25
    print('SCOPE: this25-command primary prefix begins at the concrete native F2 inlet. '
          'Different earlier preparation/metadata or other inlet is not excluded.', flush=True)


def local_exit_contracts():
    a = q['State']('early_mask_F4')
    p = w['base'](a, 0xF4)
    p.add(a.r[23] == 0, a.r[21] == 15, a.r[25] == 1)
    out = []
    b = w['ex'](a, 0xF4, *q['arbitrary_keys']('early_mask_F4_keys'), emitted_outputs=out)
    w['prove'](p, And(w['ip'](b) == 0xEA, b.r[21] == 15, b.r[24] == 1,
                     w['eq'](b.r[1:36:3], a.r[1:36:3]), w['eq'](out, a.m)),
               'CONDITIONAL earlyF4 copies B8=1 into A8, retains A7=F, callsEA; no ring write')
    out = []
    c = w['ex'](b, 0xEA, *q['arbitrary_keys']('early_mask_F4_EA_keys'), emitted_outputs=out)
    w['prove'](p, And(c.r[21] == 15, c.r[24] == 2, w['eq'](out, b.m)),
               'earlyF4/EA keeps sourceA7=F but changes A8 from1 to2; no ring write')

    a = q['State']('early_mask_EA_gate')
    p = w['base'](a, 0xEA)
    out = []
    b = w['ex'](a, 0xEA, *q['arbitrary_keys']('early_mask_EA_gate_keys'), emitted_outputs=out)
    # Exact carry chain of the three B order/type tetras, not a guess from R2.
    chooses_d8 = Or(UGE(a.r[34], 10),
                    And(a.r[34] == 9, a.r[28] == 0, a.r[31] == 0))
    w['prove'](p, And((w['ip'](b) == 0xD8) == chooses_d8,
                     Or(w['ip'](b) == 0xD8, w['ip'](b) == 0xEC),
                     w['eq'](out, a.m)),
               'EA choosesD8 iff B11>=A or B11=9/B9=B10=0; otherwiseEC; '
               'R2 is not its dispatch predicate')

    a = q['State']('early_mask_EC')
    p = w['base'](a, 0xEC)
    out = []
    b = w['ex'](a, 0xEC, *q['arbitrary_keys']('early_mask_EC_keys'), emitted_outputs=out)
    w['prove'](p, And(w['ip'](b) == 0x40,
                     w['eq'](b.r[1:36:3], a.r[0:36:3]),
                     w['eq'](b.r[0:36:3], a.r[1:36:3]),
                     b.r[37] == 14, b.r[40] == 3, w['eq'](out, a.m)),
               'EC swaps A12/B12, sets B service pair3E and enters40; '
               'all A-mask fields remain in B, not globally erased')

    a = q['State']('early_mask_EE_sign_pair')
    other = q['State']('early_mask_EE_other')
    c = a.copy()
    c.r[21] = other.r[21]
    p = w['base'](a, 0xEE)
    pins = q['arbitrary_keys']('early_mask_EE_pair_keys')
    serial = q['State']('early_mask_EE_pair_serial').m
    out_a, out_c = [], []
    b = w['ex'](a, 0xEE, *pins, serial_inputs=serial, emitted_outputs=out_a)
    d = w['ex'](c, 0xEE, *pins, serial_inputs=serial, emitted_outputs=out_c)
    w['prove'](p, And(w['same'](b, d), w['eq'](out_a, out_c)),
               'EE forgets arbitrary oldA7 in ALL primary R/ST/M/scalars and outgoing ring; '
               'earlier independent reserves are not excluded')


def conditional_early_exit():
    entry = next(v for v in native['prefix'] if v['ip'] == 0xF4)
    assert entry['command'] == 59 and entry['state']['ik1302']['r'][23] == 15
    state, tags, phase = engine['make'](entry)
    initial = engine['ring'](state, tags)
    # Sole hypothesis. This model state never enters the reference emulator.
    state['ik1302'].r[23] = q['N4'](0)
    held = {name: (entry['state'][name]['keyX'], entry['state'][name]['keyY'])
            for name in engine['models']}
    sequence, writers = [], []
    early = []
    for offset in range(1100):
        command = entry['command'] + offset
        pins = dict(held)
        if command >= 560:
            pins['ik1302'] = (0, 0)
        code = engine['boundary_ip'](state['ik1302'])
        sequence.append(code)
        a = state['ik1302']
        if offset < 4:
            early.append({'ip': f'{code:02X}', 'A': word(a.r), 'B': word(a.r, 1),
                          'R23': number(a.r[23])})
        if code == 0xD4:
            raise AssertionError('new conditional D4 path requires investigation')
        if command >= 560 and code == 0x35:
            break
        before = engine['ring'](state, tags)
        if code == 0xE7:
            writers.append({'ip': 'E7', 'slot': tags['ik1302'][1][0], 'A': word(a.r)})
        phase, _ = engine['step'](state, tags, phase, pins)
        after = engine['ring'](state, tags)
        assert all(number(before[slot][i]) == number(after[slot][i])
                   for slot in engine['slots'] for i in range(42)), (offset, code)
        if offset % 100 == 99:
            print(f'conditional earlyF4: {offset+1} complete five-chip transitions; '
                  'all630 circulating tetras held, noD4', flush=True)
    else:
        raise AssertionError('fixed-release continuation did not reach35')
    assert offset == 502 and command == 561
    assert early[0]['A'] == 'FFFFFFFFFFFF'
    assert [v['ip'] for v in early] == ['F4', 'EA', 'EC', '40']
    assert early[1]['A'] == 'FFFFFFFF1FFF'
    assert early[2]['A'] == early[3]['B'] == 'FFFFFFFF2FFF'
    assert early[3]['A'] == '000000001000'
    assert writers == [{'ip': 'E7', 'slot': 'X', 'A': '000000000000'}]
    final = engine['ring'](state, tags)
    assert all(number(initial[slot][i]) == number(final[slot][i])
               for slot in engine['slots'] for i in range(42))
    # M1 includes all15 ordinary words (C among them), M3 all105 program
    # bytes; the complete ring also covers every Ms word/service tetra.
    print('CONDITIONAL early-exit report:', json.dumps({
        'native': False, 'hypothesis': 'R23=0 only at firstF4; not keyboard preparation',
        'early': early, 'transitions': offset, 'firstReleased35Command': command,
        'writers': writers, 'all630RingTetrasHeld': True,
        'D4': False, 'ordinaryCSignFCreated': False,
        'primaryFinal': {'A': word(state['ik1302'].r), 'B': word(state['ik1302'].r, 1),
                         'C': word(state['ik1302'].r, 2),
                         'ST': [word(state['ik1302'].st, lane) for lane in range(3)]},
        'partialK2': False}), flush=True)
    print('LIMIT: fixed native digit1/560-macro release schedule in a detached model. '
          'A-mask survives EC in B; this is NOT global erasure, not a native counter '
          'constructor and not a prohibition of other reserves/entries/later key sequences. '
          'One early counter repair alone does not create C-signF or partial K2.', flush=True)
    return state, tags, phase, command


def store_after_early_exit(start):
    fixture = json.loads(subprocess.check_output([
        'node', str(root / 'cache-input-mask-store-native.cjs'), '--proof-input'], text=True))
    assert fixture['report']['observerIndependent'] is True
    assert fixture['report']['CAfter'] == '000010000000'
    held = {name: (fixture['prefix'][0]['state'][name]['keyX'],
                   fixture['prefix'][0]['state'][name]['keyY'])
            for name in engine['models']}
    released = dict(held)
    released['ik1302'] = (0, 0)
    second_key = dict(held)
    second_key['ik1302'] = (9, 8)
    assert held['ik1302'] == (6, 9)
    assert (fixture['second'][0]['state']['ik1302']['keyX'],
            fixture['second'][0]['state']['ik1302']['keyY']) == (9, 8)

    # New native control: both observed command windows, and the COMPLETE end
    # of all six frames. Long waits are shortened only by exact state periods.
    state, tags, phase = engine['make'](fixture['entry'])
    command = 0
    for entries, pins in ((fixture['prefix'], held), (fixture['second'], second_key)):
        if entries[0]['command'] > command:
            phase, command = advance_fixed(state, tags, phase, command, 560, held,
                                           label='native STORE held')
            phase, command = advance_fixed(state, tags, phase, command, 1120, released,
                                           label='native STORE release')
        snapshot_matches(state, phase, entries[0]['state'])
        for entry, following in zip(entries, entries[1:]):
            assert command == entry['command']
            assert engine['boundary_ip'](state['ik1302']) == entry['ip']
            phase, _ = engine['step'](state, tags, phase, pins)
            command += 1
            snapshot_matches(state, phase, following['state'])
    phase, command = advance_fixed(state, tags, phase, command, 1680, second_key,
                                   label='native STORE C held')
    phase, command = advance_fixed(state, tags, phase, command, 3360, released,
                                   label='native STORE final release')
    snapshot_matches(state, phase, fixture['end']['state'])
    print('PASS native STORE control: ALL64+89 consecutive five-chip transitions '
          'including D4(Y)/sign0, plus complete3360-macro final state and fresh mirror.', flush=True)

    state, tags, phase, command = start
    initial = engine['ring'](state, tags)
    phase, command = advance_fixed(state, tags, phase, command, 3360, released,
                                   label='conditional earlyF4 remaining input frames')
    stable_a = word(state['ik1302'].r)
    writers, losses = [], []
    for end, pins, label in (
        (3920, held, 'conditional STORE held'),
        (4480, released, 'conditional STORE release'),
        (5040, second_key, 'conditional STORE C held'),
        (6720, released, 'conditional STORE final release')):
        phase, command = advance_fixed(state, tags, phase, command, end, pins,
                                       events=writers, losses=losses, label=label)
    final = engine['ring'](state, tags)
    changes = [{'slot': slot, 'tetra': i, 'before': number(initial[slot][i]),
                'after': number(final[slot][i])}
               for slot in engine['slots'] for i in range(42)
               if number(initial[slot][i]) != number(final[slot][i])]
    assert stable_a == 'FFFFFFFF2FFF'
    assert writers == [{'command': 4545, 'slot': 'Y', 'A': '000000000000',
                        'sourceA7': 0, 'outgoingSign': 0}]
    assert losses[0] == {'command': 4514, 'ip': 'EE', 'beforeA': 'FFFFFFFF2FC4',
                         'oldM2': '000000000000', 'afterA': '000000000000'}
    assert changes == [] and number(final['Y'][24]) == 0
    print('CONDITIONAL ordinary STORE after earlyF4:', json.dumps({
        'native': False, 'hypothesis': 'only original firstF4 R23=0; fixed public frame schedule',
        'stableWorkingA': stable_a, 'writers': writers, 'A7FLosses': losses,
        'ringChanges': changes,
        'ordinaryCSign': number(final['Y'][24]),
        'ordinaryCWord': word(final['Y']), 'partialK2': False}), flush=True)
    print('SCOPE: this STORE continuation still depends on the NON-NATIVE earlyF4 counter. '
          'It is not a construction of C-signF by keys or a program-cache/Ms transfer.', flush=True)


if __name__ == '__main__':
    validate_native()
    known_formatter_prefix()
    local_exit_contracts()
    start = conditional_early_exit()
    store_after_early_exit(start)
