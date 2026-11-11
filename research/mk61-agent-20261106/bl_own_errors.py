"""Retire opened BJ tasks; label actual model hypotheses and actual decision states."""
import collections
import copy
import hashlib
import json
import re
from bl_common import ROOT, PARENT, SOURCES, read, rows, write, save_rows, sha, signature, check_previous
from bj_common import ROOT as BJ_ROOT
from bh_spec import install
from bl_vm import CachedVM
from ar_spec import verify


def visible_code(prompt, question):
    at = prompt.index('Задача: ') + len('Задача: ')
    assert prompt[at:at + len(question.strip())] == question.strip()
    protected = prompt[:at] + '<QUESTION>' + prompt[at + len(question.strip()):]
    code = []
    for address, text in re.findall(r'^([0-9A-F]{4}): ([0-9A-F ]+)$', protected, re.M):
        assert int(address, 16) == len(code)
        code += [int(x, 16) for x in text.split()]
    return code


def differences(a, b):
    out = []
    if a is None:
        return ['invalid_spec']
    if set(a.get('writes', {})) != set(b['writes']):
        out.append('store')
    def walk(x, y):
        if x == y:
            return
        if isinstance(x, str) and isinstance(y, str):
            out.append('register'); return
        if isinstance(x, dict) and isinstance(y, dict):
            out.append('constant'); return
        if isinstance(x, list) and isinstance(y, list):
            if x[0] != y[0]:
                out.append('operation_or_scope')
            for u, v in zip(x[1:], y[1:]):
                walk(u, v)
            return
        out.append('structure_or_scope')
    walk(a['X'], b['X'])
    return sorted(set(out)) or ['algebra_or_order']


def main():
    check_previous(); install(); ROOT.mkdir(exist_ok=True)
    assert not (ROOT / 'own-frozen.json').exists()
    vm = CachedVM(); positives = {}; negatives = {}; policy = {}; goals = {}; counts = collections.Counter(); sources = {}
    for split in ['development', 'closed']:
        by_id = {g['id']: g for g in rows(PARENT / (split + '-clean.jsonl'))}
        for arm in ['lora', 'full']:
            path = PARENT / arm / 'development-6000.json' if split == 'development' else PARENT / ('fixed6000_' + arm) / 'closed.json'
            report = read(path); sources[str(path)] = sha(path)
            primary = {r['id']: r for r in report['primary']['records']}
            if split == 'closed':
                episode_path = BJ_ROOT / 'decoder-budget-replay' / arm / 'results.json'
                episodes = read(episode_path)['records']; sources[str(episode_path)] = sha(episode_path)
            else:
                episodes = report['self']['records']
            for r in primary.values():
                goal = by_id[r['id']]; goals[goal['id']] = goal
                spec = r['declared_spec']; correct = bool(r['intent']['tested_equal'] and r['program_correct'])
                if r['intent']['tested_equal'] and not r['program_correct']:
                    counts['excluded_ROM_mismatch'] += 1; continue
                item = {'goal': goal, 'hypothesis': spec, 'correct': correct, 'source_models': [arm],
                        'source_split_retired': split, 'model_packet_sha256': sha(SOURCES[arm] / 'model.mkqb'),
                        'error_types': [] if correct else differences(spec, goal['spec'])}
                key = json.dumps([goal['task'], goal['spec']['angle'], spec], sort_keys=True, ensure_ascii=False)
                pool = positives if correct else negatives
                if key in pool:
                    pool[key]['source_models'].append(arm)
                else:
                    pool[key] = item
            for episode in episodes:
                goal = by_id[episode['task_id']]; current = episode['initial_spec']; attempted = False
                truth = bool(primary[goal['id']]['intent']['tested_equal'])
                for history in episode['history']:
                    if 'prompt' not in history or 'generation' not in history:
                        continue
                    prompt = history['prompt']; generation = history['generation']
                    is_replan = 'Повторно разбери только русское условие' in prompt
                    if is_replan:
                        attempted = True
                        if history['kind'] == 'replan':
                            current = episode['declared_spec']; truth = bool(episode['final_spec_intent']['tested_equal'])
                        continue
                    if generation.get('codec_error'):
                        continue
                    remaining = int(re.search(r'Осталось действий: (\d+)', prompt)[1])
                    code = visible_code(prompt, goal['task'])
                    check = verify(vm, code, goal['pool'], goal['spec'], goal['public_inputs'] + goal['audit_inputs'])
                    good_code = check['status'] == 'TESTED'
                    missing_text = re.search(r'не запускались: ([^\n]*)', prompt)[1].strip()
                    missing = [] if missing_text == 'нет' else [int(x.strip(), 16) for x in missing_text.split(',')]
                    if not truth:
                        action = 'diag' if not attempted and remaining >= 4 else 'unsure'; body = [4, 255, 255, 0, 0] if action == 'diag' else []
                    elif not good_code:
                        action = 'write' if remaining >= 3 else 'unsure'; body = []
                    elif missing:
                        action = 'run' if remaining >= 2 else 'unsure'; body = missing[:1] if action == 'run' else []
                    else:
                        action = 'done'; body = []
                    # Keep one early and one last-budget representative of repeated states.
                    normalized = re.sub(r'Осталось действий: \d+', 'Осталось действий: N', prompt)
                    key = hashlib.sha256(json.dumps([normalized, action, remaining <= 2, attempted], ensure_ascii=False).encode()).hexdigest()
                    if key in policy:
                        continue
                    policy[key] = {'id': 'bl:own:state:' + key[:16], 'goal': goal, 'question': goal['task'],
                        'raw_prompt': prompt, 'replan_attempted': attempted, 'hypothesis': copy.deepcopy(current),
                        'hypothesis_correct': truth, 'code_correct': good_code, 'action': action, 'body': body,
                        'target_spec': goal['spec'], 'pool': goal['pool'], 'source_arm': arm, 'source_split_retired': split,
                        'original_action': generation.get('action'), 'source_history_kind': history['kind']}
    for name, pool in [('own-correct', positives), ('own-errors', negatives)]:
        values = list(pool.values())
        for i, r in enumerate(values):
            r['id'] = f'bl:{name}:{i:05}'
        save_rows(ROOT / (name + '.jsonl'), values)
    save_rows(ROOT / 'own-policy.jsonl', list(policy.values()))
    save_rows(ROOT / 'retired-own-goals.jsonl', list(goals.values()))
    stats = {'own_correct': len(positives), 'own_wrong': len(negatives), 'actual_policy_states': len(policy),
             'error_types': dict(collections.Counter(t for r in negatives.values() for t in r['error_types'])),
             'policy_actions': dict(collections.Counter(r['action'] for r in policy.values())),
             'policy_hypothesis_truth': dict(collections.Counter(str(r['hypothesis_correct']) for r in policy.values())),
             'excluded': dict(counts), 'VM_cache': {'hits': vm.hits, 'misses': vm.misses}}
    write(ROOT / 'own-frozen.json', {'complete': True, 'all_source_tests_retired': True, 'no_fresh_test_used': True,
          'source_files': sources, 'stats': stats, 'files': {n: sha(ROOT / n) for n in ['own-correct.jsonl', 'own-errors.jsonl', 'own-policy.jsonl', 'retired-own-goals.jsonl']}})
    print(json.dumps(stats, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
