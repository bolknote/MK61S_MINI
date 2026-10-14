#!/usr/bin/env python3
"""Candidates for preserving the three raw program bytes after scanner 35.

This uses the COMPLETE C8-inclusive reset controller cache, not the older
pre-C8 graph. It is still only a candidate generator: individual field-copy
classification is deliberately incomplete, the external ring is not a payload
reserve, and controller correlations may produce spurious paths. Exhaustion
does not prove that partial K2 or a different reader is impossible.
"""
from collections import Counter, deque
import gzip
import json
from pathlib import Path
import runpy
import subprocess

root = Path(__file__).resolve().parent
audit = runpy.run_path(str(root / 'k1-formatter-entry-audit.py'))
with gzip.open(audit['cache_path'], 'rt', encoding='utf8') as stream:
    graph = json.load(stream)
assert graph['metadata']['sourceSha256'] == audit['fingerprints']()
assert graph['metadata']['complete'] and not graph['metadata']['pending']
assert graph['metadata']['terminal'] is None
states, edges = graph['states'], graph['successors']
assert len(states) == len(edges) == len(graph['parents'])

q = runpy.run_path(str(root / 'ik1302_symbolic.py'))
compiler = runpy.run_path(str(root / 'analyze_k1_buffers.py'))
copies = compiler['compile_copies']({'q': q})
transport = compiler['transport']

native = json.loads(subprocess.check_output([
    'node', '-e',
    "const {capture}=require('./check_partial_k2_program_scan.cjs');"
    "console.log(JSON.stringify(capture().state.ik1302));"
], cwd=root, text=True))
assert native['r'][36] + 16*native['r'][39] == 0x35


def compatible(st):
    ip, sp, vector, selector, delta, r38, dr38, r26, types = st
    a = native
    address_stack = [a['st'][36+i] + 16*a['st'][39+i] for i in range(3)]
    if ip != 0x35 or list(sp) != address_stack:
        return False
    av = a['r'][37] + 16*a['r'][40]
    if vector == 'diagonal' and a['r'][37] != a['r'][40]:
        return False
    if isinstance(vector, int) and vector != av:
        return False
    if selector is not None and a['s1'] not in selector:
        return False
    if delta is not None and delta != (a['s1'] - a['r'][35]) % 16:
        return False
    if r38 is not None and a['r'][38] not in r38:
        return False
    if dr38 is not None and dr38 != (a['r'][38] - a['r'][35]) % 16:
        return False
    if r26 is not None and a['r'][26] not in r26:
        return False
    assert types is None, 'the cached graph does not track independent type fields'
    return True


def find_candidate(blocked=(), blocked_prefixes=(), blocked_patterns=(), limit=500000):
    # Six opaque tetra tokens, NOT the test values 04/05/06. F separators
    # do not carry payload and are not counted as three further bytes.
    payload = bytearray(86)
    for token, pos in enumerate((0, 3, 9, 12, 18, 21), 1):
        payload[pos] = token
    patterns = {tuple(seq) for seq in blocked_patterns}
    patterns.update((0x100,) + tuple(seq) for seq in blocked_prefixes)
    prefixes = {()}
    for pattern in patterns:
        prefixes.update(pattern[:i] for i in range(1, len(pattern)))

    def advance(history, ip):
        extended = history + (ip,)
        if any(len(p) <= len(extended) and extended[-len(p):] == p for p in patterns):
            return None
        return max((p for p in prefixes if not p or extended[-len(p):] == p), key=len)

    starts = [(i, bytes(payload), advance(advance((), 0x100), 0x35))
              for i, st in enumerate(states) if compatible(st)]
    assert starts, 'no compatible cached context; do not substitute a different entry'
    parents = {v: None for v in starts}
    queue = deque(starts)
    terminal = None
    dropped = Counter()
    while queue and len(parents) < limit:
        item = queue.popleft()
        index, before, history = item
        ip = states[index][0]
        following = transport(copies[ip], before)
        # A numeric write is a waypoint only: it is NOT an exchange, nor
        # necessarily aligned with a hidden Ms page. Program M3 is excluded.
        numeric_out = following[86:122:3] + following[87:123:3]
        if all(token in numeric_out for token in range(1, 7)):
            terminal = item
            break
        internal = following[:86]
        if not all(token in internal for token in range(1, 7)):
            dropped[ip] += 1
            continue
        for next_index in edges[index]:
            next_ip = states[next_index][0]
            if (ip, next_ip) in blocked:
                continue
            next_history = advance(history, next_ip)
            if next_history is None:
                continue
            nxt = (next_index, internal, next_history)
            if nxt not in parents:
                parents[nxt] = item
                queue.append(nxt)
    path = []
    item = terminal
    while item is not None:
        path.append(item)
        item = parents[item]
    path.reverse()
    print('Cache transport:', len(starts), 'native-compatible contexts;',
          len(parents), 'visited;', len(queue), 'pending;',
          'candidate=', terminal is not None, flush=True)
    print('Copy-losing frontiers:', [(f'{ip:02X}', n)
                                   for ip, n in dropped.most_common(12)], flush=True)
    if path:
        sequence = []
        for index, _, _ in path:
            ip = states[index][0]
            sequence.append(ip)
            if ip == 0x93:
                sequence.append(0x94)
            if ip == 0x12:
                sequence.append(0xC6)
        print('CANDIDATE, not native:', ' '.join(f'{ip:02X}' for ip in sequence), flush=True)
    else:
        print('LIMIT: no copy-only candidate here; no partial-K2 exclusion follows.', flush=True)
    return path


if __name__ == '__main__':
    import sys
    if '--refine' not in sys.argv:
        find_candidate()
    else:
        checker = runpy.run_path(str(root / 'verify_c8_recovery_candidate.py'),
                                init_globals={'transport': {'q': q}})
        excluded = []
        universal = [
            [0x35, 0x45, 0x8B, 0x48, 0xB1],
            [0x35, 0xB5, 0x83, 0x45, 0x8B, 0x48, 0xB1],
            [0x35, 0xB5, 0xB7, 0x45, 0x8B, 0x48, 0xB1],
            [0x7A, 0x7C, 0x75],
        ]
        for sequence in universal:
            assert checker['verify_sequence'](sequence)['result'] == q['unsat']
        for attempt in range(12):
            print('REFINEMENT', attempt+1, flush=True)
            path = find_candidate(blocked_prefixes=excluded, blocked_patterns=universal)
            if not path:
                break
            sequence = []
            for index, _, _ in path:
                ip = states[index][0]
                sequence.append(ip)
                if ip == 0x93:
                    sequence.append(0x94)
                if ip == 0x12:
                    sequence.append(0xC6)
            result = checker['verify_sequence'](sequence, native)
            if result['result'] != q['unsat']:
                print('LIMIT: exact candidate still needs a full-ring native protocol.', flush=True)
                break
            bad = sequence[:result['index']+1]
            # Try a short impossible suffix first. Unlike a bounded number
            # of rejected 35 waits, a universal suffix covers ANY number.
            generic_bad = None
            for start in range(max(0, len(bad)-8), len(bad)-1):
                suffix = bad[start:]
                if checker['verify_sequence'](suffix)['result'] == q['unsat']:
                    generic_bad = suffix
            if generic_bad is not None:
                universal.append(generic_bad)
                print('EXCLUDED universal ROM suffix:',
                      ' '.join(f'{ip:02X}' for ip in generic_bad), flush=True)
                continue
            compressed = []
            for ip in bad:
                if compressed and (compressed[-1], ip) in ((0x93, 0x94), (0x12, 0xC6)):
                    continue
                compressed.append(ip)
            excluded.append(compressed)
            print('EXCLUDED only this native prefix:',
                  ' '.join(f'{ip:02X}' for ip in compressed), flush=True)
