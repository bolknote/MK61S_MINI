"""Audit the completed inference-only paired recovery experiment."""
import collections
import json
from bi_rejected_write import ARMS, ROOT, sources, read, write, sha, check_inputs


def signature(history):
    return [(h['kind'], h.get('generation', {}).get('generated_token_ids'), h.get('prompt')) for h in history]


def main():
    check_inputs()
    comparisons = {}
    details = {}
    for arm in ARMS:
        receipt = read(ROOT / arm / 'complete.json')
        assert receipt['complete'] and receipt['optimizer_updates'] == 0 and receipt['weights_unchanged']
        assert receipt['comparison_sha256'] == sha(ROOT / arm / 'comparison.json')
        comparison = read(ROOT / arm / 'comparison.json')
        control = read(ROOT / arm / 'control.json')['records']
        treatment = read(ROOT / arm / 'one_write.json')['records']
        assert comparison['control_reproducibility']['exact_matches'] == 512, 'Control differs from the original Q4 run'
        assert not comparison['nontriggered_reproducibility']['differences'], 'Untriggered trajectory changed'
        old = {r['id']: r for r in control}
        plans = {r['id']: r for r in read(sources() / f'fixed6000_{arm}/closed.json')['primary']['records']}
        recovered = []
        harmed = []
        events = []
        prefix_count = 0
        for row in treatment:
            before = old[row['id']]
            forced = [i for i, h in enumerate(row['history']) if h.get('forced_action') == 'write']
            assert len(forced) <= 1
            assert bool(forced) == row['recovery_used']
            if not forced:
                assert signature(row['history']) == signature(before['history'])
                continue
            index = forced[0]
            assert index > 0 and row['history'][index - 1]['kind'] == 'done_rejected'
            assert signature(row['history'][:index]) == signature(before['history'][:index]), 'Diverged before intervention'
            assert row['history'][index]['prompt'] == before['history'][index]['prompt'], 'Forced WRITE received a different prompt'
            prefix_count += 1
            event = row['recovery_events'][0]
            entry = {
                'id': row['id'], 'initially_correct': row['initially_correct'],
                'initial_spec_correct_on_audit': plans[row['task_id']]['intent']['tested_equal'],
                'reason': row['first_rejection']['check']['reason'],
                'ordinary_next_action': event['ordinary_action'],
                'before_WRITE_correct': event['before_task_correct'], 'after_WRITE_correct': event['after_task_correct'],
                'forced_generation_error': event['generation'].get('codec_error'),
                'control_pass': before['pass'], 'treatment_pass': row['pass'],
                'control_false_DONE': before['finished'] and not before['program_correct'],
                'treatment_false_DONE': row['finished'] and not row['program_correct'],
                'after_WRITE_actions': [h['kind'] for h in row['history'][index + 1:]],
                'final_correct': row['program_correct'], 'finished': row['finished'], 'abstained': row['abstained'],
            }
            events.append(entry)
            if row['pass'] and not before['pass']:
                recovered.append(entry)
            if before['pass'] and not row['pass']:
                harmed.append(entry)
        breakdown = {}
        for name, predicate in [
            ('initially_correct', lambda e: e['initially_correct']),
            ('initially_wrong', lambda e: not e['initially_correct']),
            ('initial_spec_correct', lambda e: e['initial_spec_correct_on_audit']),
            ('initial_spec_wrong', lambda e: not e['initial_spec_correct_on_audit']),
        ]:
            values = [e for e in events if predicate(e)]
            breakdown[name] = {
                'episodes': len(values), 'control_success': sum(e['control_pass'] for e in values),
                'one_write_success': sum(e['treatment_pass'] for e in values),
                'one_write_false_DONE': sum(e['treatment_false_DONE'] for e in values),
                'immediate_WRITE_correct': sum(e['after_WRITE_correct'] for e in values),
                'immediate_WRITE_corrupted_correct': sum(e['before_WRITE_correct'] and not e['after_WRITE_correct'] for e in values),
                'final_correct_but_unfinished': sum(e['final_correct'] and not e['finished'] for e in values),
                'abstained': sum(e['abstained'] for e in values),
            }
        details[arm] = {
            'causal_prefixes_exact': prefix_count, 'never_more_than_one_forced_WRITE': True,
            'triggered': events, 'recovered_successes': recovered, 'lost_successes': harmed,
            'breakdown': breakdown,
            'post_WRITE_action_sequences': dict(collections.Counter(' -> '.join(e['after_WRITE_actions']) for e in events)),
            'false_DONE_added': comparison['paired']['false_DONE']['gained_ids'],
            'false_DONE_removed': comparison['paired']['false_DONE']['lost_ids'],
            'new_false_DONE_with_correct_initial_spec': [row['id'] for row in treatment
                if row['id'] in comparison['paired']['false_DONE']['gained_ids']
                and plans[row['task_id']]['intent']['tested_equal']],
        }
        comparisons[arm] = comparison
    result = {'inference_only': True, 'optimizer_updates': 0, 'posthoc_diagnostic': True,
              'protocol_sha256': sha(ROOT / 'protocol.json'), 'comparisons': comparisons, 'analysis': details}
    write(ROOT / 'analysis.json', result)
    print(json.dumps({arm: {'control': comparisons[arm]['control'], 'one_write': comparisons[arm]['one_write'],
                           'triggered': comparisons[arm]['triggered'], 'breakdown': details[arm]['breakdown'],
                           'recovered': len(details[arm]['recovered_successes']), 'lost': len(details[arm]['lost_successes'])}
                      for arm in ARMS}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
