"""Balanced new curricula, verified old-policy anchors, and unseen exams."""
import copy
import json
import multiprocessing
import random
import shutil
from concurrent.futures import ProcessPoolExecutor
from ah_common import ROOT,PARENT,START,START_PACKET,TEACHER,INITIAL,INITIAL_PACKET,COMPILER,COMPILER_PACKET,read,write,sha
from ah_teacher import make_session,correct,follow,row
from ah_skills import build as skill_pairs
from af_data import seeds as ordinary_seeds
from af_goals import tasks as goal_tasks
from ac_data import twin_seeds
from ha_data import basic_tasks,composite_tasks,algorithm_tasks
from hr_data import boundary_tasks,hard_tasks
from full_isa_vm import FullVM
from ha_protocol import constants,encode
from tasks import BUILD,save_jsonl

_VM=None
def init_worker():
    global _VM
    _VM=FullVM()


def history():
    seen=set()
    for directory in BUILD.iterdir():
        if not directory.is_dir()or directory==ROOT:continue
        for d in [directory,directory/'server-results']:
            for p in d.glob('*.jsonl'):
                if not any(x in p.name for x in ['train','validation','development','fresh','exam']):continue
                if any(x in p.name for x in ['lessons','seeds','onpolicy','preferences','sft']):continue
                for t in read(p):
                    if isinstance(t,dict)and isinstance(t.get('task'),str):seen.add((t.get('angle'),t['task']))
    return seen


def label(value):
    t,seed,origin=value;return follow(make_session(t,seed,_VM),t,origin)


def select(candidates,quota,level,split,seen):
    chosen=[]
    for t in candidates:
        if(t['angle'],t['task'])in seen:continue
        t=copy.deepcopy(t);t.update(id=f'ah:{split}:general:{level}:{len(chosen):04}',level=level,constants=constants(t['task']),require_subroutine=t['group']=='algorithm_subroutine')
        cases=t['public_tests']+t['hidden_tests'];n=1+len(chosen)%4;t['public_tests'],t['hidden_tests']=cases[:n],cases[n:]
        chosen.append(t);seen.add((t['angle'],t['task']))
        if len(chosen)==quota:break
    assert len(chosen)==quota,(split,level,len(chosen),quota)
    return chosen


def main():
    ROOT.mkdir(exist_ok=True)
    if(ROOT/'data-frozen.json').exists():return
    assert(ROOT/'anchor-frozen.json').exists()
    vm=FullVM();seen=history();sets={}
    for split,kind,n,seed in [('train','train',240,1113301),('development','validation',24,1113302),('fresh','fresh',36,1113303)]:
        path=ROOT/(split+'-skills.jsonl');values=read(path)if path.exists()else skill_pairs(vm,kind,n,seed,seen)
        save_jsonl(path,values);seen.update((t['angle'],t['task'])for t in values)
        items=twin_seeds(values,seed+1)
        if split=='train':
            rng=random.Random(seed+2)
            for pair in range(0,len(items),2):
                if pair%4==0:
                    pool=values[0]['constants']if False else next(t['constants']for t in values if t['id']==items[pair]['task_id'])
                    pool=pool[:];rng.shuffle(pool)
                    for s in items[pair:pair+2]:s['pool']=pool[:]
        save_jsonl(ROOT/(split+'-skill-seeds.jsonl'),items)
        print(json.dumps({'split':split,'skill_tasks':len(values)}),flush=True)
    for split,kind,count,seed in [('train','train',1000,1113401),('development','validation',160,1113402),('fresh','fresh',240,1113403)]:
        path=ROOT/(split+'.jsonl')
        if path.exists():sets[split]=read(path);seen.update((t['angle'],t['task'])for t in sets[split]);continue
        rng=random.Random(seed);tasks=[]
        specs=[(1,basic_tasks(vm,kind,max(800,count),seed)+boundary_tasks(vm,kind,240,seed+1),200 if split=='train'else int(count*.4)),
          (2,composite_tasks(vm,kind,max(900,count),seed+2),600 if split=='train'else int(count*.4)),
          (3,algorithm_tasks(vm,kind,800,seed+3)+hard_tasks(vm,kind,120,seed+4),200 if split=='train'else count-2*int(count*.4))]
        for level,candidates,quota in specs:
            rng.shuffle(candidates);tasks+=select(candidates,quota,level,split,seen)
        for t in tasks:assert correct(vm,t,encode(t['reference_code'],t['constants'],'asm'),t['constants'])
        save_jsonl(path,tasks);sets[split]=tasks
        print(json.dumps({'split':split,'main_tasks':len(tasks)}),flush=True)
    for split,kind,n,seed in [('development','validation',16,1113502),('fresh','fresh',24,1113503)]:
        path=ROOT/(split+'-goals.jsonl')
        if path.exists():values=read(path)
        else:
            candidates=goal_tasks(vm,kind,96,seed);values=[]
            for at in range(0,len(candidates),2):
                pair=candidates[at:at+2]
                if any((t['angle'],t['task'])in seen for t in pair):continue
                for t in pair:t['id']='ah:'+t['id'];t['goal_twin_group']='ah:'+t['goal_twin_group']
                values+=pair;seen.update((t['angle'],t['task'])for t in pair)
                if len(values)==2*n:break
            assert len(values)==2*n,(split,len(values));save_jsonl(path,values)
        save_jsonl(ROOT/(split+'-goal-seeds.jsonl'),twin_seeds(values,seed+1))
    train={t['id']:t for name in ['train.jsonl','fresh.jsonl','fresh-neighbors.jsonl','fresh-goals.jsonl']for t in read(PARENT/name)}
    train.update({t['id']:t for t in sets['train']+read(ROOT/'train-skills.jsonl')})
    new_main_seeds=ordinary_seeds(sets['train'],vm,1113601)
    save_jsonl(ROOT/'train-new-seeds.jsonl',new_main_seeds)
    for split,seed in [('development',1113602),('fresh',1113603)]:save_jsonl(ROOT/(split+'-seeds.jsonl'),ordinary_seeds(sets[split],vm,seed))
    jobs=[(train[s['task_id']],s,'skill_pair')for s in read(ROOT/'train-skill-seeds.jsonl')]
    jobs += [(train[s['task_id']],s,'composition'if train[s['task_id']]['level']>=2 else'general_basic')for s in new_main_seeds]
    lessons=[]
    with ProcessPoolExecutor(max_workers=4,mp_context=multiprocessing.get_context('spawn'),initializer=init_worker)as pool:
        for i,values in enumerate(pool.map(label,jobs,chunksize=8)):
            lessons+=values
            if i%1000==0:print(json.dumps({'episodes':i,'lessons':len(lessons)}),flush=True)
    # Completion practice balances RUN 01/02/03, especially the last pending case.
    completion=[]
    for t in sets['train']:
        if len(t['public_tests'])<3:continue
        s=make_session(t,{'initial_code':t['reference_code'],'candidate_code':t['reference_code']},vm)
        for _ in range(5):
            r=row(s,t,'correct_partial_checks');completion.append(r);s.apply_action(r['action'],r['body'])
            if s.finished or s.abstained:break
        for repeat in [0,1]:
            s=make_session(t,{'initial_code':t['reference_code'],'candidate_code':t['reference_code'],'pre_run_all':True,'prefill_revision':repeat},vm)
            completion.append(row(s,t,'correct_complete_no_rewrite'))
    # Ambiguity is still taught with independent wording combinations.
    rng=random.Random(1113701)
    for i in range(128):
        text=rng.choice(['Нужен расчёт на МК-61. ','Хочу программу для X. ','Надо обработать R2. ','Помоги составить вычисление. '])+rng.choice([
          'Формулу пока не назвал.','Требуемое действие уточню позднее.','Условие расчёта ещё отсутствует.','Нужную функцию пока не выбрали.','Что именно вычислять, сообщу потом.','Результат ещё не определён.'])
        t=copy.deepcopy(sets['train'][0]);t.update(id=f'ah:unknown:{i}',task=text,constants=constants(text),underspecified=True)
        s=make_session(t,{'initial_code':[0x50],'candidate_code':[0x50],'start_empty':i%2==0,'pre_run_all':True},vm)
        lessons.append(row(s,t,'underspecified'))
    save_jsonl(ROOT/'lessons.jsonl',lessons);save_jsonl(ROOT/'completion.jsonl',completion)
    save_jsonl(ROOT/'retention.jsonl',read(PARENT/'lessons.jsonl')+read(PARENT/'hard-lessons.jsonl')+read(PARENT/'retention.jsonl'))
    train_seeds=new_main_seeds+read(ROOT/'train-skill-seeds.jsonl')+read(PARENT/'train-seeds.jsonl')+ordinary_seeds(read(PARENT/'fresh.jsonl'),vm,1113801)
    save_jsonl(ROOT/'train.jsonl',list(train.values()));save_jsonl(ROOT/'train-seeds.jsonl',train_seeds)
    # Previous 33 failures are a seen reproduction panel, never selection.
    failures=read(PARENT/'new-false-DONE.jsonl');lookup={t['id']:t for t in read(PARENT/'fresh.jsonl')}
    save_jsonl(ROOT/'reproduction.jsonl',[lookup[k]for k in dict.fromkeys(f['task_id']for f in failures)])
    save_jsonl(ROOT/'reproduction-seeds.jsonl',[f['seed']for f in failures])
    for n in ['catalog.json','isa-audit.jsonl','legacy-development.jsonl']:shutil.copyfile(PARENT/n,ROOT/n)
    shutil.copytree(PARENT/'core-source',ROOT/'core-source',dirs_exist_ok=True)
    policy={'blocks':3,'steps_per_block':1000,'batch':64,'anchor_batch':16,'temperature':2.,'distill_weight':2.,
      'lr_lora':5e-5,'lr_action':5e-5,'lr_correct':5e-5,'body_weight':1.5,'semantic_weight':.5,'incorrect_class_weight':2.,'false_DONE_penalty':1.,
      'quotas':{'skills':{'write':8,'done':5,'run':3},'composition':{'write':8,'done':4,'run':4},'retention':{'write':4,'done':5,'run':3,'trace':1,'unsure':3},
        'online':{'write':4,'done':2,'trace':1,'unsure':1},'completion':{'run':4,'done':4}},
      'anchor_quotas':{'done':8,'write':4,'run':3,'trace':1},'power_skill_fraction':.25,'balance_RUN_test_indices':True,
      'selection_weights':{'main':.60,'skills':.25,'goals':.15},'no_regression_gate':True,
      'no_regression_fields':['passed','false_DONE','correct_controls_completed'],'release':{'false_DONE':0,'strict_success':.8},
      'context':1024,'max_turns':10,'same_draws':True,'actual_Q4_every_update':True,'old_reproductions_not_for_selection':True,
      'teacher_is_verified_frozen_balanced_policy':True,'new_large_LLM_calls':False}
    write(ROOT/'policy.json',policy)
    files={p.name:sha(p)for p in ROOT.iterdir()if p.suffix in ['.json','.jsonl']and p.name not in ['data-frozen.json','start-launch.json']}
    write(ROOT/'data-frozen.json',{'files':files,'task_counts':{'train':len(train),'development':len(sets['development']),'fresh':len(sets['fresh'])},
      'lessons':len(lessons),'completion_lessons':len(completion),'retention_lessons':len(read(ROOT/'retention.jsonl')),
      'anchors':len(read(ROOT/'anchors.jsonl')),'start_checkpoint_sha256':sha(START),'start_packet_sha256':sha(START_PACKET),
      'teacher_master_sha256':sha(TEACHER/'model.safetensors'),'initial_tool_master_sha256':sha(INITIAL/'model.safetensors'),'initial_tool_packet_sha256':sha(INITIAL_PACKET),
      'compiler_master_sha256':sha(COMPILER/'model.safetensors'),'compiler_packet_sha256':sha(COMPILER_PACKET),
      'frozen_before_SGD':True,'runtime_has_no_expected_hidden_reference':True,'old_exam_now_training':True})
    print(json.dumps({'frozen':True,'lessons':len(lessons),'completion':len(completion)}),flush=True)


if __name__=='__main__':main()
