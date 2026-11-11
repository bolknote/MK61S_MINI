"""Actual retired student misunderstandings, preservation controls and repair replay."""
import collections
import copy
import json
import re
from bl_common import ROOT, PARENT, read, rows, save_rows, write, sha
from bl_spec import install
from bl_vm import CachedVM
from bh_lessons import goal_row
from bj_runtime import Session, snapshot, SPEC_DIAG
from ar_spec import equivalent, verify
from ay_codec import encode, compile_spec


def main():
    install(); assert not (ROOT / 'frozen.json').exists()
    if (ROOT / 'lessons-frozen.json').exists(): return
    out = [goal_row(g, i, 'natural') for i, g in enumerate(rows(ROOT / 'train-clean.jsonl'))]
    # Replay keeps the old successful, ROM-checked repair trajectories. Synthetic
    # wrong SPECs are deliberately excluded: the new negatives are student errors.
    keep = {'good_spec_good_code', 'good_spec_bad_code', 'replay_repair', 'replay_run_0', 'replay_run_1', 'replay_done', 'budget_unsure'}
    for old in rows(PARENT / 'lessons.jsonl'):
        if old['origin'] not in keep: continue
        r = copy.deepcopy(old); r['state']['replan_attempted'] = False
        out.append(r)
    vm = CachedVM(); skipped = collections.Counter()
    for correct, name in [(False, 'own-errors'), (True, 'own-correct')]:
        for item in rows(ROOT / (name + '.jsonl')):
            g = item['goal']; hyp = item['hypothesis']
            bank = g['public_inputs'] + g['checker_inputs'] + g['audit_inputs']
            if hyp is not None and equivalent(hyp, g['spec'], bank)['tested_equal'] != correct:
                skipped['inconsistent_hypothesis'] += 1; continue
            if hyp is None and correct: continue
            target = hyp if correct else g['spec']
            try:
                body = encode(target, g['pool']); reference = compile_spec(target, g['pool'])
            except (ValueError, ArithmeticError):
                skipped['unencodable_review'] += 1; continue
            if correct and verify(vm, reference, g['pool'], g['spec'], bank)['status'] != 'TESTED':
                skipped['correct_hypothesis_ROM_mismatch'] += 1; continue
            r = goal_row(g, 0, 'review_keep' if correct else 'review_fix')
            r['target_spec'] = copy.deepcopy(target); r['spec_body'] = body; r['reference_body'] = reference
            r['state'].update(replan=True, prior_spec=copy.deepcopy(hyp), replan_attempted=True, remaining=8)
            r['student_source'] = item['id']; out.append(r)
            # Matched actual-own-misreading controls: identical task and hypothesis,
            # both a correct program and the student's erroneous compiled program.
            if correct or hyp is None: continue
            try: bad = compile_spec(hyp, g['pool'])
            except (ValueError, ArithmeticError): continue
            if verify(vm, bad, g['pool'], g['spec'], bank)['status'] != 'FAIL': continue
            for case in [0, 1]:
                for code_ok in [True, False]:
                    s = Session(g, g['reference_body'] if code_ok else bad, vm, 'spec', hyp, True, start_case=case)
                    r = goal_row(g, 0, 'own_bad_good_code' if code_ok else 'own_bad_bad_code')
                    r.update(state=snapshot(s), action='diag', body=SPEC_DIAG,
                             contrast_id=item['id'] + ':' + str(case), student_source=item['id'])
                    r['state']['replan_attempted'] = False; out.append(r)
    # Genuine on-policy observations include failures after a used review and late
    # budgets. Do not relabel a raw prompt's literal pool during augmentation.
    for item in rows(ROOT / 'own-policy.jsonl'):
        g = item['goal']; text = item['raw_prompt']
        remaining = int(re.search(r'Осталось действий: (\d+)', text).group(1))
        missing = re.search(r'не запускались: ([^\n]*)', text).group(1)
        cases = re.findall(r'\b0[01]\b', missing)
        if not item['hypothesis_correct']:
            need = 3 + len(cases) if item['code_correct'] else 5
            action = 'diag' if not item['replan_attempted'] and remaining >= need else 'unsure'
        elif not item['code_correct']: action = 'write' if remaining >= 3 else 'unsure'
        elif cases: action = 'run' if remaining >= len(cases) + 1 else 'unsure'
        else: action = 'done'
        r = goal_row(g, 0, 'own_policy_' + action)
        r.update({k: copy.deepcopy(item[k]) for k in ['raw_prompt', 'question', 'replan_attempted']})
        r.update(action=action, body=SPEC_DIAG if action == 'diag' else [int(cases[0], 16)] if action == 'run' else [],
                 student_source=item['id'], own_hypothesis_correct=item['hypothesis_correct'])
        out.append(r)
    for i, r in enumerate(out): r['id'] = f'bl:lesson:{i:06}'
    save_rows(ROOT / 'lessons.jsonl', out)
    counts = dict(collections.Counter(r['origin'] for r in out))
    write(ROOT / 'lessons-frozen.json', {'rows': len(out), 'counts': counts, 'skipped': dict(skipped),
          'own_hypotheses_checked_on_full_retired_bank': True, 'review_keep_target_is_exact_student_hypothesis': True,
          'new_closed_used': False, 'files': {'lessons.jsonl': sha(ROOT / 'lessons.jsonl')}})
    print(json.dumps({'lessons_ready': True, 'counts': counts, 'skipped': dict(skipped)}), flush=True)


if __name__ == '__main__': main()
