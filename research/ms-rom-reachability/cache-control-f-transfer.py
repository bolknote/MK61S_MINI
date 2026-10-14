#!/usr/bin/env python3
"""Follow a restored R2=F until its FIRST assignment, without state injection.

Complete cached controller plus exact local input-context/R2 constraints.
Positive paths remain conservative candidates, not native key recipes.
The 91 subroutine contracts are detached universal primary-chip proofs.
"""
from collections import Counter, deque
import json
from pathlib import Path
import runpy
import subprocess

from z3 import And, BitVec, Or, UGE, sat, unsat

root = Path(__file__).resolve().parent
r = runpy.run_path(str(root / 'cache-control-f-reserve.py'))
w, q, equal = r['w'], r['q'], r['equal']
graph_model = runpy.run_path(str(root / 'cache-numeric-export-gates.py'))
graph = graph_model['graph']
states, edges = graph_model['states'], graph_model['edges']
fused = graph['metadata']['fusedCommands']
groups = {
    'zero': (0x00, 0x54, 0x76, 0xD0, 0xD1, 0xD8, 0xD9, 0xDF),
    'eight': (0xC3,), 'fifteen': (0x77,),
    'copy_R5': (0x58, 0x78, 0x7F, 0x8B, 0xB9),
    'copy_R1': (0x92, 0x9A), 'copy_S1': (0xB0, 0xF2),
    'toggle': (0xAF, 0xC2, 0xCA, 0xEA),
}
changes = {code: label for label, row in groups.items() for code in row}
assert len(changes) == 23


def words(code):
    return [int(s, 16) for s in fused.get(f'{code:02X}', [f'{code:02X}'])]


def r2_assignment_inventory():
    for code in range(256):
        a = q['State'](f'F_transfer_inventory_{code:02X}')
        b = w['ex'](a, code, *q['arbitrary_keys'](f'F_transfer_keys_{code:02X}'))
        label = changes.get(code, 'preserve')
        expected = {'zero': 0, 'eight': 8, 'fifteen': 15,
                    'copy_R5': a.r[5], 'copy_R1': a.r[1],
                    'copy_S1': a.s1, 'toggle': a.r[2] ^ 8,
                    'preserve': a.r[2]}[label]
        p = w['base'](a, code)
        w['prove'](p, b.r[2] == expected, f'R2 assignment{code:02X}', False)
        if code in changes:
            assert r['possible_difference'](p, b.r[2] == a.r[2])
        if code % 64 == 63:
            print(f'PASS exact R2 assignment inventory through{code:02X}', flush=True)


def context_constraints(a, context):
    code, sp, vector, selector, delta, r38, dr38, r26, types = context
    assert types is None
    result = [w['address'](a) == code,
              *[v == n for v, n in zip(w['stack'](a), sp)]]
    if vector == 'diagonal':
        result.append(a.r[37] == a.r[40])
    elif vector is not None:
        assert isinstance(vector, int)
        result.append(w['byte'](a.r[37], a.r[40]) == vector)
    for value, domain in ((a.s1, selector), (a.r[38], r38), (a.r[26], r26)):
        if domain is not None:
            assert domain
            result.append(Or(*[value == n for n in domain]))
    if delta is not None:
        result.append(a.s1-a.r[35] == delta)
    if dr38 is not None:
        result.append(a.r[38]-a.r[35] == dr38)
    return result


templates = {}
context_cache = {}


def successors_with_f(index):
    if index in context_cache:
        return context_cache[index]
    code = states[index][0]
    if code not in templates:
        a = q['State'](f'F_transfer_context_{code:02X}')
        b = a
        for number, word in enumerate(words(code)):
            assert word not in changes
            b = w['ex'](b, word, *q['arbitrary_keys'](
                f'F_transfer_context_keys_{code:02X}_{number}'))
        p = w['base'](a, code)
        w['prove'](p, b.r[2] == a.r[2], f'fused{code:02X} holds R2', False)
        p.add(a.r[2] == 15)
        assert p.check() == sat
        templates[code] = a, b, p
    a, b, p = templates[code]
    p.push();p.add(*context_constraints(a, states[index]))
    feasible = p.check();assert feasible in (sat, unsat)
    allowed = []
    if feasible == sat:
        for target in edges[index]:
            p.push();p.add(w['address'](b) == states[target][0])
            answer = p.check();p.pop();assert answer in (sat, unsat)
            if answer == sat:
                allowed.append(target)
    p.pop()
    context_cache[index] = allowed
    return allowed


def first_assignment_cut(start_code, refine):
    starts = [i for i, s in enumerate(states) if s[0] == start_code]
    if start_code != 0x35:
        starts = sorted({child for i in starts for child in edges[i]})
    reached = set(starts);todo = deque(starts);parents = dict.fromkeys(starts)
    stops = [];pruned = 0
    while todo:
        i = todo.popleft();sequence = words(states[i][0])
        hit = next((word for word in sequence if word in changes), None)
        if hit is not None:
            stops.append((i, hit))
            continue
        allowed = successors_with_f(i) if refine else edges[i]
        pruned += len(edges[i])-len(allowed)
        for child in allowed:
            if child not in reached:
                reached.add(child);parents[child] = i;todo.append(child)
        if refine and len(context_cache) % 1000 == 0:
            print(f'R2=F context cut{start_code:02X}: '
                  f'{len(reached)} reached, {len(todo)} pending, '
                  f'{len(context_cache)} cached input contexts', flush=True)
    counts = Counter(word for _, word in stops)
    report = {'start': f'{start_code:02X}', 'R2': 'F' if refine else 'untracked',
              'starts': len(starts), 'contexts': len(reached), 'pending': len(todo),
              'prunedEdges': pruned,
              'firstAssignments': {f'{c:02X}': n for c, n in sorted(counts.items())}}
    assert report['pending'] == 0
    if not refine:
        assert (len(starts), len(reached)) == {
            0x35: (806, 4464), 0x58: (175, 18260), 0x8B: (447, 20017)}[start_code]
    else:
        assert (len(starts), len(reached), pruned) == {
            0x35: (806, 4464, 0), 0x58: (175, 4396, 261),
            0x8B: (447, 13371, 546)}[start_code]
        if start_code == 0x58:
            assert counts == {0x7F: 1, 0xD9: 1}
        elif start_code == 0x8B:
            assert counts[0x92] == 53 and counts[0x9A] == 13
    print('COMPLETE first R2-assignment cut:', json.dumps(report), flush=True)
    for sink in (0x92, 0x9A):
        matches = [i for i, word in stops if word == sink]
        if not matches:
            continue
        cursor = matches[0];chain = []
        while cursor is not None:
            chain.append(cursor);cursor = parents[cursor]
        sequence = [word for i in reversed(chain) for word in words(states[i][0])]
        print('CANDIDATE, not native:', f'{sink:02X}',
              ' '.join(f'{word:02X}' for word in sequence), flush=True)
    return report


def rejected_short_routes():
    fixtures = (
        ((0x8B, 0x48, 0xB1, 0xB3, 0xBD, 0x91, 0x92), 5),
        ((0x58, 0x4E, 0x97, 0x99, 0x9B, 0x9C, 0x9E, 0x8C, 0x91, 0x92), 3))
    for sequence, expected_failure in fixtures:
        a = q['State'](f'F_transfer_short_{sequence[0]:02X}')
        p = w['base'](a, sequence[0]);p.add(a.r[5] == 15);b = a
        failure = None
        for index, code in enumerate(sequence):
            p.add(w['address'](b) == code)
            outcome = p.check();assert outcome in (sat, unsat)
            if outcome == unsat:
                failure = index;break
            b = w['ex'](b, code, *q['arbitrary_keys'](
                f'F_transfer_short_keys_{sequence[0]:02X}_{index}'))
        assert failure == expected_failure
        print('PASS rejected only this F-restoration path at',
              f'{sequence[failure]:02X}', ' '.join(f'{c:02X}' for c in sequence), flush=True)
    a = q['State']('F_transfer_97');p = w['base'](a, 0x97);p.add(a.r[2] == 15)
    b = w['ex'](a, 0x97, *q['arbitrary_keys']('F_transfer_97_keys'))
    w['prove'](p, w['address'](b) == 0x63,
               '97 with R2=F always enters63, not99, arbitrary keys/pages')


def middle_st_copy():
    sequence = (0x91, 0x92, 0x93, 0x94, 0x95, 0x98, 0x9A,
                0x93, 0x94, 0x95, 0x98, 0x9A)
    a = q['State']('F_transfer_91');p = w['base'](a, 0x91)
    c = a.copy();c.r[2] = BitVec('F_transfer_91_otherR2', 4)
    pair = (a, c)
    for index, code in enumerate(sequence):
        pins = q['arbitrary_keys'](f'F_transfer_91_keys{index}')
        serial = q['State'](f'F_transfer_91_serial{index}').m
        fresh = []
        for before in pair:
            w['prove'](p, w['address'](before) == code, f'91 forces{code:02X}', False)
            out = [];after = w['ex'](before, code, *pins,
                                    serial_inputs=serial, emitted_outputs=out)
            w['prove'](p, equal(out, before.m), f'91/{code:02X} no outgoing write', False)
            fresh.append(after)
        pair = fresh
    b, d = pair
    w['prove'](p, equal(b.r[0:36:3], a.r[0:36:3]),
               'full91 double call preserves ALL12 original A fields')
    w['prove'](p, And(*[b.st[1+3*i] == a.r[2+3*i] for i in (0, 1, 7)]),
               'full91 double call saves oldC0/C1/C7 in middle ST[1/4/22], '
               'not numeric signST25')
    p.add(UGE(a.r[2], 5), UGE(c.r[2], 5))
    w['prove'](p, And(equal(b.r, d.r), equal(b.m, d.m),
                     *[b.st[i] == d.st[i] for i in range(42) if i != 1],
                     *[getattr(b, n) == getattr(d, n)
                       for n in ('s', 's1', 'l', 't', 'carry')]),
               'full91 retains high oldR2 ONLY in ST1, not controlR2, '
               'other primary fields or outgoing ring')
    print('LIMIT: this middle-ST reserve is conditional on a legal91 entry. '
          'It is not a native F constructor, a signF writer or partial K2. '
          'Other source copies, changes after the first R2 assignment, '
          'encoded sources and later middle-ST extraction remain open.', flush=True)


def native_input_mask():
    data = json.loads(subprocess.check_output([
        'node', str(root / 'cache-control-f-transfer-native.cjs'), '--proof-input'], text=True))
    assert data['report']['observerIndependent'] is True
    entries = data['prefix']
    engine = runpy.run_path(str(root / 'cache-stack-lift-ring.py'))
    state, tags, phase = engine['make'](entries[0])
    for entry, following in zip(entries, entries[1:]):
        assert engine['boundary_ip'](state['ik1302']) == entry['ip']
        pins = {name: (entry['state'][name]['keyX'], entry['state'][name]['keyY'])
                for name in engine['models']}
        phase, _ = engine['step'](state, tags, phase, pins)
        for name in engine['names']:
            expected = following['state'][name]
            for field in ('input', 'output'):
                assert w['number'](state['_wire'][name][field]) == expected[field], (name, field)
            if name.startswith('ir'):
                assert [w['number'](v) for v in state[name]] == expected['m'], name
                assert phase == expected['tick']
            else:
                for field in ('r', 'm', 'st'):
                    assert [w['number'](v) for v in getattr(state[name], field)] == expected[field], (name, field)
                for field in ('s', 's1', 'l', 't', 'carry'):
                    assert w['number'](getattr(state[name], field)) == expected[field], (name, field)
    assert len(entries)-1 == 60
    print('PASS native digit1 mask: ALL60 consecutive full-five-chip '
          'transitions/wires/IRphase matched through the actual E7(X); '
          'fresh unobserved ALL5 mirror and program/Ms/15 ordinary words held.', flush=True)
    # This identity does not dispatch the native F6 state to D4. Native A7=F
    # supplies only a payload condition; the real source remains inside input.
    a = q['State']('F_input_D4_feed');p = w['base'](a, 0xD4);p.add(a.r[21] == 15)
    out = [];w['ex'](a, 0xD4, *q['arbitrary_keys']('F_input_D4_feed_keys'), emitted_outputs=out)
    w['prove'](p, out[24] == 15,
               'CONDITIONAL D4 with A7=F writes numeric M1 signF; '
               'native input reaches that payload position, NOT that dispatch')
    print('SCOPE: ordinary digit input provides a real early A-maskF and '
          'later A7=F without Ms preparation. Its actual E7 writes only1/sign0. '
          'No native D4/C-signF, cache-preserving joint preparation or partial K2.', flush=True)


def input_mask_exit_contracts():
    a = q['State']('input_mask_F4_gate');p = w['base'](a, 0xF4)
    out = [];b = w['ex'](a, 0xF4, *q['arbitrary_keys']('input_mask_F4_gate_keys'),
                        emitted_outputs=out)
    w['prove'](p, And((w['address'](b) == 0xEA) == (a.r[23] == 0),
                     Or(w['address'](b) == 0xEA, w['address'](b) == 0xF6),
                     equal(out, a.m)),
               'F4 exitsEA iff R23=0, elseF6; no outgoing write, arbitrary keys/pages')
    a = q['State']('input_mask_F6_feed');p = w['base'](a, 0xF6)
    p.add(a.r[21] == 15, a.r[24] == 1)
    b = a
    for code in (0xF6, 0xF4):
        w['prove'](p, w['address'](b) == code, f'input-mask forces{code:02X}', False)
        out = [];before = b
        b = w['ex'](b, code, *q['arbitrary_keys'](f'input_mask_feed_keys{code:02X}'),
                    emitted_outputs=out)
        w['prove'](p, equal(out, before.m), f'input-mask {code:02X} no outgoing write', False)
    w['prove'](p, b.r[21] == 1,
               'native-shaped F6/F4 with A7=F/A8=1 replaces D4 sign feed by1 '
               'before any writer; arbitrary other fields/keys/pages')
    print('LIMIT: this excludes only direct interception from that F6 entry. '
          'Other F copies remain. The earlier F4->EA exit would require R23=0 '
          'already at the first F4, not its native F; payload/destination/exit '
          'must still be verified, no native counter repair is asserted.', flush=True)


if __name__ == '__main__':
    r2_assignment_inventory()
    for code in (0x35, 0x58, 0x8B):
        first_assignment_cut(code, refine=False)
        first_assignment_cut(code, refine=True)
    rejected_short_routes()
    middle_st_copy()
    native_input_mask()
    input_mask_exit_contracts()
