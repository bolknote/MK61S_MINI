"""Cross both code and goal; grade exclusively offline and seal new exams."""
import collections
import copy
import json
import random
import shutil
from al_common import ROOT, PREVIOUS, PARENT, INITIAL, INITIAL_PACKET, read, write, sha
from al_skills import build as skill_pairs
from ah_data import history as past_history
from ai_data import completion_seeds, select, replay_target
from af_data import seeds as ordinary_seeds
from ac_data import twin_seeds
from ha_data import basic_tasks, composite_tasks, algorithm_tasks
from hr_data import boundary_tasks, hard_tasks
from aj_teacher import make_session, row, follow, correct
from full_isa_vm import FullVM, check_task
from ha_protocol import encode, assemble
from tasks import save_jsonl


def main():
    ROOT.mkdir(exist_ok=True)
    if (ROOT / 'data-frozen.json').exists(): return
    rng = random.Random(141301); vm = FullVM(); seen = past_history()
    for directory in [PARENT, PREVIOUS]:
        for p in directory.glob('*.jsonl'):
            if any(x in p.name for x in ['train', 'development', 'fresh']) and not any(x in p.name for x in ['seeds', 'lessons', 'onpolicy']):
                seen.update((t.get('angle'), t['task']) for t in read(p) if isinstance(t.get('task'), str))
    sets = {}; skills = {}
    for split, kind, n, pairs, seed in [('train', 'train', 240, 600, 141302),
            ('development', 'validation', 80, 12, 141303), ('fresh', 'fresh', 160, 24, 141304)]:
        p = ROOT / (split + '.jsonl')
        if p.exists(): tasks = read(p); seen.update((t['angle'], t['task']) for t in tasks)
        else:
            specs = [(1, basic_tasks(vm, kind, 400, seed) + boundary_tasks(vm, kind, 100, seed + 1), int(n * .4)),
                (2, composite_tasks(vm, kind, 500, seed + 2), int(n * .4)),
                (3, algorithm_tasks(vm, kind, 300, seed + 3) + hard_tasks(vm, kind, 80, seed + 4), n - 2 * int(n * .4))]
            tasks = []
            for level, values, quota in specs:
                rng.shuffle(values); tasks += select(values, quota, level, split, seen)
            for t in tasks: t['id'] = 'al:' + t['id']
            save_jsonl(p, tasks)
        sets[split] = tasks
        save_jsonl(ROOT / (split + '-seeds.jsonl'), ordinary_seeds(tasks, vm, seed + 10))
        p = ROOT / (split + '-skills.jsonl')
        values = read(p) if p.exists() else skill_pairs(vm, kind, pairs, seed + 11, seen)
        save_jsonl(p, values); skills[split] = values; seen.update((t['angle'], t['task']) for t in values)
        save_jsonl(ROOT / (split + '-skill-seeds.jsonl'), twin_seeds(values, seed + 12))
        if split != 'train':
            selected = [t for level in [1, 2, 3] for t in [t for t in tasks if t['level'] == level][:8 if split == 'development' else 16]]
            save_jsonl(ROOT / (split + '-completion-seeds.jsonl'), completion_seeds(selected, 2))
        print(json.dumps({'split': split, 'tasks': len(tasks), 'skill_tasks': len(values)}), flush=True)
    crossed = []; recoveries = []; families = collections.Counter(); skipped = 0
    for i in range(0, len(skills['train']), 2):
        peers = skills['train'][i:i + 2]; quad = []; runs = []; valid = True
        rev = (i // 2) % 3
        for code_index, source in enumerate(peers):
            for goal_index, t in enumerate(peers):
                seed = {'initial_code': source['reference_code'], 'candidate_code': source['reference_code'],
                    'prefill_revision': rev, 'pre_run_all': True, 'trace_before': (i // 2) % 3 == 1,
                    'pool': t['constants']}
                s = make_session(t, seed, vm); r = row(s, t, 'crossed_goal_code')
                expected = int(code_index == goal_index)
                if not s.eligibility()[0] or r['correctness'] != expected: valid = False
                checked = check_task(vm, assemble(s.body, s.pool, 'asm'), t)
                if not expected and all(c['pass'] for c in checked['details'][:len(t['public_tests'])]): valid = False
                quad.append(r); runs.append(copy.deepcopy(s.runs))
                if expected == 0: recoveries += follow(s, t, 'crossed_verified_repair')
        if not valid: skipped += 1; continue
        assert runs[0] == runs[1] and runs[2] == runs[3], 'Only goal may differ within a code row'
        assert [r['action'] for r in quad] == ['done', 'write', 'write', 'done']
        crossed.append({'id': peers[0]['goal_twin_group'], 'family': peers[0]['skill_family'],
            'rows': quad, 'truth': [1, 0, 0, 1], 'public_counterexamples_available': True})
        families[peers[0]['skill_family']] += 1
    assert len(crossed) >= 300
    save_jsonl(ROOT / 'crossed.jsonl', crossed)
    # Every new ordinary exercise also has a complete verified repair/finish path.
    ordinary = []
    lookup = {t['id']: t for t in sets['train']}
    for seed in read(ROOT / 'train-seeds.jsonl'):
        ordinary += follow(make_session(lookup[seed['task_id']], seed, vm), lookup[seed['task_id']], 'new_ordinary')
    observed = []; old_counts = collections.Counter()
    report = json.loads((PREVIOUS / 'initial-fresh.json').read_text())
    for part, tf, sf in [('main', 'fresh.jsonl', 'fresh-seeds.jsonl'),
            ('skills', 'fresh-skills.jsonl', 'fresh-skill-seeds.jsonl'),
            ('completion', 'fresh.jsonl', 'fresh-completion-seeds.jsonl')]:
        tasks = {t['id']: t for t in read(PREVIOUS / tf)}
        for seed, episode in zip(read(PREVIOUS / sf), report[part]['details']):
            if episode['pass']: continue
            t = tasks[episode['id']]
            observed += replay_target(t, {'seed': seed, 'history': episode['history']}, vm)
            if episode['finished'] and not episode['program_correct']:
                s = make_session(t, seed, vm)
                checked = check_task(vm, assemble(episode['body'], s.pool, 'asm'), t)
                public_bad = any(not c['pass'] for c in checked['details'][:len(t['public_tests'])])
                old_counts['false_DONE'] += 1; old_counts['public_failure' if public_bad else 'hidden_only_failure'] += 1
    save_jsonl(ROOT / 'hard-lessons.jsonl', observed + recoveries)
    save_jsonl(ROOT / 'lessons.jsonl', ordinary)
    retention = read(PARENT / 'anchors.jsonl') + read(PARENT / 'completion.jsonl') + read(PARENT / 'retention.jsonl')
    rng.shuffle(retention); retention = retention[:20000]
    save_jsonl(ROOT / 'retention.jsonl', retention)
    shutil.copytree(PARENT / 'core-source', ROOT / 'core-source', dirs_exist_ok=True)
    policy = {'arms': ['late', 'all'], 'steps': 750, 'checkpoints': [250, 500, 750],
        'rank': 16, 'alpha': 32, 'lr_lora': .00015, 'lr_heads': .00005,
        'crossed_groups_per_batch': 4, 'hard_rows': 8, 'retention_rows': 8, 'ordinary_rows': 8,
        'anchor_rows': 8, 'semantic_weight': 1., 'cross_weight': 1., 'cross_margin': 1.,
        'body_weight': 1.5, 'distill_weight': 2., 'temperature': 2.,
        'no_global_false_DONE_suppression': True, 'context': 1024, 'max_turns': 10,
        'same_draws': True, 'strict_original_nonregression': True, 'Q4_every_forward': True,
        'old_exam_now_training': True, 'new_LLM_teacher_calls': False,
        'runtime_no_expected_hidden_reference': True}
    write(ROOT / 'policy.json', policy)
    files = {p.name: sha(p) for p in ROOT.iterdir() if p.suffix in ['.json', '.jsonl'] and p.name not in ['data-frozen.json', 'start-launch.json']}
    write(ROOT / 'data-frozen.json', {'files': files, 'crossed_groups': len(crossed), 'families': dict(families),
        'ambiguous_or_nonstopping_groups_skipped': skipped, 'hard_lessons': len(observed + recoveries),
        'ordinary_lessons': len(ordinary), 'retention_lessons': len(retention), 'old_false_DONE_diagnosis': dict(old_counts),
        'source_master_sha256': sha(INITIAL / 'model.safetensors'), 'source_packet_sha256': sha(INITIAL_PACKET),
        'frozen_before_SGD': True, 'input_rows_frozen': True})
    print(json.dumps({'frozen': True, 'crossed': len(crossed), 'hard': len(observed + recoveries), 'old_errors': dict(old_counts)}), flush=True)


if __name__ == '__main__': main()
