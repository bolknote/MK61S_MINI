"""Transparent secondary correction of the vacuous zero-coverage comparator.

Reads development only. Original preregistration/selection remains unchanged.
Introduced after development inspection, before observing any closed scores.
"""
import hashlib
import json
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1] / '.build/mk61-agent-20261106/spec-intent-recovery-v1'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def key(summary, natural):
    return [summary['wrong_starts_repaired'], summary['passed'], -summary['false_DONE'],
            -summary['correct_starts_corrupted'], -summary['episodes_with_false_DONE_claims'],
            natural['passed'] / natural['total']]


def main():
    destination = ROOT / 'corrected-product-selection.json'
    assert not destination.exists(), 'Secondary selection is already frozen'
    inputs = {}; decisions = {}; checks = {}
    for arm in ['lora', 'full']:
        path = ROOT / f'parent-{arm}-development.json'
        parent = read(path); inputs[str(path.relative_to(ROOT))] = sha(path)
        baseline = parent['legacy_self']['summary']
        natural = parent['primary']['natural']
        best = {'step': 0, 'role': 'parent_' + arm, 'key': key(baseline, natural), 'fallback_to_legacy_runtime': True}
        checks[arm] = {}
        for step in [1000, 3000, 6000]:
            path = ROOT / arm / f'development-{step}.json'
            report = read(path); inputs[str(path.relative_to(ROOT))] = sha(path)
            current = report['self']['summary']
            tests = {
                'accepted_false_DONE_nonincrease': current['false_DONE'] <= baseline['false_DONE'],
                'corruption_nonincrease': current['correct_starts_corrupted'] <= baseline['correct_starts_corrupted'],
                'repairs_nondecrease': current['wrong_starts_repaired'] >= baseline['wrong_starts_repaired'],
                'completion_nondecrease': current['passed'] >= baseline['passed'],
                'false_claim_episodes_nonincrease': current['episodes_with_false_DONE_claims'] <= baseline['episodes_with_false_DONE_claims'],
            }
            rate = lambda r: r['passed'] / r['total']
            tests['natural_retention'] = rate(report['primary']['natural']) >= rate(natural) - .03
            for panel in ['editorial', 'structured']:
                tests[panel + '_retention'] = rate(report['primary']['panels'][panel]) >= rate(parent['primary']['panels'][panel]) - .05
            eligible = all(tests.values()); score = key(current, report['primary']['natural'])
            checks[arm][str(step)] = {'eligible': eligible, 'checks': tests, 'key': score}
            if eligible and score > best['key']:
                checkpoint = ROOT / arm / f'step-{step}.safetensors'
                best = {'step': step, 'role': ('fixed6000_' + arm if step == 6000 else 'secondary_' + arm),
                        'checkpoint_sha256': sha(checkpoint), 'key': score, 'fallback_to_legacy_runtime': False}
        decisions[arm] = best
    result = {
        'unix': time.time(), 'secondary_development_revision': True,
        'registered_after_development_inspection': True, 'closed_scores_observed': False,
        'closed_inference_may_already_be_running': True, 'uses_closed_files': False,
        'original_primary_selection_unchanged': True, 'training_and_exam_unchanged': True,
        'reason': 'New-prompt untrained actors have almost zero completion. Their zero error count is vacuous; compare to the original working legacy loop at nonzero coverage instead.',
        'criteria': 'The existing legacy-parent subset of the preregistered guards, including false-claim episodes and completion; no new numerical thresholds.',
        'branches': decisions, 'development_checks': checks,
        'preferred': max(decisions, key=lambda a: decisions[a]['key']),
        'development_inputs_sha256': inputs, 'driver_sha256': sha(Path(__file__)),
        'main_profile_changed': False,
    }
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
