#!/usr/bin/env python3
"""Source-based post-reader mode repair: destructive tails and guarded cuts.

The stock reference/ROM and six frozen audit sources are read-only. Paired
primary proofs share arbitrary future keys/serial pages; they do NOT erase
earlier correlated reserves or the original program in the physical ring.
The complete controller graph overapproximates reset execution. A positive
product path is only a candidate, never a keyboard recipe.
"""
from collections import Counter, deque
import json
from pathlib import Path
import runpy
import subprocess

from z3 import And, BitVec, If, Or, UGE, ULE, sat, unsat

root = Path(__file__).resolve().parent
origin = runpy.run_path(str(root / 'cache-reader-mode-origin.py'))
r, w, q = origin['r'], origin['w'], origin['q']
states, edges = r['states'], r['edges']
raw = w['raw']
unsafe_expected = tuple(int(code, 16) for code in (
    '00 08 0B 0C 0D 0E 12 13 16 20 22 24 26 30 3A 3B 3C 3D 3E 3F '
    '40 43 44 47 49 57 60 61 62 6A 6B 6E 6F 88 91 92 93 94 95 '
    '98 9A A6 A8 BB C3 C4 C6 C7 C8 C9 CF D2 D6 D7 D8 DD DF E1 '
    'E4 E7 EB EC EE F6 F7 FE').split())


def same(a, b):
    return And(*[w['eq'](getattr(a, n), getattr(b, n)) for n in ('r', 'st', 'm')],
               *[getattr(a, n) == getattr(b, n)
                 for n in ('s', 's1', 'l', 't', 'carry')])


def same_except_a0(a, b):
    return And(*[a.r[j] == b.r[j] for j in range(42) if j != 0],
               w['eq'](a.st, b.st), w['eq'](a.m, b.m),
               *[getattr(a, n) == getattr(b, n)
                 for n in ('s', 's1', 'l', 't', 'carry')])


def paired_path(sequence, name, *, marker=False, forced=False):
    a = q['State'](name); other = a.copy()
    other.r[0] = BitVec(name+'_independent_A0', 4)
    p = w['base'](a, sequence[0]); b, c = a, other
    for index, code in enumerate(sequence):
        if forced:
            w['prove'](p, And(w['ip'](b) == code, w['ip'](c) == code),
                       name+' forced next address', False)
        p.add(w['ip'](b) == code, w['ip'](c) == code)
        if marker and code == 0xE5: p.add(b.m[22] == 15)
        assert p.check() == sat, ('empty paired path', name, index)
        before_b, before_c = b, c
        pins = q['arbitrary_keys'](f'{name}_keys{index}')
        serial = q['State'](f'{name}_future{index}').m
        ob, oc = [], []
        b = w['ex'](b, code, *pins, serial_inputs=serial, emitted_outputs=ob)
        c = w['ex'](c, code, *pins, serial_inputs=serial, emitted_outputs=oc)
        w['prove'](p, And(w['eq'](ob, before_b.m), w['eq'](oc, before_c.m),
                         w['eq'](ob, oc)), name+' equal outputs / no ring write', False)
    w['prove'](p, same(b, c), name+' forgets independent incoming A0 in ALL primary fields/output')
    p.push(); p.add(a.r[0] != other.r[0]); assert p.check() == sat; p.pop()
    return a, b, p


def forced_tail_loss():
    for code, exits in ((0xD0, (0xF2, 0xF3)), (0xD9, (0xF3,)),
                        (0xF2, (0xF3,)), (0xF3, (0xF5, 0xF7)),
                        (0xF5, (0xF6,))):
        a = q['State'](f'reset_tail_gate_{code:02X}'); p = w['base'](a, code)
        b = w['ex'](a, code, *q['arbitrary_keys'](f'reset_tail_gate_keys_{code:02X}'))
        w['prove'](p, Or(*[w['ip'](b) == v for v in exits]),
                   f'{code:02X} complete forced-exit set '+','.join(f'{v:02X}' for v in exits))
    a = q['State']('reset_tail_F3_exact'); p = w['base'](a, 0xF3)
    b = w['ex'](a, 0xF3, *q['arbitrary_keys']('reset_tail_F3_exact_keys'))
    w['prove'](p, w['ip'](b) == If(a.r[23]+a.r[26]+1 == 0,
        q['BitVecVal'](0xF5, 8), q['BitVecVal'](0xF7, 8)),
        'F3 choosesF5 iff modulo16(R23+R26+1)=0; otherwiseF7')
    # Local paired operators make arbitrary finite future paths irrelevant:
    # neither precursor observes/copies old A0, and the FIRST shift loses it.
    for code in (0xD0, 0xD9, 0xF2, 0xF3, 0xF5, 0xF6, 0xF7):
        a = q['State'](f'reset_tail_pair_{code:02X}'); other = a.copy()
        other.r[0] = BitVec(f'reset_tail_other_{code:02X}', 4)
        p = w['base'](a, code)
        pins = q['arbitrary_keys'](f'reset_tail_pair_keys_{code:02X}')
        serial = q['State'](f'reset_tail_pair_future_{code:02X}').m
        ob, oc = [], []
        b = w['ex'](a, code, *pins, serial_inputs=serial, emitted_outputs=ob)
        c = w['ex'](other, code, *pins, serial_inputs=serial, emitted_outputs=oc)
        claim = same(b, c) if code in (0xF6, 0xF7) else And(
            same_except_a0(b, c), b.r[0] == a.r[0], c.r[0] == other.r[0])
        w['prove'](p, And(claim, w['eq'](ob, a.m), w['eq'](oc, other.m)),
            f'{code:02X} '+('forgets oldA0 entirely' if code in (0xF6, 0xF7)
                           else 'holds A0 only atR0; no new copy or control dependence'))
    cases = [(head, *prelude, *end) for head, preludes in (
        (0xD0, ((), (0xF2,))), (0xD9, ((),)))
        for prelude in preludes for end in ((0xF3, 0xF7), (0xF3, 0xF5, 0xF6))]
    assert len(cases) == 6 and max(map(len, cases)) == 5
    for j, sequence in enumerate(cases): paired_path(sequence, f'reset_tail_case{j}')
    # D1's double restore is not itself an eraser. Its compulsory D2 is.
    sequence = (0xD1, *r['double'], 0xD2)
    assert len(sequence) == 14
    paired_path(sequence, 'reset_D1_double_then_D2', forced=True)
    # 76 similarly zeroes mode locally, but reads a new number before idle.
    sequence = (0x76, 0xE2, 0xE5, 0xE6, 0xED, 0xEE)
    paired_path(sequence, 'reset_76_first_EE', marker=True, forced=True)
    a = q['State']('reset_76_wait'); p = w['base'](a, 0xE5)
    b = w['ex'](a, 0xE5, *q['arbitrary_keys']('reset_76_wait_keys'))
    w['prove'](p, And(w['eq'](b.st, a.st),
        *[b.r[j] == a.r[j] for j in range(42) if j not in (36, 39)]),
        'any finite E5 repeats beforeEE preserve the same soleA0 difference')
    print('PASS: direct D0/D9 reset tails forget oldA0 within at most5 words; '
          'D1 does so at compulsoryD2 after14 words;76 at firstEE. No word '
          'before the loss writes a new outgoing copy. Earlier/encoded reserves '
          'and physical program copies remain OPEN.', flush=True)


def holder_inventory():
    safe, unsafe = set(), []
    for code in range(256):
        a = q['State'](f'reset_hold_{code:02X}'); p = w['base'](a, code)
        p.add(r['ready'](a)); assert p.check() == sat
        b = w['ex'](a, code, *q['arbitrary_keys'](f'reset_hold_keys_{code:02X}'))
        p.add(~And(r['ready'](b), *[b.r[j] == a.r[j] for j in raw]))
        answer = p.check(); assert answer in (sat, unsat)
        if answer == unsat: safe.add(code)
        else: unsafe.append(code)
    assert tuple(unsafe) == unsafe_expected and len(safe) == 190
    print('PASS ALL256:190 universally hold raw6 AND B7=7/zeroST1;66 may '
          'change one. The cut stops BEFORE a nonholder. Particular data, '
          'permutations, encoded/earlier reserves and later recovery are NOT excluded.', flush=True)
    return safe


def b3_provenance():
    parents = Counter(states[i][0] for i, row in enumerate(edges)
                      for child in row if states[child][0] == 0xB3)
    assert parents == {0xB1: 149, 0xB3: 30}
    assert states[0][0] != 0xB3
    a = q['State']('reset_B1_gate'); p = w['base'](a, 0xB1)
    b = w['ex'](a, 0xB1, *q['arbitrary_keys']('reset_B1_gate_keys'))
    w['prove'](p, And(w['ip'](b) == If(UGE(a.r[29], 8),
        q['BitVecVal'](0xB3, 8), q['BitVecVal'](0xB2, 8)), b.r[29] == a.r[29]),
        'B1 reachesB3 iff oldR29>=8, and holdsR29')
    a = q['State']('reset_B3_gate'); p = w['base'](a, 0xB3)
    b = w['ex'](a, 0xB3, *q['arbitrary_keys']('reset_B3_gate_keys'))
    w['prove'](p, And(w['ip'](b) == (q['BitVecVal'](0xB0, 8) | q['ZeroExt'](4, a.r[29])),
                         b.r[29] == a.r[29], b.s1 == a.r[29]),
        'B3 dispatchesB0|R29 and holdsR29')
    p.add(UGE(a.r[29], 8))
    w['prove'](p, And(UGE(w['ip'](b), 0xB8), ULE(w['ip'](b), 0xBF)),
        'reset B3 provenance: onlyB8..BF; graph B3→B0..B7/self edges are spurious')
    print('PASS complete reset graph: only149 B1 and30 self incomingB3 '
          'edges. Since reset is notB3, induction forcesR29>=8 there. This '
          'guards edge use WITHOUT editing/rebuilding the frozen graph.', flush=True)


def operand_dispatch_provenance():
    parents = Counter(states[i][0] for i, row in enumerate(edges)
                      for child in row if states[child][0] == 0x5F)
    assert parents == {0x59: 127, 0x5C: 220, 0x5F: 156}
    assert states[0][0] != 0x5F
    for code in (0x59, 0x5C, 0x5F):
        a = q['State'](f'reset_operand_{code:02X}'); p = w['base'](a, code)
        out = []; b = w['ex'](a, code, *q['arbitrary_keys'](
            f'reset_operand_keys_{code:02X}'), emitted_outputs=out)
        if code == 0x5F:
            w['prove'](p, And(w['ip'](b) == (
                q['BitVecVal'](0x50, 8) | q['ZeroExt'](4, a.r[29])),
                b.r[29] == a.r[29], w['eq'](out, a.m)),
                '5F dispatches50|R29, holdsR29 and writes nothing')
            p.add(w['ip'](b) == 0x5F)
            w['prove'](p, And(a.r[29] == 15, b.r[29] == 15),
                '5F self-edge fixesR29=F forever, independent of all future keys/serial')
        else:
            p.add(w['ip'](b) == 0x5F)
            permitted = (15,) if code == 0x5C else (5, 7, 13, 15)
            w['prove'](p, Or(*[b.r[29] == v for v in permitted]),
                f'{code:02X}→5F exact outgoingR29 domain '+','.join(f'{v:X}' for v in permitted))
    print('PASS complete reset incoming5F/induction: R29 only5/7/D/F; '
          'next55/57/5D/5F, never54/56. Self5F is a real closed control '
          'loop, NOT a chance to choose a new operand on another iteration.', flush=True)


def b9_repair_branches():
    # A real prefix must carry its own type/count correlations. Checking a
    # single abstract edge7C→7F misses this necessary six-word relationship.
    a = q['State']('reset_B9_prefix'); p = w['base'](a, 0xB3)
    p.add(a.r[29] == 9, a.r[2] == 5, a.r[5] == 0); b = a
    for index, code in enumerate((0xB3, 0xB9, 0xF8, 0xFA, 0x7A, 0x7C)):
        p.add(w['ip'](b) == code)
        b = w['ex'](b, code, *q['arbitrary_keys'](f'reset_B9_prefix_keys{index}'))
    w['prove'](p, And(UGE(w['ip'](b), 0x76), ULE(w['ip'](b), 0x79),
                      b.r[35] == 9, b.r[2] == 0, b.r[5] == 5),
        'conditional B3/9 B9 F8 FA 7A 7C: only76..79/type9/mode(0,5); not7D/7F')
    for target in range(0x76, 0x7A):
        p.push(); p.add(w['ip'](b) == target); assert p.check() == sat; p.pop()
    a = q['State']('reset_78_pair'); p = w['base'](a, 0x78); b = a
    for index, code in enumerate((0x78, 0x7F)):
        w['prove'](p, w['ip'](b) == code, '78 suffix forced', False)
        before = b; out = []
        b = w['ex'](b, code, *q['arbitrary_keys'](f'reset_78_keys{index}'), emitted_outputs=out)
        w['prove'](p, w['eq'](out, before.m), '78 suffix no outgoing write', False)
    w['prove'](p, And(w['ip'](b) == 0x33, b.r[2] == a.r[2], b.r[5] == a.r[5]),
        '78/7F double swap restores original mode pair, NOT a lasting reset')
    a = q['State']('reset_79_exit'); p = w['base'](a, 0x79); out = []
    b = w['ex'](a, 0x79, *q['arbitrary_keys']('reset_79_keys'), emitted_outputs=out)
    w['prove'](p, And(w['ip'](b) == 0x45,
        w['eq'](b.r[0:36:3], a.r[0:36:3]), w['eq'](b.r[1:36:3], a.r[1:36:3]),
        w['eq'](b.st[:36], a.st[:36]), b.r[2] == a.r[2], b.r[5] == a.r[5],
        w['eq'](out, a.m)),
        '79 holds ALL A12/B12/numericST/mode pair; forces45; no outgoing write')
    print('SOURCE branch79→45→8B→48 is NOT an idle return or a promise '
          'that a new key can be chosen between words. The separate native '
          'F/В↑ control audits its actual decoder continuation/return limit.', flush=True)


def native_entry():
    # Fresh keyboard preparation and a fresh completely unobserved mirror.
    # Only read-only snapshots are used; no calculator state is imported.
    code = """
const assert=require('node:assert/strict');
const a=require('./tmp/ms-rom-reachability/cache-reader-mode-origin-native.cjs');
const s=require('./tmp/ms-rom-reachability/probe_c8_pc_reader.cjs');
const first=s.machineSnapshot(a.prepare(a.specs[2]));
const plain=s.machineSnapshot(a.prepare(a.specs[2]));
assert.deepEqual(first,plain,'fresh unobserved whole-five-chip preparation');
console.log(JSON.stringify(first));
"""
    native = json.loads(subprocess.check_output(['node', '-e', code], text=True,
                                                cwd=root.parent.parent))
    a = r['concrete_primary'](native['ik1302'])
    assert r['number'](w['ip'](a)) == 0x35
    assert [r['number'](a.r[j]) for j in (2, 5)] == [0, 5]
    assert r['number'](a.r[22]) == 7 and all(
        r['number'](a.st[j]) == 0 for j in range(1, 24, 3))
    starts = r['inlet']['match_controller'](a); assert len(starts) == 2
    print('PASS fresh native cancelled-reader35: mode(0,5), raw cache and '
          'ready data; two original-controller matches; unobserved ALL5 mirror.', flush=True)
    return starts, native


def context_constraints(a, context):
    code, sp, vector, selector, delta, r38, dr38, r26, types = context
    assert types is None
    result = [w['ip'](a) == code,
              *[value == n for value, n in zip(w['stack'](a), sp)]]
    if vector == 'diagonal': result.append(a.r[37] == a.r[40])
    elif vector is not None: result.append(w['byte'](a.r[37], a.r[40]) == vector)
    for value, domain in ((a.s1, selector), (a.r[38], r38), (a.r[26], r26)):
        if domain is not None: result.append(Or(*[value == n for n in domain]))
    if delta is not None: result.append(a.s1-a.r[35] == delta)
    if dr38 is not None: result.append(a.r[38]-a.r[35] == dr38)
    return result


def assigned(label, x, y, selector):
    return {'zero': 0, 'eight': 8, 'fifteen': 15,
        'copy_R5': y, 'copy_R2': x, 'copy_S1': selector,
        'toggle': x^8, 'toggle_R2': x^8, 'preserve2': x, 'preserve5': y}[label]


def mode_product(starts, safe, *, exact=False):
    parents = {(i, 0, 5): None for i in starts}; todo = deque(parents)
    templates = {}; pruned = 0; expanded = 0
    while todo:
        state = todo.popleft(); i, x, y = state; code = states[i][0]
        if code not in safe: continue
        template = None
        if exact:
            key = code, x, y
            if key not in templates:
                a = q['State'](f'reset_product_{code:02X}_{x:X}_{y:X}')
                p = w['base'](a, code); p.add(a.r[2] == x, a.r[5] == y, r['ready'](a))
                if code == 0xB3: p.add(UGE(a.r[29], 8))
                if code == 0x5F: p.add(Or(*[a.r[29] == v for v in (5, 7, 13, 15)]))
                b = w['ex'](a, code, *q['arbitrary_keys'](
                    f'reset_product_keys_{code:02X}_{x:X}_{y:X}'))
                templates[key] = a, b, p
            a, b, p = templates[key]
            p.push(); p.add(*context_constraints(a, states[i]))
            answer = p.check(); assert answer in (sat, unsat)
            if answer == unsat:
                p.pop(); pruned += len(edges[i]); continue
            template = a, b, p
        for selector in states[i][3]:
            u = assigned(origin['r2_changes'].get(code, 'preserve2'), x, y, selector)
            v = assigned(origin['r5_changes'].get(code, 'preserve5'), x, y, selector)
            for child in edges[i]:
                if code == 0xB3 and states[child][0] < 0xB8:
                    pruned += 1; continue
                if template:
                    p.push(); p.add(a.s1 == selector, b.r[2] == u, b.r[5] == v,
                                   *context_constraints(b, states[child]))
                    answer = p.check(); p.pop(); assert answer in (sat, unsat)
                    if answer == unsat: pruned += 1; continue
                target = child, u, v
                if target not in parents: parents[target] = state; todo.append(target)
        if template: p.pop()
        expanded += 1
        if exact and expanded % 500 == 0:
            print(f'exact product:{expanded} expanded/{len(parents)} reached/'
                  f'{len(todo)} pending', flush=True)
    # Only savedR5 must be low for the NEXT scanner8B/07 gate. Requiring
    # both fields low would miss a useful candidate idle(5,0), for example.
    goals = [s for s in parents if states[s[0]][0] == 0x35 and s[2] < 5]
    both_low = sum(s[1] < 5 for s in goals)
    report = {'exactLocalEdges': exact, 'contextsWithMode': len(parents),
        'controllerIds': len({s[0] for s in parents}), 'pending': len(todo),
        'expanded': expanded, 'pruned': pruned, 'lowSavedIdleGoals': len(goals),
        'bothLowIdleGoals': both_low,
        'idlePairs': {f'{x:X}/{y:X}': n for (x, y), n in sorted(Counter(
            (x, y) for i, x, y in parents if states[i][0] == 0x35).items())}}
    if not exact: assert (len(parents), report['controllerIds'], len(goals), both_low) == (12003, 1546, 80, 26)
    else: assert (len(parents), report['controllerIds'], len(goals), both_low,
                  expanded, pruned) == (7070, 1229, 68, 22, 6378, 5071)
    print('COMPLETE mode/readiness/raw product:', json.dumps(report), flush=True)
    for target in goals[:1]:
        chain = []
        while target is not None: chain.append(target); target = parents[target]
        print('CANDIDATE, not native:', ' '.join(
            f'{states[i][0]:02X}({x:X},{y:X})' for i, x, y in reversed(chain)), flush=True)
    return report, parents, goals


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    origin['assignment_inventory']()
    forced_tail_loss(); safe = holder_inventory(); b3_provenance(); operand_dispatch_provenance()
    b9_repair_branches()
    starts, native = native_entry()
    mode_product(starts, safe)
    mode_product(starts, safe, exact=True)
    r['inlet']['immutable_reference']()
    print('PASS source-based mode-reset audit. No native restore93, C-signF, '
          'Ms exchange or partialK2 is claimed.', flush=True)
