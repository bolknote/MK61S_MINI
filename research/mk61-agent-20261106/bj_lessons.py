"""Verified four-way code/spec contrasts and complete old/new repair trajectories."""
import collections
import concurrent.futures
import copy
import json
import random
from bj_common import ROOT, PARENT, read, rows, write, save_rows, sha
from bh_spec import install
from bh_lessons import goal_row
from bj_runtime import Session, snapshot, goal_state, SPEC_DIAG
from ba_lessons import wrong_program
from ay_codec import encode, compile_spec
from ar_spec import infer, verify, equivalent
from full_isa_vm import FullVM, build


def tool_chunk(goals):
    install(); vm = FullVM(); out = []; stats = collections.Counter()
    for i, goal in enumerate(goals):
        bad, plausible = wrong_program(goal, vm, ['operation', 'argument', 'order'][i % 3])
        if not plausible:
            continue
        try:
            bad_spec = infer(bad, goal['pool'], goal['spec']['angle'])
            encode(bad_spec, goal['pool'])
            if equivalent(bad_spec, goal['spec'], goal['audit_inputs'])['tested_equal']:
                continue
        except (ValueError, ArithmeticError, KeyError, TypeError):
            continue
        assert verify(vm, bad, goal['pool'], goal['spec'], goal['audit_inputs'])['status'] == 'FAIL'
        for case in [0, 1]:
            identity = goal['id'] + ':' + str(case)
            for spec_ok, code_ok, origin in [
                (True, True, 'good_spec_good_code'), (True, False, 'good_spec_bad_code'),
                (False, True, 'bad_spec_good_code'), (False, False, 'bad_spec_bad_code')]:
                session = Session(goal, goal['reference_body'] if code_ok else bad, vm, 'spec', goal['spec'] if spec_ok else bad_spec, True, start_case=case)
                if i % 2 and spec_ok != code_ok:
                    session.apply_action('done', [])
                    assert not session.finished
                action = ('done' if code_ok else 'write') if spec_ok else 'diag'
                row = goal_row(goal, 0, origin)
                row.update(state=snapshot(session), action=action, body=SPEC_DIAG if not spec_ok else [],
                           contrast_id=identity, correctness=int(code_ok), simple=False)
                out.append(row)
                if not spec_ok:
                    session.apply_action('diag', SPEC_DIAG)
                    session.replan_attempted = True
                    session.apply_replan(goal['spec_body'])
                    post = goal_row(goal, 0, 'replay_done' if code_ok else 'replay_repair')
                    post.update(state=snapshot(session), action='done' if code_ok else 'write', correctness=int(code_ok))
                    out.append(post)
                if spec_ok and not code_ok:
                    session.apply_action('write', goal['spec_body'])
                    post = goal_row(goal, 0, 'replay_run_' + str(1 - case))
                    post.update(state=snapshot(session), action='run', body=[1 - case], correctness=1)
                    out.append(post)
                    session.apply_action('run', [1 - case])
                    post = goal_row(goal, 0, 'replay_done')
                    post.update(state=snapshot(session), action='done', correctness=1)
                    out.append(post)
            session = Session(goal, bad, vm, 'spec', bad_spec, True, start_case=case)
            for _ in range(11):
                session.apply_action('run', [case])
            post = goal_row(goal, 0, 'budget_unsure')
            post.update(state=snapshot(session), action='unsure', correctness=0)
            out.append(post)
        stats['four_way_goal_groups'] += 1
    return out, dict(stats)


def main():
    install(); assert not (ROOT / 'frozen.json').exists()
    if (ROOT / 'lessons-frozen.json').exists():
        return
    frozen = read(ROOT / 'teacher-frozen.json')
    for n, digest in frozen['files'].items():
        assert sha(ROOT / n) == digest
    goals = rows(ROOT / 'train-clean.jsonl')
    out = []
    for i, goal in enumerate(goals):
        out.append(goal_row(goal, i, 'natural'))
        replan = goal_row(goal, i, 'replan'); replan['state']['replan'] = True; replan['state']['remaining'] = 3 + i % 9; out.append(replan)
    rng = random.Random(261111115)
    unique = list({g['id']: g for g in goals}.values()); rng.shuffle(unique)
    # Retired failure tasks and explicit linguistic contrasts get representation.
    priority = [g for g in unique if g.get('curriculum') == 'new_minimal']
    selected = list({g['id']: g for g in priority + unique[:1200]}.values())
    build(); stats = collections.Counter()
    chunks = [selected[i:i + 12] for i in range(0, len(selected), 12)]
    with concurrent.futures.ProcessPoolExecutor(4) as pool:
        for i, (values, counts) in enumerate(pool.map(tool_chunk, chunks)):
            out.extend(values); stats.update(counts)
            if i % 10 == 0:
                print(json.dumps({'chunks': i + 1, 'of': len(chunks), 'rows': len(out)}), flush=True)
    # Keep old repairs and both public RUN cases. Exclude the known systematic
    # rejection->UNSURE bias; bounded UNSURE is explicitly generated above.
    for old in rows(PARENT / 'lessons.jsonl'):
        if old['origin'] not in ['replay_repair', 'replay_run_0', 'replay_run_1', 'replay_done']:
            continue
        row = copy.deepcopy(old)
        row['state']['declared_spec'] = copy.deepcopy(row['target_spec'])
        row['replay_source'] = 'frozen BF successful behavior retained through BH'
        out.append(row)
    for i, row in enumerate(out):
        row['id'] = f'bj:lesson:{i:06}'
    save_rows(ROOT / 'lessons.jsonl', out)
    write(ROOT / 'lessons-frozen.json', {'rows': len(out), 'counts': dict(collections.Counter(r['origin'] for r in out)),
          'stats': dict(stats), 'actual_ROM_verified_wrong_code': True, 'four_way_matching': True,
          'rejection_never_implies_UNSURE_when_budget_allows_replan': True,
          'files': {'lessons.jsonl': sha(ROOT / 'lessons.jsonl')}})
    print(json.dumps(read(ROOT / 'lessons-frozen.json')), flush=True)


if __name__ == '__main__':
    main()
