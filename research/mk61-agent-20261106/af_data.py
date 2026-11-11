"""Former exam errors become training; new tasks and seeds are sealed before SGD."""
import collections
import copy
import json
import multiprocessing
import random
import shutil
from concurrent.futures import ProcessPoolExecutor
from af_common import ROOT,PARENT,START,START_PACKET,INITIAL,INITIAL_PACKET,COMPILER,COMPILER_PACKET,COMPILER_SOURCE,read,write,sha
from ae_data import wrong
from af_teacher import correct,make_session,row,follow
from full_isa_vm import FullVM
from full_isa_math import literal,compile_expr
from full_isa_prepare import make_task,base_inputs
from ha_data import basic_tasks,composite_tasks,algorithm_tasks,verified
from hr_data import boundary_tasks,hard_tasks
from ha_protocol import constants,encode
from tasks import save_jsonl

_VM=None
def init_worker():
    global _VM
    _VM=FullVM()


def target_tasks(vm,split,count,seed):
    rng=random.Random(seed);out=[];seen=set()
    forms={
      'train':['Вычисли {f} {x}.','Найди {f} {x}.','Выдай в X {f} {x}.','Получи {f} {x}.','Нужен {f} {x}.'],
      'validation':['Итогом должен быть {f} {x}.','Требуется программа для {f} {x}.','Рассчитай {f} {x}.'],
      'fresh':['Составь код, вычисляющий {f} {x}.','Запрограммируй {f} {x}.','Нужно получить {f} {x}.']}
    values=['0','1','-1','.125','-.75','2','3','7']if split=='train'else['0','1','-1','.375','-.625','4','5','8']if split=='validation'else['0','1','-1','.625','-.375','6','9','11']
    for attempt in range(count*100):
        i=len(out);family=i%3;angle=rng.choice(['RAD','DEG','GRAD']);source='X'if rng.random()<.65 else 'R'+format(rng.randrange(15),'X')
        src='R0'if source=='X'else source;load=[]if source=='X'else[0x60+int(source[1:],16)]
        if family==0:
            power=rng.choice([2,4,8]);depth={2:1,4:2,8:3}[power];expr=src
            for _ in range(depth):expr=['square',expr]
            code=load+[0x22]*depth+[0x50]
            name={2:'квадрат',4:'четвёртую степень',8:'восьмую степень'}[power]
            text=rng.choice(forms[split]).format(f=name,x='текущего X'if source=='X'else source)
            if split=='train'and source=='X'and power==2 and i%2==0:text='Вычисли квадрат текущего X.'
            alternatives=[load+[0x22]*d+[0x50]for d in [1,2,3]if d!=depth]
            group='power_near_miss'
        elif family==1:
            value_=rng.choice(values);expr={'constant':value_};code=literal(value_)+[0x50];source='constant'
            if split=='train':text=rng.choice(['Выдай в X число {n}.','Загрузи в X число {n}.','Введи {n} и остановись.','В X должно быть {n}.']).format(n=value_)
            elif split=='validation':text=rng.choice(['Оставь в X константу {n}.','После выполнения требуется значение {n} в X.']).format(n=value_)
            else:text=rng.choice(['Сделай итог в X равным числу {n}.','Запрограммируй получение в X константы {n}.']).format(n=value_)
            alternatives=[literal(v)+[0x50]for v in ['0','1','-1','2']if v!=value_];group='literal_completion'
        else:
            value_=rng.choice(values[1:]);expr=['square',['+',src,{'constant':value_}]]
            code=load+literal(value_)+[0x10,0x22,0x50]
            if split=='train':text=rng.choice(['Вычисли ({x}+{n})*({x}+{n}).','Возведи сумму {x} и {n} в квадрат.','Выдай квадрат ({x}+{n}).']).format(x=source,n=value_)
            elif split=='validation':text=f'Результат в X: ({source}+{value_})².'
            else:text=rng.choice(['Нужен квадрат суммы {x} и {n}.','Составь программу для ({x}+{n})².']).format(x=source,n=value_)
            alternatives=[load+[0x22,0x50],load+literal(value_)+[0x10,0x50],load+literal(value_)+[0x10,0x22,0x22,0x50]];group='shifted_square'
        if not(split=='train'and i%3==0):text+=' Память R0–RE сохрани.'
        key=(angle,text)
        if key in seen:continue
        t=verified(vm,expr,text,f'af:{split}:target:{i:04}',group,split,angle,rng,code=code,source=source,raw=family==1)
        if not t:continue
        t.update(level=1 if family!=2 else 2,targeted=True,near_miss_codes=alternatives)
        cases=t['public_tests']+t['hidden_tests'];n=1+i%4
        t['public_tests'],t['hidden_tests']=cases[:n],cases[n:]
        out.append(t);seen.add(key)
        if len(out)==count:return out
    raise RuntimeError(('Finite target generator exhausted',split,len(out),count))


def choose_bad(t,vm,salt):
    for code in t.get('near_miss_codes',[]):
        if not correct(vm,t,encode(code,t['constants'],'asm'),t['constants']):return code
    return wrong(t,vm,salt)


def seeds(tasks,vm,seed,train=False):
    rng=random.Random(seed);items=[]
    for i,t in enumerate(tasks):
        pool=t.get('constants')or constants(t['task']);bad=choose_bad(t,vm,seed+i)
        for phase in range(2 if train else 1):
            values=pool[:]
            if phase==1 or(not train and i%3==0):rng.shuffle(values)
            common={'task_id':t['id'],'pair_id':t['id']+f':phase{phase}',
              'pool':values,'prefill_revision':rng.choice([0,1,2]),'initial_code':bad,
              'pre_run_all':rng.random()<.6,'trace_before':rng.random()<.15,
              'critic_warning':rng.random()<.15,'error_probe':rng.random()<.1,
              'binding_permuted':values!=pool}
            for good,candidate in [(False,bad),(True,t['reference_code'])]:
                items.append({**common,'candidate_code':candidate,'intentionally_correct':good})
    return items


def label(value):
    t,seed=value;s=make_session(t,seed,_VM);rows=follow(s,t)
    # Identical repeated writes can occur in the student's rollouts: the expert
    # must still finish a correct program, at varying remaining action budgets.
    base=make_session(t,{**seed,'pre_run_all':True},_VM);extras=[]
    if base.body is None:return rows
    for k in range(5):
        if k in [0,1,3,4]:
            if k and len(t['public_tests'])>1:
                for j in range(1,len(t['public_tests'])):base.run(j)
            if len(base.history)-base.initial_history<9:extras.append(row(base,t,'repeated_current_code',repeat_count=k))
        base.apply_action('write',base.body)
    return rows+extras


def replay_error(task,seed,detail,vm,gate=False):
    s=make_session(task,seed,vm);s.gate=gate;values=[];wrong_done=0;repeated=0
    for h in detail['history']:
        if 'prompt'not in h or 'generation'not in h:continue
        assert s.request()==h['prompt'],('Replay prompt mismatch',task['id'],h['kind'])
        value=row(s,task,'former_exam_student_state',student_action=h['generation'].get('action'))
        if h['kind']=='done'and value['correctness']==0:wrong_done+=1;value['hard_false_DONE']=True
        if h['kind']=='write'and value['correctness']==1:repeated+=1;value['unnecessary_WRITE']=True
        values.append(value)
        g=h['generation']
        if h['kind']=='generation_error':break
        if h['kind']=='semantic_DONE_rejected':
            s.observation=h['observation'];s.history.append({k:v for k,v in h.items()if k not in ['prompt','generation']})
        else:s.apply_action(g['action'],g['body'])
        if s.finished or s.abstained:break
    return values,wrong_done,repeated


def main():
    ROOT.mkdir(exist_ok=True)
    if(ROOT/'data-frozen.json').exists():return
    vm=FullVM();old={t['id']:t for name in ['fresh.jsonl','fresh-twins.jsonl','fresh-binding.jsonl']for t in read(PARENT/name)}
    seen={(t['angle'],t['task'])for name in ['train.jsonl','development.jsonl','fresh.jsonl','train-twins.jsonl','development-twins.jsonl','fresh-twins.jsonl']for t in read(PARENT/name)}
    sets={}
    for split,kind,count,seed in [('train','train',720,913301),('development','validation',160,913302),('fresh','fresh',240,913303)]:
        path=ROOT/(split+'.jsonl')
        if path.exists():sets[split]=read(path);seen.update((t['angle'],t['task'])for t in sets[split]);continue
        targets=target_tasks(vm,kind,240 if split=='train'else 32 if split=='development'else 48,seed)
        tasks=[]
        for t in targets:
            if(t['angle'],t['task'])in seen:continue
            seen.add((t['angle'],t['task']));tasks.append(t)
        desired=len(tasks)
        groups=[(1,basic_tasks(vm,kind,max(500,count),seed+10)+boundary_tasks(vm,kind,250,seed+11),160 if split=='train'else 48 if split=='development'else 72),
           (2,composite_tasks(vm,kind,max(500,count),seed+12),200 if split=='train'else 48 if split=='development'else 72),
           (3,algorithm_tasks(vm,kind,max(500,count),seed+13)+hard_tasks(vm,kind,120,seed+14),120 if split=='train'else 32 if split=='development'else 48)]
        rng=random.Random(seed)
        for level,candidates,quota in groups:
            rng.shuffle(candidates);chosen=[]
            for t in candidates:
                key=(t['angle'],t['task'])
                if key in seen:continue
                t=copy.deepcopy(t);t.update(id=f'af:{split}:general:{len(tasks)+len(chosen):04}',level=level,
                    constants=constants(t['task']),require_subroutine=t['group']=='algorithm_subroutine')
                cases=t['public_tests']+t['hidden_tests'];n=1+(len(tasks)+len(chosen))%4
                t['public_tests'],t['hidden_tests']=cases[:n],cases[n:]
                assert correct(vm,t,encode(t['reference_code'],t['constants'],'asm'),t['constants'])
                chosen.append(t);seen.add(key)
                if len(chosen)==quota:break
            assert len(chosen)==quota,(split,level,len(chosen));tasks+=chosen
        if split=='train':
            tasks+=list(old.values())
            from ab_demos import tasks as user_tasks
            for j,(t,bad)in enumerate(user_tasks(vm)):
                t.update(id=f'af:user:{j}',level=2 if bad is None else 1,constants=constants(t['task']),targeted=True)
                if bad is None:bad=literal('1')+[0x65,0x10]+literal('-1')+[0x12,0x50]
                t['near_miss_codes']=[bad];tasks.append(t)
        save_jsonl(path,tasks);sets[split]=tasks
        print(json.dumps({'split':split,'tasks':len(tasks),'new_targeted':desired}),flush=True)
    for split,seed in [('train',913401),('development',913402),('fresh',913403)]:
        path=ROOT/(split+'-seeds.jsonl')
        if not path.exists():
            items=seeds(sets[split],vm,seed,split=='train')
            if split=='train':
                items+=[{**s,'start_empty':True}for s in items[::16]if not s['intentionally_correct']]
            save_jsonl(path,items)
    lookup={t['id']:t for t in sets['train']}
    if(ROOT/'lessons.jsonl').exists():
        lessons=read(ROOT/'lessons.jsonl');replayed=sum(r['origin']=='former_exam_student_state'for r in lessons)
        bad_done=sum(r.get('hard_false_DONE',False)for r in lessons);unnecessary=sum(r.get('unnecessary_WRITE',False)for r in lessons)
    else:
        jobs=[];lookup={t['id']:t for t in sets['train']}
        jobs=[(lookup[s['task_id']],s)for s in read(ROOT/'train-seeds.jsonl')]
        lessons=[]
        with ProcessPoolExecutor(max_workers=4,mp_context=multiprocessing.get_context('spawn'),initializer=init_worker)as pool:
            for i,values in enumerate(pool.map(label,jobs,chunksize=8)):
                lessons+=values
                if i%1000==0:print(json.dumps({'labelled':i,'lessons':len(lessons)}),flush=True)
        # Last turn's viewed exam is explicitly training data in this experiment.
        replayed=0;bad_done=0;unnecessary=0
        for arm in ['lora16','full']:
            audit=json.loads((PARENT/(arm+'-fresh-audit.json')).read_text())
            for part,taskfile,seedfile in [('main','fresh.jsonl','fresh-seeds.jsonl'),('twins','fresh-twins.jsonl','fresh-twin-seeds.jsonl'),('binding','fresh-binding.jsonl','fresh-binding-seeds.jsonl')]:
                tasks={t['id']:t for t in read(PARENT/taskfile)};items=read(PARENT/seedfile)
                for mode,panel in audit[part].items():
                    for seed,detail in zip(items,panel['details']):
                        values,n,m=replay_error(tasks[seed['task_id']],seed,detail,vm,gate=mode!='raw')
                        lessons+=values;replayed+=len(values);bad_done+=n;unnecessary+=m
    save_jsonl(ROOT/'lessons.jsonl',lessons);shutil.copyfile(PARENT/'lessons.jsonl',ROOT/'retention.jsonl')
    # Semantic pairs share the goal and session schedule; current code is the difference.
    pairs=[];items=[s for s in read(ROOT/'train-seeds.jsonl')if not s.get('start_empty')]
    for at in range(0,len(items),2):
        bad,good=items[at:at+2];t=lookup[bad['task_id']]
        common={'pre_run_all':True,'critic_warning':False,'error_probe':False,'trace_before':False}
        b=make_session(t,{**bad,**common},vm);g=make_session(t,{**good,**common},vm)
        if not g.eligibility()[0]:continue
        assert not correct(vm,t,b.body,b.pool)and correct(vm,t,g.body,g.pool)
        pairs.append({'bad':row(b,t,'paired_near_miss'),'good':row(g,t,'paired_near_miss')})
    save_jsonl(ROOT/'pairs.jsonl',pairs)
    for n in ['catalog.json','isa-audit.jsonl','legacy-development.jsonl']:shutil.copyfile(PARENT/n,ROOT/n)
    shutil.copytree(PARENT/'core-source',ROOT/'core-source',dirs_exist_ok=True)
    policy={'blocks':4,'steps_per_block':1000,'batch':64,'pairs_per_step':4,'lr_lora':1.5e-4,'lr_action':1e-4,'lr_correct':1e-4,
        'context':1024,'max_turns':10,'targeted_fraction':.7,'online_fraction_within_targeted':.35,
        'action_quotas':{'write':20,'done':24,'run':12,'trace':4,'unsure':4},
        'semantic_weight':.5,'incorrect_class_weight':2.,'false_DONE_penalty':1.,'pair_weight':.5,'pair_margin':3.,
        'release':{'false_DONE':0,'strict_success':.8},'same_draws':True,'actual_Q4_every_update':True,
        'old_exam_now_training':True,'start_is_existing_rank16_checkpoint':True,'teacher':'authored programs verified by ROM; no new LLM calls'}
    write(ROOT/'policy.json',policy)
    files={p.name:sha(p)for p in ROOT.iterdir()if p.suffix in ['.json','.jsonl']and p.name not in ['data-frozen.json','start-launch.json']}
    write(ROOT/'data-frozen.json',{'files':files,'task_counts':{k:len(v)for k,v in sets.items()},'lessons':len(lessons),'pairs':len(pairs),
        'retention_lessons':len(read(ROOT/'retention.jsonl')),'replayed_student_states':replayed,'prior_false_DONE_states':bad_done,'prior_unnecessary_WRITE_states':unnecessary,
        'start_checkpoint_sha256':sha(START),'start_packet_sha256':sha(START_PACKET),
        'initial_tool_master_sha256':sha(INITIAL/'model.safetensors'),'initial_tool_packet_sha256':sha(INITIAL_PACKET),
        'compiler_master_sha256':sha(COMPILER/'model.safetensors'),'compiler_packet_sha256':sha(COMPILER_PACKET),
        'frozen_before_SGD':True,'runtime_has_no_reference_or_expected':True})
    print(json.dumps({'frozen':True,'lessons':len(lessons),'pairs':len(pairs),'student_states':replayed}),flush=True)


if __name__=='__main__':main()
