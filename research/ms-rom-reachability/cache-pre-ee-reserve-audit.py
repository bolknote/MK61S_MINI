#!/usr/bin/env python3
"""Source-driven reserve candidates before the first EE of the P9 reader.

The controller cache is complete, but token transport is an incomplete cover
of universal exact copies. A candidate is not a keyboard recipe; a closed
negative is not an exclusion of arithmetic/encoded reserves or other readers.
Only exact UNSAT suffixes (arbitrary entry), or raw-free fixed-metadata entry
prefixes, may remove paths. No emulator state or ROM is modified.
"""
from collections import Counter, deque
from pathlib import Path
import runpy
import sys

from z3 import And, sat, unsat

root = Path(__file__).resolve().parent
entry = runpy.run_path(str(root / 'cache-e4-entry-audit.py'))
states, edges, q = (entry[name] for name in ('states', 'edges', 'q'))
State, ex, base, keys = (q[name] for name in
                       ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))
w = runpy.run_path(str(root / 'cache46-writer-contracts.py'))
compiler = runpy.run_path(str(root / 'analyze_k1_buffers.py'))
checker = entry['checker']
raw = (0, 3, 9, 12, 18, 21)
native = entry['native']['readerInitial']


def inventory():
    hits = []
    for code in range(256):
        a = State(f'pre_ee_reserve_inventory_{code:02X}')
        out = []
        b = ex(a, code, *keys(f'pre_ee_reserve_inventory_keys_{code:02X}'),
               emitted_outputs=out)
        p = base(a, code)
        for lane in range(3):
            claim = w['eq'](b.st[lane:36:3], w['A'](a))
            p.push(); p.add(~claim)
            answer = p.check(); p.pop()
            assert answer in (sat, unsat), p.reason_unknown()
            if answer == unsat:
                w['prove'](p, And(claim, w['eq'](w['A'](b), w['A'](a)),
                                  w['eq'](out, a.m)),
                           f'{code:02X}: exact A12 copy into ST lane{lane}, A and ring held')
                hits.append((code, lane))
    assert hits == [(0x40, 0), (0x93, 0)], hits
    print('PASS: all256 words; only40/93 make a universal full A12-to-ST copy.', flush=True)


def constraints(a):
    # Six raw tetras and ALL serial/scalar inputs are free. The non-raw R/ST
    # metadata describes the current reader entry, not every possible reader.
    return [getattr(a, group)[j] == value
            for group in ('r', 'st')
            for j, value in enumerate(native[group])
            if group != 'r' or j not in raw + (29, 32)]


def wait_contract():
    a = State('pre_ee_reserve_wait35')
    b = ex(a, 0x35, *keys('pre_ee_reserve_wait35_keys'))
    p = base(a, 0x35)
    p.add(w['ip'](b) == 0x35)
    w['prove'](p, And(w['eq'](b.st, a.st),
                      *[b.r[j] == a.r[j] for j in range(42)
                        if j not in (29, 32)]),
               '35 self branch holds R except29/32 and whole ST; leading waits preserve entry class')


def expanded(path):
    answer = []
    for index in path:
        code = states[index][0]
        answer.append(code)
        if code == 0x93:
            answer.append(0x94)
        elif code == 0x12:
            answer.append(0xC6)
    return answer


def find(copies, blocked=(), limit=500000):
    # 100 marks the fixed-metadata entry, distinguishing a prefix exclusion
    # from an arbitrary-state suffix exclusion.
    patterns = set(tuple(p) for p in blocked)
    prefixes = {()}
    for pattern in patterns:
        prefixes.update(pattern[:j] for j in range(1, len(pattern)))

    def advance(history, code):
        if history == (0x100, 0x35) and code == 0x35:
            return history
        value = history + (code,)
        if any(len(p) <= len(value) and value[-len(p):] == p for p in patterns):
            return None
        return max((p for p in prefixes if not p or value[-len(p):] == p), key=len)

    tokens = bytearray(86)
    for token, pos in enumerate(raw, 1):
        tokens[pos] = token
    starts = [(j, bytes(tokens), advance(advance((), 0x100), 0x35))
              for j, st in enumerate(states) if entry['compatible'](st, native)]
    assert len(starts) == 4
    parents = dict.fromkeys(starts)
    queue = deque(starts)
    losses = Counter()
    terminal = None
    while queue and len(parents) < limit:
        item = queue.popleft()
        index, payload, history = item
        code = states[index][0]
        following = compiler['transport'](copies[code], payload)
        if code == 0xEE:
            if all(t in following[:86] for t in range(1, 7)):
                terminal = item
                break
            losses[code] += 1
            continue
        # A transient A/B/C permutation is NOT a reserve. Demand either a
        # complete ST copy, two disjoint internal copies, or an export. These
        # remain waypoints, not a path to E4 or a physical destination.
        outside_a = bytes(v for j, v in enumerate(following[:86])
                          if j >= 36 or j % 3 != 0)
        outgoing = following[86:]
        in_a = following[:36:3]
        if (all(t in following[42:78] for t in range(1, 7)) or
            (all(t in in_a for t in range(1, 7)) and
             all(t in outside_a for t in range(1, 7))) or
            all(t in outgoing for t in range(1, 7))):
            terminal = item
            break
        if code == 0xC9:
            losses[code] += 1
            continue
        internal = following[:86]
        if not all(t in internal for t in range(1, 7)):
            losses[code] += 1
            continue
        for nxt in edges[index]:
            next_history = advance(history, states[nxt][0])
            if next_history is None:
                continue
            value = (nxt, internal, next_history)
            if value not in parents:
                parents[value] = item
                queue.append(value)
    path = []
    cursor = terminal
    while cursor is not None:
        path.append(cursor[0]); cursor = parents[cursor]
    path.reverse()
    print('COPY-RESERVE COVER:', len(parents), 'visited;', len(queue), 'pending;',
          'candidate', terminal is not None, '; losses',
          [(f'{code:02X}', n) for code, n in losses.most_common(12)], flush=True)
    return expanded(path), not queue and terminal is None


def compress(sequence):
    answer = []
    for code in sequence:
        if answer and (answer[-1], code) in ((0x93, 0x94), (0x12, 0xC6)):
            continue
        answer.append(code)
    return answer


def main():
    inventory()
    wait_contract()
    copies = compiler['compile_copies']({'q': q})
    # These are universal exact controller lemmas, not merely historical
    # rejected examples. Verify them again before using them as cuts.
    blocked = []
    for text in ('35 45 8B 48 B1', '35 B5 83 45 8B 48 B1',
                 '35 B5 B7 45 8B 48 B1', '7A 7C 75'):
        seq = tuple(int(v, 16) for v in text.split())
        assert checker['verify_sequence'](seq)['result'] == unsat
        blocked.append(seq)
    decoder = tuple(int(v, 16) for v in
                    '35 C5 8A 65 7B B7 45 8B 48 B1 B3'.split())
    for seq, allowed in ((decoder, (0xB8, 0xB9)),
                         (decoder + (0xB9, 0xF8, 0xFA, 0x7A, 0x7C),
                          (0x76, 0x77, 0x78, 0x79))):
        result = checker['verify_sequence'](seq)
        assert result['result'] == sat
        claim = q['Or'](*[w['ip'](result['final']) == c for c in allowed])
        w['prove'](result['solver'], claim,
                   'decoder universal successors ' + '/'.join(f'{c:02X}' for c in allowed))
        blocked.extend(seq + (c,) for c in range(256) if c not in allowed)
    rejected = 0
    outcome = 'bounded'
    for attempt in range(24):
        sequence, closed = find(copies, blocked)
        if not sequence:
            outcome = 'closed-copy-cover' if closed else 'bounded'
            print('CLOSED copy cover' if closed else 'BOUNDED copy cover', flush=True)
            break
        print('CANDIDATE only:', ' '.join(f'{code:02X}' for code in sequence), flush=True)
        # Include the outgoing edge of the last command as forced by the
        # graph when possible; preservation itself is checked separately.
        result = checker['verify_sequence'](sequence, constraints=constraints)
        if result['result'] != unsat:
            outcome = 'candidate-needs-data-and-ring-proof'
            print('LIMIT: SAT needs exact reserve survival and full-ring keys.', flush=True)
            break
        rejected += 1
        bad = sequence[:result['index']+1]
        suffix = None
        for start in range(max(0, len(bad)-8), len(bad)-1):
            piece = bad[start:]
            if checker['verify_sequence'](piece)['result'] == unsat:
                suffix = piece
        if suffix is None:
            blocked.append((0x100,) + tuple(compress(bad)))
            print('EXCLUDED fixed-metadata raw-free prefix:',
                  ' '.join(f'{code:02X}' for code in bad), flush=True)
        else:
            blocked.append(tuple(compress(suffix)))
            print('EXCLUDED universal suffix:',
                  ' '.join(f'{code:02X}' for code in suffix), flush=True)
    print('RESULT:', outcome, '; exact rejected candidates', rejected,
          '; refinement budget24. Not a universal reserve exclusion.', flush=True)
    print('LIMIT: only universal copies in this metadata entry are covered; '
          'encoded/conditional reserves, earlier preparation, other chips, '
          'program re-reads and different readers remain open.', flush=True)


if __name__ == '__main__':
    if '--inventory-only' in sys.argv:
        inventory()
        wait_contract()
    else:
        main()
