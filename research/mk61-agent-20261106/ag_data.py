"""New error neighborhoods and held-out tasks, without changing old experiments."""
import collections
import copy
import json
import multiprocessing
import random
import shutil
from concurrent.futures import ProcessPoolExecutor
from ag_common import ROOT,PARENT,START,START_PACKET,HERE,INITIAL,INITIAL_PACKET,COMPILER,COMPILER_PACKET,read,write,sha
from ag_teacher import correct,make_session,row,follow
from af_data import seeds as ordinary_seeds,choose_bad
from ae_data import wrong
from ac_data import twin_seeds
from af_goals import tasks as goal_tasks
from ha_data import basic_tasks,composite_tasks,algorithm_tasks,number,verified
from hr_data import boundary_tasks,hard_tasks
from natural_data import symbolic,describe
from full_isa_math import compile_expr
from full_isa_protocol import linear_instructions
from full_isa_vm import FullVM
from ha_protocol import constants,encode,assemble
from tasks import BUILD,save_jsonl

_VM=None
def init_worker():
    global _VM
    _VM=FullVM()


def historical_keys():
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


def remap(expr,register_map,rng,kind,large=False):
    if isinstance(expr,str):return register_map.get(expr,expr)
    if isinstance(expr,dict):
        if'constant'in expr:
            n=number(rng,kind,small=not large)
            if large and rng.random()<.35:n=rng.choice(['0','1','-1','2','3','6','11','23'])
            return {'constant':n}
        return copy.deepcopy(expr)
    return [expr[0],*[remap(x,register_map,rng,kind,large)for x in expr[1:]]]


def corrupt(t,vm,rng,category):
    code=t['reference_code'];pool=t['constants'];body=encode(code,pool,'asm')
    candidates=[]
    if category=='constant_binding':
        positions=[i+2 for i in range(len(body)-2)if body[i:i+2]==[255,1]];rng.shuffle(positions)
        for at in positions:
            for value in [2,1,0,*range(len(pool))]:
                if value==body[at]:continue
                b=body[:];b[at]=value;candidates.append(assemble(b,pool,'asm'))
    if category=='register_binding':
        positions=[r['pc']for r in linear_instructions(code)if 0x60<=r['opcode']<=0x6E];rng.shuffle(positions)
        for at in positions:
            for v in rng.sample(list(range(0x60,0x6F)),15):
                if v==code[at]:continue
                c=code[:];c[at]=v;candidates.append(c)
    if category in ['missing_operations','expression_structure']and not t.get('require_subroutine'):
        positions=[r['pc']for r in linear_instructions(code)if r['opcode']in [0x0B,0x10,0x11,0x12,0x13,0x19,0x1A,0x1B,0x1C,0x1D,0x22,0x31,0x35]];rng.shuffle(positions)
        candidates += [code[:at]+code[at+1:]for at in positions]
    for c in candidates:
        if not correct(vm,t,encode(c,pool,'asm'),pool):return c
    return wrong(t,vm,rng.randrange(10**9))


def neighbors(vm,kind,count,seed,failures,seen):
    rng=random.Random(seed);out=[];templates={t['id']:t for t in read(PARENT/'fresh.jsonl')};algorithm_pool=None
    forms={'train':['Вычисли {e}.','Найди значение {e}.','Получи в X: {e}.','Нужен код для {e}.','Составь расчёт {e}.','Запиши программу: {e}.','Итогом должно быть {e}.','Проверь расчёт и получи {e}.'],
      'validation':['Результат требуется такой: {e}.','Построй программу, чтобы вычислить {e}.','Требуется получить в X выражение {e}.'],
      'fresh':['Разработай расчёт для выражения {e}.','Сделай вычисление величины {e}.','После запуска нужно получить {e}.']}
    for attempt in range(count*150):
        origin=failures[attempt%len(failures)];base=templates[origin['task_id']];category=origin['category'];source=base.get('source_kind','R')
        if base.get('expression')is not None:
            mapping=dict(zip([f'R{i:X}'for i in range(15)],rng.sample([f'R{i:X}'for i in range(15)],15)))
            if source=='X':mapping['R0']='R0'
            expr=remap(base['expression'],mapping,rng,kind,large=isinstance(base['expression'],dict))
            code=compile_expr(expr)+[0x50]
            if source=='X':
                if code[0]!=0x60:continue
                code=code[1:]
            term=symbolic(expr)if rng.random()<.5 else describe(expr,kind,rng)
            if source=='X':term=term.replace('R0','X')
            text=rng.choice(forms[kind]).format(e=term)+' Память R0–RE сохрани.'
            angle=rng.choice(['RAD','DEG','GRAD'])
            if(angle,text)in seen:continue
            t=verified(vm,expr,text,f'ag:{kind}:neighbor:{len(out):04}',base['group'],kind,angle,rng,code=code,source=source,raw=isinstance(expr,dict))
            if not t:continue
        else:
            if algorithm_pool is None:algorithm_pool=algorithm_tasks(vm,kind,max(700,count),seed+100)
            candidates=[t for t in algorithm_pool if t['group']==base['group']and(t['angle'],t['task'])not in seen]
            if not candidates:continue
            t=copy.deepcopy(rng.choice(candidates))
        t.update(id=f'ag:{kind}:neighbor:{len(out):04}',level=base['level'],constants=constants(t['task']),
            error_family=category,origin_failed_task=base['id'],require_subroutine=t['group']=='algorithm_subroutine')
        cases=t['public_tests']+t['hidden_tests'];n=1+len(out)%4;t['public_tests'],t['hidden_tests']=cases[:n],cases[n:]
        assert correct(vm,t,encode(t['reference_code'],t['constants'],'asm'),t['constants'])
        t['near_miss_codes']=[corrupt(t,vm,rng,category)]
        seen.add((t['angle'],t['task']));out.append(t)
        if len(out)==count:return out
    raise RuntimeError(('Error-neighborhood generator exhausted',kind,len(out),count))


def label(value):
    t,seed=value;out=follow(make_session(t,seed,_VM),t)
    # Positive completion controls matched to bad examples; revisions and run
    # schedules alone must never determine DONE.
    s=make_session(t,{**seed,'pre_run_all':True},_VM)
    if s.body:
        for repeat in range(3):
            if len(s.history)-s.initial_history<9:out.append(row(s,t,'repeat_control'))
            s.apply_action('write',s.body)
            for j in range(1,len(t['public_tests'])):s.apply_action('run',[j])
    return out


def main():
    ROOT.mkdir(exist_ok=True)
    if(ROOT/'data-frozen.json').exists():return
    vm=FullVM();failures=read(ROOT/'forty-errors.jsonl');seen=historical_keys();sets={}
    # The previous exam is training now. Its exact 40 failures remain a
    # separate reproduction panel, never a model-selection panel.
    for split,kind,count,seed in [('train','train',1200,1013301),('development','validation',64,1013302),('fresh','fresh',96,1013303)]:
        path=ROOT/(split+'-neighbors.jsonl')
        values=read(path)if path.exists()else neighbors(vm,kind,count,seed,failures,seen)
        save_jsonl(path,values);seen.update((t['angle'],t['task'])for t in values)
        print(json.dumps({'split':split,'neighbors':len(values)}),flush=True)
    for split,kind,count,seed in [('development','validation',160,1013402),('fresh','fresh',240,1013403)]:
        path=ROOT/(split+'.jsonl')
        if path.exists():sets[split]=read(path);seen.update((t['angle'],t['task'])for t in sets[split]);continue
        tasks=[];rng=random.Random(seed)
        groups=[(1,basic_tasks(vm,kind,1000,seed)+boundary_tasks(vm,kind,250,seed+1),int(count*.4)),
          (2,composite_tasks(vm,kind,1000,seed+2),int(count*.4)),
          (3,algorithm_tasks(vm,kind,900,seed+3)+hard_tasks(vm,kind,160,seed+4),count-2*int(count*.4))]
        for level,candidates,quota in groups:
            rng.shuffle(candidates);selected=[]
            for t in candidates:
                if(t['angle'],t['task'])in seen:continue
                t=copy.deepcopy(t);t.update(id=f'ag:{split}:general:{len(tasks)+len(selected):04}',level=level,constants=constants(t['task']),require_subroutine=t['group']=='algorithm_subroutine')
                cases=t['public_tests']+t['hidden_tests'];n=1+(len(tasks)+len(selected))%4;t['public_tests'],t['hidden_tests']=cases[:n],cases[n:]
                assert correct(vm,t,encode(t['reference_code'],t['constants'],'asm'),t['constants'])
                selected.append(t);seen.add((t['angle'],t['task']))
                if len(selected)==quota:break
            assert len(selected)==quota,(split,level,len(selected));tasks+=selected
        save_jsonl(path,tasks);sets[split]=tasks
    for split,kind,n,seed in [('development','validation',16,1013502),('fresh','fresh',24,1013503)]:
        path=ROOT/(split+'-goals.jsonl')
        if path.exists():values=read(path)
        else:
            candidates=goal_tasks(vm,kind,64,seed);values=[]
            for at in range(0,len(candidates),2):
                pair=candidates[at:at+2]
                if any((t['angle'],t['task'])in seen for t in pair):continue
                for t in pair:t['id']='ag:'+t['id'];t['goal_twin_group']='ag:'+t['goal_twin_group']
                values+=pair;seen.update((t['angle'],t['task'])for t in pair)
                if len(values)==2*n:break
            assert len(values)==2*n,(split,len(values));save_jsonl(path,values)
        save_jsonl(ROOT/(split+'-goal-seeds.jsonl'),twin_seeds(values,seed+1))
    train={t['id']:t for name in ['train.jsonl','fresh.jsonl','fresh-goals.jsonl']for t in read(PARENT/name)}
    train.update({t['id']:t for t in read(ROOT/'train-neighbors.jsonl')});sets['train']=list(train.values());save_jsonl(ROOT/'train.jsonl',sets['train'])
    for split,seed in [('train',1013601),('development',1013602),('fresh',1013603)]:
        selected=read(ROOT/'train-neighbors.jsonl')if split=='train'else sets[split]
        save_jsonl(ROOT/(split+'-seeds.jsonl'),ordinary_seeds(selected,vm,seed,train=split=='train'))
        if split!='train':save_jsonl(ROOT/(split+'-neighbor-seeds.jsonl'),ordinary_seeds(read(ROOT/(split+'-neighbors.jsonl')),vm,seed+10))
    jobs=[(train[s['task_id']],s)for s in read(ROOT/'train-seeds.jsonl')]
    lessons=[]
    with ProcessPoolExecutor(max_workers=4,mp_context=multiprocessing.get_context('spawn'),initializer=init_worker)as pool:
        for i,rows in enumerate(pool.map(label,jobs,chunksize=8)):
            lessons+=rows
            if i%1000==0:print(json.dumps({'episodes':i,'lessons':len(lessons)}),flush=True)
    # Replay the actual trajectories up to DONE, then label both the repair and
    # the same task already correctly repaired. The old seed/pool is preserved.
    hard=[];old_seeds=read(PARENT/'fresh-seeds.jsonl');audit=json.loads((PARENT/'replay-fresh-audit.json').read_text())['main']['raw']['details']
    from af_data import replay_error
    for f in failures:
        t=train[f['task_id']];seed=old_seeds[f['episode_index']];detail=audit[f['episode_index']]
        values,_,_=replay_error(t,seed,detail,vm)
        for r in values:
            r['hard_case']=True;r['origin']='actual_forty_error_state';hard.append(r)
        for permuted in [False,True]:
            pool=f['pool'][:]
            if permuted:random.Random(1013701+f['episode_index']).shuffle(pool)
            for good,code in [(False,f['wrong_code']),(True,t['reference_code'])]:
                s=make_session(t,{'task_id':t['id'],'pool':pool,'initial_code':code,'candidate_code':code,'pre_run_all':True,'prefill_revision':1},vm)
                hard+=follow(s,t,'forty_repair_and_completion',hard_case=True)
    save_jsonl(ROOT/'lessons.jsonl',lessons);save_jsonl(ROOT/'hard-lessons.jsonl',hard)
    save_jsonl(ROOT/'retention.jsonl',read(PARENT/'lessons.jsonl')+read(PARENT/'retention.jsonl'))
    # Mining sees both new neighborhoods and the entire old course, not only 40 strings.
    save_jsonl(ROOT/'train-seeds.jsonl',read(ROOT/'train-seeds.jsonl')+read(PARENT/'train-seeds.jsonl')+ordinary_seeds(read(PARENT/'fresh.jsonl'),vm,1013801))
    save_jsonl(ROOT/'reproduction.jsonl',[train[k]for k in dict.fromkeys(f['task_id']for f in failures)])
    save_jsonl(ROOT/'reproduction-seeds.jsonl',[old_seeds[f['episode_index']]for f in failures])
    for n in ['catalog.json','isa-audit.jsonl','legacy-development.jsonl']:shutil.copyfile(PARENT/n,ROOT/n)
    shutil.copytree(PARENT/'core-source',ROOT/'core-source',dirs_exist_ok=True)
    policy={'blocks':3,'steps_per_block':1200,'batch':64,'lr_lora':1e-4,'lr_action':8e-5,'lr_correct':8e-5,
        'context':1024,'max_turns':10,'semantic_weight':.5,'incorrect_class_weight':2.,'false_DONE_penalty':1.,
        'hard_quotas':{'write':8,'done':6,'run':2},'other_quotas':{'write':16,'done':14,'run':10,'trace':4,'unsure':4},
        'targeted_fraction':.5,'online_fraction':.2,'focused_hard_weight':2.,'focused_changed_token_weight':4.,
        'release':{'false_DONE':0,'strict_success':.8},'same_draws':True,'actual_Q4_every_update':True,
        'old_forty_not_for_selection':True,'raw_policy_is_primary':True,'full_calibrated_exam_not_repeated':True,
        'selection_weights':{'main':.65,'neighbors':.25,'goals':.10},'no_extra_pair_forward':True}
    write(ROOT/'policy.json',policy)
    files={p.name:sha(p)for p in ROOT.iterdir()if p.suffix in ['.json','.jsonl']and p.name not in ['data-frozen.json','start-launch.json']}
    write(ROOT/'data-frozen.json',{'files':files,'task_counts':{k:len(v)for k,v in sets.items()},'lessons':len(lessons),
        'hard_lessons':len(hard),'retention_lessons':len(read(ROOT/'retention.jsonl')),'original_false_DONE_episodes':40,
        'start_checkpoint_sha256':sha(START),'start_packet_sha256':sha(START_PACKET),
        'initial_tool_master_sha256':sha(INITIAL/'model.safetensors'),'initial_tool_packet_sha256':sha(INITIAL_PACKET),
        'compiler_master_sha256':sha(COMPILER/'model.safetensors'),'compiler_packet_sha256':sha(COMPILER_PACKET),
        'frozen_before_SGD':True,'runtime_has_no_reference_or_expected':True,'teacher':'authored programs verified by ROM; no new LLM calls'})
    print(json.dumps({'frozen':True,'lessons':len(lessons),'hard_lessons':len(hard)}),flush=True)


if __name__=='__main__':main()
