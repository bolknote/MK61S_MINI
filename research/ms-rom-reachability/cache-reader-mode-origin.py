#!/usr/bin/env python3
"""Exact seed→mode provenance and the two conflicting 07 gates.

Local contracts use arbitrary per-tick keys and future serial inputs. A
recorded-path source identity does not certify every alternate path. Four
guarded keyboard controls have fresh unobserved whole-five-chip mirrors and
are replayed independently on the original five-chip/ring model. No reference
state, ROM, source, return tag or dispatch is repaired.
"""
import json
from pathlib import Path
import runpy
import subprocess

from z3 import And, BitVec, If, Or, UGE, sat, unsat

root = Path(__file__).resolve().parent
r = runpy.run_path(str(root / 'cache-cf-ready-control.py'))
w, q = r['w'], r['q']
r2_groups = {
    'zero': (0x00, 0x54, 0x76, 0xD0, 0xD1, 0xD8, 0xD9, 0xDF),
    'eight': (0xC3,), 'fifteen': (0x77,),
    'copy_R5': (0x58, 0x78, 0x7F, 0x8B, 0xB9),
    'copy_R1': (0x92, 0x9A), 'copy_S1': (0xB0, 0xF2),
    'toggle': (0xAF, 0xC2, 0xCA, 0xEA),
}
r5_groups = {
    'zero': (0x00, 0x76, 0x77, 0xD0, 0xD1, 0xD2, 0xD9),
    'copy_R2': (0x54, 0x58, 0x78, 0x7F, 0x8B, 0xB0, 0xB9, 0xF2),
    'copy_R8': (0x44,), 'copy_R4': (0x92, 0x9A),
    'toggle_R2': (0xEA,), 'increment': (0xF6, 0xF7),
}
r2_changes = {code: label for label, codes in r2_groups.items() for code in codes}
r5_changes = {code: label for label, codes in r5_groups.items() for code in codes}


def assignment_inventory():
    assert len(r2_changes) == 23 and len(r5_changes) == 21
    dependent_ips = []
    for code in range(256):
        a = q['State'](f'reader_mode_{code:02X}'); p = w['base'](a, code)
        pins = q['arbitrary_keys'](f'reader_mode_keys_{code:02X}')
        b = w['ex'](a, code, *pins)
        expected2 = {'zero': q['N4'](0), 'eight': q['N4'](8), 'fifteen': q['N4'](15),
            'copy_R5': a.r[5], 'copy_R1': a.r[1], 'copy_S1': a.s1,
            'toggle': a.r[2]^8, 'preserve': a.r[2]}[r2_changes.get(code, 'preserve')]
        expected5 = {'zero': q['N4'](0), 'copy_R2': a.r[2], 'copy_R8': a.r[8],
            'copy_R4': a.r[4], 'toggle_R2': a.r[2]^8, 'increment': a.r[5]+1,
            'preserve': a.r[5]}[r5_changes.get(code, 'preserve')]
        w['prove'](p, And(b.r[2] == expected2, b.r[5] == expected5),
                   f'exact ALL256 mode assignment{code:02X}', False)
        # Change BOTH original mode fields, not another field or the keys.
        other = a.copy()
        other.r[2] = BitVec(f'reader_mode_other_R2_{code:02X}', 4)
        other.r[5] = BitVec(f'reader_mode_other_R5_{code:02X}', 4)
        serial = q['State'](f'reader_mode_serial_{code:02X}').m
        b = w['ex'](a, code, *pins, serial_inputs=serial)
        c = w['ex'](other, code, *pins, serial_inputs=serial)
        p.push(); p.add(w['ip'](b) != w['ip'](c))
        answer = p.check(); p.pop(); assert answer in (sat, unsat)
        if answer == sat: dependent_ips.append(code)
        if code % 64 == 63:
            print(f'PASS exact mode assignments / paired IP dependency through{code:02X}', flush=True)
    assert dependent_ips == [0x07, 0x5A, 0x7A, 0x7D, 0x97, 0xB5, 0xF1, 0xFB]
    print('PASS ALL256: R2 has23 assignment words; R5 has21. Only8 words can '
          'change nextIP when just originalR2/R5 change. C5/8A hold both; '
          '8B/7F swap them. SAT dependency is NOT a callable keyboard entry.', flush=True)


def pair_holder(code, *, swap=False):
    a = q['State'](f'reader_mode_hold_{code:02X}_{swap}'); p = w['base'](a, code)
    b = w['ex'](a, code, *q['arbitrary_keys'](f'reader_mode_hold_keys_{code:02X}_{swap}'))
    values = (a.r[5], a.r[2]) if swap else (a.r[2], a.r[5])
    w['prove'](p, And(b.r[2] == values[0], b.r[5] == values[1]),
               f'{code:02X} exact pair'+(' swap' if swap else ' preservation'), False)


def gate_contract():
    a = q['State']('reader_mode_gate07'); p = w['base'](a, 0x07)
    b = w['ex'](a, 0x07, *q['arbitrary_keys']('reader_mode_gate07_keys'))
    w['prove'](p, And(w['ip'](b) == If(UGE(a.r[2], 5), q['BitVecVal'](0x6D, 8),
                                     q['BitVecVal'](0x09, 8)),
                     b.r[2] == a.r[2], b.r[5] == a.r[5]),
               '07 chooses6D iff R2>=5, otherwise09; all other state/keys/serial arbitrary')
    a = q['State']('reader_mode_NOP_pair'); p = w['base'](a, 0x54)
    b = w['ex'](a, 0x54, *q['arbitrary_keys']('reader_mode_NOP54_keys'))
    w['prove'](p, And(b.r[2] == 0, b.r[5] == a.r[2]),
               '54 zeroes activeR2 but reserves its exact old value inR5')
    b = w['ex'](b, 0x58, *q['arbitrary_keys']('reader_mode_NOP58_keys'))
    w['prove'](p, And(b.r[2] == a.r[2], b.r[5] == 0),
               'the54;58 mode operator pair restores oldR2, NOT a lasting zero mode')


def reset_exit_contracts():
    for code in (0xD0, 0xD1):
        a = q['State'](f'reader_mode_reset_{code:02X}'); p = w['base'](a, code)
        out = []; b = w['ex'](a, code,
            *q['arbitrary_keys'](f'reader_mode_reset_keys_{code:02X}'), emitted_outputs=out)
        target = Or(w['ip'](b) == 0xF2, w['ip'](b) == 0xF3) if code == 0xD0 else And(
            w['ip'](b) == 0x91, w['stack'](b)[0] == 0xD2)
        w['prove'](p, And(b.r[2] == 0, b.r[5] == 0,
            w['eq'](b.r[0:36:3], a.r[0:36:3]), w['eq'](b.r[1:36:3], a.r[1:36:3]),
            w['eq'](b.st[:36], a.st[:36]), w['eq'](out, a.m), target),
            f'{code:02X} clears both mode fields and holds A/B/numericST/ring, '
            + ('but forcesF2/F3, not an idle return' if code == 0xD0
               else 'but pushesD2 and forces91, not CF or idle35'))
    for code, following in ((0xD2, 0x30), (0xD9, 0xF3)):
        a = q['State'](f'reader_mode_reset_tail_{code:02X}'); p = w['base'](a, code)
        out = []; b = w['ex'](a, code,
            *q['arbitrary_keys'](f'reader_mode_reset_tail_keys_{code:02X}'), emitted_outputs=out)
        w['prove'](p, And(w['ip'](b) == following, w['eq'](b.st[:36], a.st[:36]),
                         w['eq'](b.r[1:36:3], a.r[1:36:3]), w['eq'](out, a.m)),
                   f'{code:02X} forced exit{following:02X}/B/ST/no ring writes')
        if code == 0xD2:
            p.push(); p.add(~w['eq'](b.r[0:24:3], a.r[0:24:3]))
            assert p.check() == sat; p.pop()
        else:
            w['prove'](p, w['eq'](b.r[0:24:3], a.r[0:24:3]),
                       'D9 itself holds lowerA8, but cannot choose an exit other than F3')
    print('LIMIT: a local zero-mode writer is not a preserving callable gadget. '
          'D0/D1/D9 force formatter/packet tails; D2 may alter lower rawA. '
          'A compatible native entry AND safe whole exit remain missing.', flush=True)


def origin_contract(five, zero, step):
    entries = [e for e in five['source'] if e['command'] <= 1250]
    assert entries[0]['ip'] == 0xAC and entries[-1]['ip'] == 0x9A
    assert [e['ip'] for e in entries] == [e['ip'] for e in zero['source']
                                         if e['command'] <= 1250]
    sequence = [e['ip'] for i, e in enumerate(entries)
                if not (i and e['ip'] == entries[i-1]['ip'] == 0xE5)]
    assert sequence == [int(code, 16) for code in (
        'AC E2 E5 E6 ED EE E3 91 92 93 94 95 98 9A 93 94 95 98 9A '
        'E4 DE D6 E5 E6 E9 AD A9 93 94 95 98 9A').split()]
    a = q['State']('reader_mode_AC_origin'); p = w['base'](a, 0xAC); b = a
    for index, code in enumerate(sequence):
        p.add(w['ip'](b) == code)
        b = w['ex'](b, code, *q['arbitrary_keys'](f'reader_mode_AC_origin_keys{index}'))
    w['prove'](w['base'](a, 0xAC), And(b.r[2] == a.r[1], b.r[5] == a.r[4]),
               'ALL-metadata32-operator source identity; requiring those words '
               'is still a path hypothesis, not arbitrary native execution')
    w['prove'](p, And(b.r[2] == a.r[1], b.r[5] == a.r[4]),
               'conditional32-word AC prefix ends with R2=oldAC.B0/R5=oldAC.B1; '
               'not copied from a guessed control field')
    for digit in (0, 5):
        p.push(); p.add(a.r[1] == digit, a.r[4] == 0)
        assert p.check() == sat, ('vacuous source case', digit); p.pop()
    # The source identity remains valid under ANY finite marker waits.
    wait = q['State']('reader_mode_origin_wait'); pw = w['base'](wait, 0xE5)
    after = w['ex'](wait, 0xE5, *q['arbitrary_keys']('reader_mode_origin_wait_keys'))
    w['prove'](pw, And(w['eq'](wait.st, after.st),
                     *[wait.r[j] == after.r[j] for j in range(42) if j not in (36, 39)]),
               'E5 repeats preserve every non-IP R/ST field; origin does not require12-tick waits')
    first07 = five['report']['gates'][0]['command']
    continuation = [e['ip'] for e in five['source'] if 1251 <= e['command'] < first07]
    assert continuation == [e['ip'] for e in zero['source']
                            if 1251 <= e['command'] < first07]
    for code in set(continuation): pair_holder(code)
    assert {0x01, 0x02, 0x20, 0x2F, 0xE5}.issubset(continuation)
    print('PASS source→first07: every remaining operator and all marker/normalization '
          'repetitions preserve both mode fields. Therefore on THIS reader prefix '
          '07 chooses6D iff oldAC.B0>=5. Seed0 and5 are actual native controls.', flush=True)

    bridge = [e['ip'] for e in five['source'] if
              first07 <= e['command'] < five['report']['firstC8']]
    assert len(bridge) == 23
    for code in set(bridge): pair_holder(code)
    print('PASS first07→C8: all23 intervening operators hold the same mode pair.', flush=True)

    tail = five['tail']
    assert tail[0] == 0xC8 and tail[-1] == 0x35 and tail.count(0x7F) == 1
    for code in set(tail): pair_holder(code, swap=code == 0x7F)
    assert [e for e in five['report']['pairChanges'] if
            five['report']['firstC8'] <= e['command'] < five['report']['firstIdleAfterC8']] == [
                {'command': 1643, 'ip': 0x7F, 'before': [5, 0], 'after': [0, 5]}]
    # The later real ШГ→ prefix swaps once at8B before its own07; every
    # intervening original word holds both fields for arbitrary inputs.
    upto07 = step['report']['gates'][0]['command']
    before = [e['ip'] for e in step['origin'] if e['command'] <= upto07]
    assert before.count(0x8B) == 1
    for code in set(before): pair_holder(code, swap=code == 0x8B)
    print('PASS recorded reader tail:', len(tail)-1, 'steps to first35; '
          'all mode holders except ONE7F swap. Native1643 maps(5,0)→(0,5); '
          'the later ШГ→/8B maps back(5,0). Thus unchanged d must be>=5 for '
          'the reader07→6D AND <5 for the later07→09: incompatible on THESE paths.', flush=True)
    print('LIMIT: a different post-read mode assignment, a restored/encoded reserve, '
          'another reader caller or another restore93 approach remains OPEN. '
          'This is not a global partial-K2 impossibility proof.', flush=True)


def validate_native(early, fixtures):
    engine = early['engine']; total = 0
    key_pins = {'П→X': (8, 9), '9': (11, 1), 'ШГ→': (7, 9),
                'K': (10, 9), '0': (2, 1)}
    for native in fixtures:
        report = native['report']; assert report['observerIndependent'] is True
        state, tags, phase = engine['make'](native['initial']); command = 0
        windows = [entries for field in ('origin', 'source', 'control')
                   if (entries := native[field])]
        checkpoints = {e['command']: e for entries in windows for e in entries}
        pins0 = {name: (native['initial']['state'][name]['keyX'],
                        native['initial']['state'][name]['keyY']) for name in engine['models']}
        keys, end = report['keys'], report['macros']
        boundaries = sorted({0, end, *checkpoints,
            *(index*1120+offset for index in range(len(keys)) for offset in (0, 560, 1120))})
        for following in boundaries:
            if command in checkpoints:
                early['snapshot_matches'](state, phase, checkpoints[command]['state'])
            if following == command: continue
            pins = dict(pins0); index, offset = divmod(command, 1120)
            pins['ik1302'] = key_pins[keys[index]] if index < len(keys) and offset < 560 else (0, 0)
            if following == command+1 and command in checkpoints and following in checkpoints:
                phase, _ = engine['step'](state, tags, phase, pins); command += 1; total += 1
            else:
                # A7F losses are permitted in a negative control; cycle skipping
                # still requires exact ALL5/wires/phase/tags and fixed pins.
                phase, command = early['advance_fixed'](state, tags, phase, command,
                    following, pins, losses=[], label=report['name'])
        assert command == end
        early['snapshot_matches'](state, phase, native['end']['state'])
        assert r['number'](w['ip'](state['ik1302'])) == report['endIp']
        assert [r['number'](state['ik1302'].r[i]) for i in (2, 5)] == report['endMode']
        assert bool(report['finalReady']) == (
            r['number'](state['ik1302'].r[22]) == 7 and
            all(r['number'](state['ik1302'].st[i]) == 0 for i in range(1, 24, 3)))
        assert r['inlet']['match_controller'](state['ik1302'])
        print('PASS ALL5 whole suffix', report['name'], end,
              'all fields/wires/phase/tags; full unobserved mirror; native pins.', flush=True)
    assert total == 708, ('update selected transition count only after auditing windows', total)
    print('PASS', total, 'selected consecutive ALL5 transitions and four full ends; '
          'no reference state setter, native C-signF or partial K2.', flush=True)


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    assignment_inventory(); gate_contract(); reset_exit_contracts()
    fixtures = json.loads(subprocess.check_output([
        'node', str(root / 'cache-reader-mode-origin-native.cjs'), '--proof-input'], text=True))
    origin_contract(fixtures[0], fixtures[1], fixtures[2])
    early = runpy.run_path(str(root / 'cache-input-mask-early-exit.py'))
    validate_native(early, fixtures)
    r['inlet']['immutable_reference']()
    print('PASS reader seed/mode provenance + conflicting gates + four native controls. '
          'A post-read mode rewrite WITH data/return survival is still missing.', flush=True)
