"""Actual loop recoveries, complementary retention, and independently frozen exams."""
import copy
import json
import multiprocessing
import random
import shutil
from concurrent.futures import ProcessPoolExecutor
from ai_common import ROOT,PARENT,TEACHERS,START,START_PACKET,INITIAL,INITIAL_PACKET,COMPILER,COMPILER_PACKET,read,write,sha
from ai_teacher import make_session,correct,follow,row,fork
from ai_skills import build as skill_pairs
from ah_data import history as past_history
from af_data import seeds as ordinary_seeds
from af_goals import tasks as goal_tasks
from ac_data import twin_seeds
from ha_data import basic_tasks,composite_tasks,algorithm_tasks
from hr_data import boundary_tasks,hard_tasks
from full_isa_vm import FullVM
from ha_protocol import constants,encode
from tasks import save_jsonl

_VM=None
def init_worker():
    global _VM
    _VM=FullVM()


def label(job):
    t,seed,origin=job;s=make_session(t,seed,_VM);values=follow(s,t,origin)
    if origin=='loop_completion':
        assert s.finished and correct(_VM,t,s.body,s.pool),(t['id'],seed)
    return values


def select(candidates,quota,level,split,seen):
    chosen=[]
    for t in candidates:
        if(t['angle'],t['task'])in seen:continue
        t=copy.deepcopy(t);t.update(id=f'ai:{split}:general:{level}:{len(chosen):04}',level=level,constants=constants(t['task']),require_subroutine=t['group']=='algorithm_subroutine')
        cases=t['public_tests']+t['hidden_tests'];n=1+len(chosen)%4;t['public_tests'],t['hidden_tests']=cases[:n],cases[n:]
        chosen.append(t);seen.add((t['angle'],t['task']))
        if len(chosen)==quota:break
    assert len(chosen)==quota,(split,level,len(chosen),quota)
    return chosen


def completion_seeds(tasks,per_task=1):
    rows=[]
    for i,t in enumerate(tasks):
        for j in range(per_task):
            n=[2,4,6][(i+j)%3]
            rows.append({'task_id':t['id'],'pair_id':t['id']+f':completion{j}',
              'initial_code':t['reference_code'],'candidate_code':t['reference_code'],'prefill_revision':n,
              'consume_prefill_actions':n,'pre_run_all':bool((i+j)%2),'intentionally_correct':True})
    return rows


def replay_target(t,record,vm):
    s=make_session(t,record['seed'],vm);values=[];branches=0
    for h in record['history']:
        if'prompt'not in h or'generation'not in h:continue
        assert s.request()==h['prompt'],('Target history mismatch',t['id'])
        g=h['generation'];r=row(s,t,'actual_error_state',student_action=g.get('action'))
        r['observed_unnecessary_WRITE']=r['correctness']and g.get('action')=='write'
        r['observed_correct_UNSURE']=r['correctness']and g.get('action')=='unsure'
        r['observed_false_DONE']=not r['correctness']and g.get('action')=='done'
        values.append(r)
        diverges=g.get('action')!=r['action']or(g.get('action')=='write'and not correct(vm,t,g.get('body'),s.pool))
        if diverges and branches<3:
            child=fork(s);recovery=follow(child,t,'complete_actual_recovery',recovery_branch=branches)
            for item in recovery:item['recovery_finished_correctly']=child.finished and correct(vm,t,child.body,child.pool)
            values+=recovery;branches+=1
        if g.get('codec_error'):break
        s.apply_action(g['action'],g['body'])
        if s.finished or s.abstained:break
    return values


def main():
    ROOT.mkdir(exist_ok=True)
    if(ROOT/'data-frozen.json').exists():return
    assert(ROOT/'anchor-frozen.json').exists()
    vm=FullVM();seen=past_history();sets={};new_skills={}
    for p in PARENT.glob('*.jsonl'):
        if any(x in p.name for x in ['train','development','fresh'])and not any(x in p.name for x in ['lessons','seeds','onpolicy']):
            seen.update((t.get('angle'),t['task'])for t in read(p)if isinstance(t.get('task'),str))
    for split,kind,n,seed in [('train','train',160,1213301),('development','validation',24,1213302),('fresh','fresh',36,1213303)]:
        path=ROOT/(split+'-skills.jsonl');values=read(path)if path.exists()else skill_pairs(vm,kind,n,seed,seen)
        save_jsonl(path,values);new_skills[split]=values;seen.update((t['angle'],t['task'])for t in values)
        items=twin_seeds(values,seed+1)
        if split=='train':
            lookup={t['id']:t for t in values};rng=random.Random(seed+2)
            for pair in range(0,len(items),4):
                pool=lookup[items[pair]['task_id']]['constants'][:];rng.shuffle(pool)
                for s in items[pair:pair+2]:s['pool']=pool[:]
        save_jsonl(ROOT/(split+'-skill-seeds.jsonl'),items)
        print(json.dumps({'split':split,'skill_tasks':len(values)}),flush=True)
    for split,kind,count,seed in [('train','train',1000,1213401),('development','validation',160,1213402),('fresh','fresh',240,1213403)]:
        path=ROOT/('train-new.jsonl'if split=='train'else split+'.jsonl')
        if path.exists():sets[split]=read(path);seen.update((t['angle'],t['task'])for t in sets[split]);continue
        rng=random.Random(seed);tasks=[]
        specs=[(1,basic_tasks(vm,kind,max(1600,count),seed)+boundary_tasks(vm,kind,600,seed+1),150 if split=='train'else int(count*.4)),
          (2,composite_tasks(vm,kind,max(2000,count),seed+2),650 if split=='train'else int(count*.4)),
          (3,algorithm_tasks(vm,kind,1500,seed+3)+hard_tasks(vm,kind,240,seed+4),200 if split=='train'else count-2*int(count*.4))]
        for level,candidates,quota in specs:
            rng.shuffle(candidates);tasks+=select(candidates,quota,level,split,seen)
        for t in tasks:assert correct(vm,t,encode(t['reference_code'],t['constants'],'asm'),t['constants'])
        save_jsonl(path,tasks);sets[split]=tasks
        print(json.dumps({'split':split,'main_tasks':len(tasks)}),flush=True)
    # All finite legacy goal wordings are enumerated, and previous exact tasks excluded.
    for split,kind,n,seed in [('development','validation',16,1213502),('fresh','fresh',24,1213503)]:
        path=ROOT/(split+'-goals.jsonl')
        if path.exists():values=read(path)
        else:
            candidates=goal_tasks(vm,kind,96,seed);values=[]
            for at in range(0,len(candidates),2):
                pair=candidates[at:at+2]
                if any((t['angle'],t['task'])in seen for t in pair):continue
                for t in pair:t['id']='ai:'+t['id'];t['goal_twin_group']='ai:'+t['goal_twin_group']
                values+=pair;seen.update((t['angle'],t['task'])for t in pair)
                if len(values)==2*n:break
            assert len(values)==2*n,(split,len(values));save_jsonl(path,values)
        save_jsonl(ROOT/(split+'-goal-seeds.jsonl'),twin_seeds(values,seed+1))
    train={t['id']:t for name in ['train.jsonl','fresh.jsonl','fresh-skills.jsonl','fresh-goals.jsonl']for t in read(PARENT/name)}
    train.update({t['id']:t for t in sets['train']+new_skills['train']})
    ordinary=ordinary_seeds(sets['train'],vm,1213601)
    save_jsonl(ROOT/'train-new-seeds.jsonl',ordinary)
    for split,seed in [('development',1213602),('fresh',1213603)]:
        save_jsonl(ROOT/(split+'-seeds.jsonl'),ordinary_seeds(sets[split],vm,seed))
        count=16 if split=='development'else 24
        subset=[t for level in [1,2,3]for t in[t for t in sets[split]if t['level']==level][:count]]
        save_jsonl(ROOT/(split+'-completion-seeds.jsonl'),completion_seeds(subset,2))
    targets=[];episodes=set()
    for record in read(PARENT/'terminal-false-DONE-distill.jsonl')+read(PARENT/'terminal-retention-regressions-distill.jsonl'):
        seed=record['seed'];key=json.dumps([record['task_id'],seed],sort_keys=True)
        if key in episodes:continue
        episodes.add(key);detail=record.get('terminal',record)
        targets.append({'task_id':record['task_id'],'seed':seed,'history':detail['history']})
    save_jsonl(ROOT/'reproduction.jsonl',[train[k]for k in dict.fromkeys(x['task_id']for x in targets)])
    save_jsonl(ROOT/'reproduction-seeds.jsonl',[x['seed']for x in targets])
    if not(ROOT/'hard-lessons.jsonl').exists():
        hard=[]
        for target in targets:hard+=replay_target(train[target['task_id']],target,vm)
        save_jsonl(ROOT/'hard-lessons.jsonl',hard)
    jobs=[(train[s['task_id']],s,'skill_pair')for s in read(ROOT/'train-skill-seeds.jsonl')]
    jobs += [(train[s['task_id']],s,'composition'if train[s['task_id']]['level']>=2 else'general_basic')for s in ordinary]
    if not(ROOT/'lessons.jsonl').exists():
        lessons=[]
        with ProcessPoolExecutor(max_workers=4,mp_context=multiprocessing.get_context('spawn'),initializer=init_worker)as pool:
            for i,rows in enumerate(pool.map(label,jobs,chunksize=8)):
                lessons+=rows
                if i%1000==0:print(json.dumps({'ordinary_episodes':i,'lessons':len(lessons)}),flush=True)
        save_jsonl(ROOT/'lessons.jsonl',lessons)
    if not(ROOT/'completion.jsonl').exists():
        jobs=[]
        for i,t in enumerate(sets['train']):
            for n in [0,2,4,6]:
                for checked in [False,True]:
                    seed={'initial_code':t['reference_code'],'candidate_code':t['reference_code'],'prefill_revision':n,'consume_prefill_actions':n,'pre_run_all':checked}
                    jobs.append((t,seed,'loop_completion'))
        rows=[]
        with ProcessPoolExecutor(max_workers=4,mp_context=multiprocessing.get_context('spawn'),initializer=init_worker)as pool:
            for i,values in enumerate(pool.map(label,jobs,chunksize=8)):
                rows+=values
                if i%2000==0:print(json.dumps({'completion_episodes':i,'lessons':len(rows)}),flush=True)
        save_jsonl(ROOT/'completion.jsonl',rows)
    retention=read(PARENT/'retention.jsonl')+read(PARENT/'lessons.jsonl')+read(PARENT/'completion.jsonl')
    save_jsonl(ROOT/'retention.jsonl',retention)
    save_jsonl(ROOT/'train.jsonl',list(train.values()))
    save_jsonl(ROOT/'train-seeds.jsonl',ordinary+read(ROOT/'train-skill-seeds.jsonl')+read(PARENT/'train-seeds.jsonl')+ordinary_seeds(read(PARENT/'fresh.jsonl'),vm,1213801))
    for n in ['catalog.json','isa-audit.jsonl','legacy-development.jsonl']:shutil.copyfile(PARENT/n,ROOT/n)
    shutil.copytree(PARENT/'core-source',ROOT/'core-source',dirs_exist_ok=True)
    policy={'blocks':6,'steps_per_block':250,'batch':64,'anchor_batch_per_teacher':8,'temperature':2.,'distill_weight':2.,
      'lr_by_arm':{'lr20':2e-5,'lr10':1e-5},'body_weight':1.5,'semantic_weight':.5,'incorrect_class_weight':2.,'false_DONE_penalty':1.,
      'completion_margin_weight':.2,'completion_margin':1.,'context':1024,'max_turns':10,
      'quotas':{'hard':{'write':3,'done':3,'run':1,'unsure':1},'online':{'write':3,'done':2,'run':1,'trace':1,'unsure':1},
        'completion':{'done':8,'run':8},'composition':{'write':6,'done':4,'run':2},'retention':{'write':2,'done':3,'run':1,'trace':1,'unsure':1},
        'skills':{'write':2,'done':1,'run':1},'balanced':{'write':1,'done':2,'run':1},'distill':{'write':1,'done':2,'run':1}},
      'anchor_quotas':{'done':4,'write':2,'run':1,'trace':1},'power_skill_fraction':.25,'balance_RUN_test_indices':True,
      'selection_weights':{'main':.5,'skills':.2,'goals':.15,'completion':.15},'no_regression_gate':True,
      'no_regression_fields':['passed','false_DONE','correct_controls_completed'],'release':{'false_DONE':0,'strict_success':.8},
      'same_draws':True,'actual_Q4_every_update':True,'mining_blocks':[0,2,4],'old_reproductions_not_for_selection':True,
      'verified_complementary_teacher_policies':True,'new_large_LLM_calls':False,'old_exam_now_training':True}
    write(ROOT/'policy.json',policy)
    files={p.name:sha(p)for p in ROOT.iterdir()if p.suffix in ['.json','.jsonl']and p.name not in ['data-frozen.json','start-launch.json']}
    write(ROOT/'data-frozen.json',{'files':files,'task_counts':{'train':len(train),'new_train':len(sets['train'])+len(new_skills['train']),'development':len(sets['development']),'fresh':len(sets['fresh'])},
      'lessons':len(read(ROOT/'lessons.jsonl')),'hard_lessons':len(read(ROOT/'hard-lessons.jsonl')),'completion_lessons':len(read(ROOT/'completion.jsonl')),
      'retention_lessons':len(retention),'reproduction_episodes':len(targets),'anchors':len(read(ROOT/'anchors.jsonl')),
      'start_checkpoint_sha256':sha(START),'start_packet_sha256':sha(START_PACKET),
      'teachers':{n:{'master_sha256':sha(m/'model.safetensors'),'packet_sha256':sha(p)}for n,(m,p)in TEACHERS.items()},
      'initial_tool_master_sha256':sha(INITIAL/'model.safetensors'),'initial_tool_packet_sha256':sha(INITIAL_PACKET),
      'compiler_master_sha256':sha(COMPILER/'model.safetensors'),'compiler_packet_sha256':sha(COMPILER_PACKET),
      'frozen_before_SGD':True,'runtime_has_no_expected_hidden_reference':True})
    print(json.dumps({'frozen':True,'hard':len(read(ROOT/'hard-lessons.jsonl')),'completion':len(read(ROOT/'completion.jsonl'))}),flush=True)


if __name__=='__main__':main()
