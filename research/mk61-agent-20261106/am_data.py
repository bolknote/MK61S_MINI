"""Seal independent exams and separate goal, code-reading, and repair lessons."""
import collections
import copy
import json
import random
import shutil
from am_common import ROOT, SOURCE, PARENT, INITIAL, INITIAL_PACKET, read, write, sha, labels
from am_runtime import key, goal_prompt, code_prompt, snapshot, render
from am_skills import build as skill_pairs
from ah_data import history as older_history
from ai_data import select, completion_seeds
from af_data import seeds as ordinary_seeds
from ac_data import twin_seeds
from ha_data import basic_tasks, composite_tasks, algorithm_tasks
from hr_data import boundary_tasks, hard_tasks
from ha_protocol import encode
from aj_teacher import make_session, row, expert, correct, fork
from full_isa_vm import FullVM
from tasks import save_jsonl


def safe_view(t, pool):
    return {'id': t['id'], 'task': t['task'], 'angle': t['angle'], 'constants': list(pool),
        'public_tests': [{'segments': [{'inputs': copy.deepcopy(s['inputs'])} for s in c['segments']]} for c in t['public_tests']],
        'max_commands': t.get('max_commands', 128), 'max_frames': t.get('max_frames', 1024)}


def main():
    ROOT.mkdir(exist_ok=True)
    if (ROOT/'data-frozen.json').exists(): return
    vm = FullVM(); rng = random.Random(151301); seen = older_history()
    for source in [SOURCE, PARENT]:
        for p in source.glob('*.jsonl'):
            if any(x in p.name for x in ['train', 'fresh', 'development']) and not any(x in p.name for x in ['seeds', 'lessons', 'onpolicy']):
                seen.update((t.get('angle'), t['task']) for t in read(p) if isinstance(t.get('task'), str))
    for split, kind, n, seed in [('development', 'validation', 80, 151302), ('fresh', 'fresh', 160, 151303)]:
        path = ROOT/(split+'.jsonl')
        if path.exists(): tasks = read(path); seen.update((t['angle'], t['task']) for t in tasks)
        else:
            specs = [(1, basic_tasks(vm, kind, 400, seed)+boundary_tasks(vm, kind, 100, seed+1), int(n*.4)),
                (2, composite_tasks(vm, kind, 500, seed+2), int(n*.4)),
                (3, algorithm_tasks(vm, kind, 300, seed+3)+hard_tasks(vm, kind, 80, seed+4), n-2*int(n*.4))]
            tasks = []
            for level, values, quota in specs:
                rng.shuffle(values); tasks += select(values, quota, level, split, seen)
            for t in tasks: t['id'] = 'am:'+t['id']
            save_jsonl(path, tasks)
        save_jsonl(ROOT/(split+'-seeds.jsonl'), ordinary_seeds(tasks, vm, seed+10))
        selected = [t for level in [1,2,3] for t in [t for t in tasks if t['level']==level][:8 if split=='development' else 16]]
        save_jsonl(ROOT/(split+'-completion-seeds.jsonl'), completion_seeds(selected, 2))
        path = ROOT/(split+'-skills.jsonl')
        skills = read(path) if path.exists() else skill_pairs(vm, kind, 12 if split=='development' else 24, seed+11, seen)
        save_jsonl(path, skills); seen.update((t['angle'], t['task']) for t in skills)
        save_jsonl(ROOT/(split+'-skill-seeds.jsonl'), twin_seeds(skills, seed+12))
        print(json.dumps({'split': split, 'main_tasks': len(tasks), 'skills': len(skills)}), flush=True)
    main_tasks = read(SOURCE/'train.jsonl')+read(SOURCE/'fresh.jsonl')
    skills = read(SOURCE/'train-skills.jsonl')+read(SOURCE/'fresh-skills.jsonl')
    lookup = {t['id']: t for t in main_tasks+skills}; goals = {}; code_rows = []; tool_rows = []; counts = collections.Counter()
    def goal(t, pool):
        view = safe_view(t, pool); k = key(view, pool)
        if k not in goals:
            goals[k] = {'key': k, 'task_id': t['id'], 'view': view, 'pool': list(pool), 'prompt': goal_prompt(view, pool),
                'action': 'write', 'body': encode(t['reference_code'], pool, 'asm'), 'meaning': labels(t, pool), 'origin': 'goal_only', 'correctness': 0}
            if goals[k]['meaning'][0] >= 0:
                code_rows.append({'prompt': code_prompt(view, pool, goals[k]['body']), 'meaning': goals[k]['meaning'],
                    'action': 'unsure', 'body': [], 'origin': 'code_only', 'correctness': 0})
        return k
    def append(s, t, origin, cause=4):
        r = row(s, t, origin); k = goal(t, s.pool); state = snapshot(s); state['view'] = goals[k]['view']
        r.update(prompt=render(state), state=state, goal_key=k, before_body=list(s.body or []),
            meaning=[-1,-1], error_kind=3 if r['correctness'] else cause)
        tool_rows.append(r); counts[origin] += 1
    def follow(s, t, origin, cause=4):
        for _ in range(max(0, 10-(len(s.history)-s.initial_history))):
            append(s, t, origin, cause); action, body = expert(s,t); s.apply_action(action, body)
            if s.finished or s.abstained: break
    # Pool permutations are independent of requested operation or correctness.
    for at in range(0, len(skills), 2):
        peers = skills[at:at+2]
        if len(peers)!=2 or peers[0]['goal_twin_group']!=peers[1]['goal_twin_group']: continue
        pool = peers[0]['constants'][:]; rng.shuffle(pool)
        for t in peers:
            goal(t, t['constants']); goal(t, pool)
        family = peers[0]['skill_family']; cause = 1 if family in ['constant_binding','register_binding'] else 2 if family=='power_pair' else 0
        for source in peers:
            for t in peers:
                seed = {'initial_code': source['reference_code'], 'candidate_code': source['reference_code'],
                    'prefill_revision': (at//2)%3, 'pre_run_all': True, 'trace_before': False, 'pool': pool}
                follow(make_session(t,seed,vm), t, 'contrast_recovery', cause)
        if at%200==0: print(json.dumps({'skill_tasks':at,'tool_rows':len(tool_rows)}),flush=True)
    for seed in ordinary_seeds(main_tasks, vm, 151310):
        t = lookup[seed['task_id']]; follow(make_session(t,seed,vm),t,'ordinary_recovery')
    report = json.loads((SOURCE/'initial-fresh.json').read_text()); replayed = 0
    for part, tf, sf in [('main','fresh.jsonl','fresh-seeds.jsonl'),('skills','fresh-skills.jsonl','fresh-skill-seeds.jsonl'),
            ('completion','fresh.jsonl','fresh-completion-seeds.jsonl')]:
        tasks = {t['id']:t for t in read(SOURCE/tf)}
        for seed, episode in zip(read(SOURCE/sf),report[part]['details']):
            if episode['pass']:continue
            t = tasks[episode['id']]; s = make_session(t,seed,vm)
            for h in episode['history']:
                if 'prompt'not in h or 'generation'not in h:continue
                assert s.request()==h['prompt']; append(s,t,'actual_failure'); g=h['generation']; action,body=expert(s,t)
                if g.get('action')!=action or (action=='write'and not correct(vm,t,g.get('body'),s.pool)):
                    follow(fork(s),t,'actual_verified_repair')
                if g.get('codec_error'):break
                s.apply_action(g['action'],g['body'])
                if s.finished or s.abstained:break
            replayed+=1
    retention = read(SOURCE/'retention.jsonl')
    for r in retention: r.update(meaning=[-1,-1],error_kind=-1,origin='retention')
    save_jsonl(ROOT/'train-tasks.jsonl',list(lookup.values())); save_jsonl(ROOT/'goals.jsonl',list(goals.values()))
    save_jsonl(ROOT/'code-reading.jsonl',code_rows);save_jsonl(ROOT/'tool-lessons.jsonl',tool_rows);save_jsonl(ROOT/'retention.jsonl',retention)
    shutil.copytree(SOURCE/'core-source',ROOT/'core-source',dirs_exist_ok=True)
    policy={'arms':['direct','planned'],'steps':750,'warmup_stage_steps':250,'checkpoints':[250,500,750],
        'plan_cache_updates':[250,500],'lr_lora':.0001,'lr_heads':.00005,'lr_aux':.0002,
        'stage1':{'goal':16,'tool':8,'retention':8,'code':8},'stage2':{'goal':8,'tool':24,'retention':8,'code':8},
        'anchor_rows':8,'body_weight':1.5,'changed_token_weight':4.,'semantic_weight':.5,'wrong_class_weight':2.,
        'meaning_weight':.4,'error_kind_weight':.5,'risk_weight':.25,'distill_weight':2.,'temperature':2.,
        'context':1024,'max_tool_actions':10,'additional_planning_calls_per_episode':1,'same_draws':True,
        'actual_Q4_every_forward':True,'runtime_hypothesis_is_student_prediction':True,'runtime_no_gold_expected_hidden':True,
        'strict_original_nonregression':True,'new_LLM_teacher_calls':False,'auxiliary_heads_not_exported':True,
        'baseline_protocol':'legacy raw AJ','probe_fit':'closed-form ridge, no optimizer updates'}
    write(ROOT/'policy.json',policy)
    files={p.name:sha(p)for p in ROOT.iterdir()if p.suffix in ['.json','.jsonl']and p.name not in ['data-frozen.json','start-launch.json']}
    write(ROOT/'data-frozen.json',{'files':files,'goals':len(goals),'code_reading':len(code_rows),'tool_rows':len(tool_rows),
        'retention':len(retention),'replayed_failures':replayed,'origins':dict(counts),
        'source_master_sha256':sha(INITIAL/'model.safetensors'),'source_packet_sha256':sha(INITIAL_PACKET),
        'frozen_before_SGD':True,'old_exams_now_training':True,'no_true_plan_in_actor_input':True})
    print(json.dumps({'frozen':True,'goals':len(goals),'tools':len(tool_rows),'code':len(code_rows)}),flush=True)


if __name__=='__main__':main()
