"""Before-SGD goal reversals: same code and facts, X² versus X⁴ goals."""
import copy
import json
import math
import random
import shutil
from af_common import ROOT,read,write,sha
from af_teacher import make_session,row,follow,correct
from ac_data import twin_seeds
from full_isa_prepare import make_task,base_inputs
from full_isa_vm import FullVM
from ha_protocol import constants
from tasks import save_jsonl


def tasks(vm,split,count,seed):
    rng=random.Random(seed);out=[];seen=set()
    forms={'train':['Вычисли {name} {src}; результат оставь в X.','Требуется {name} {src}; запиши программу.','Получи {name} {src}, затем остановись.'],
      'validation':['Нужен расчёт: {name} {src}; итог в X.','Возведение в степень: найди {name} {src}.'],
      'fresh':['Запрограммируй возведение в степень: {name} {src}.','Построй расчёт следующей величины: {name} {src}.']}
    for attempt in range(count*100):
        src='X'if rng.random()<.3 else'R'+format(rng.randrange(15),'X');angle=rng.choice(['RAD','DEG','GRAD']);form=rng.choice(forms[split])
        key=(src,angle,form)
        if key in seen:continue
        seen.add(key);i=len(out)//2;inputs=[base_inputs(rng)for _ in range(6)]
        values=['0','1','-1','2.5','-3','.125']if split=='train'else['1','0','-1','3.25','-2.25','.375']if split=='validation'else['-1','1','0','4.25','-1.75','.625']
        for state,value in zip(inputs,values):state[src]=value
        peers=[]
        for power,name in [(2,'квадрат'),(4,'четвёртую степень')]:
            code=([]if src=='X'else[0x60+int(src[1:],16)])+[0x22]*(1 if power==2 else 2)+[0x50]
            text=form.format(name=name,src='текущего X'if src=='X'else src)+' Память R0–RE сохрани.'
            t=make_task(vm,code,text,f'af:{split}:goal:{i}:{power}','power_goal_reversal',split,angle,copy.deepcopy(inputs),kind='ha_task',check_names=['X',*[f'R{x:X}'for x in range(15)]])
            cases=t['public_tests']+t['hidden_tests']
            for case,state in zip(cases,inputs):
                assert math.isclose(float(case['segments'][0]['expected']['numeric']['X']),float(state[src])**power,rel_tol=2e-6,abs_tol=2e-6)
            n=1+i%4;t['public_tests'],t['hidden_tests']=cases[:n],cases[n:]
            t.update(constants=constants(text),level=1,targeted=True,goal_twin_group=f'af:{split}:goal:{i}')
            peers.append(t)
        out+=peers
        if len(out)==2*count:return out
    raise RuntimeError('Goal-pair generator exhausted')


def main():
    assert not(ROOT/'prepared.json').exists()and not(ROOT/'start-launch.json').exists()
    if(ROOT/'goals-added-before-SGD.json').exists():return
    vm=FullVM();lessons=read(ROOT/'lessons.jsonl');pairs=read(ROOT/'pairs.jsonl');original=json.loads((ROOT/'data-frozen.json').read_text())
    shutil.copyfile(ROOT/'data-frozen.json',ROOT/'data-before-goals.json')
    # Check all earlier task sets, including pre-parent experiments. Only texts
    # are inspected here; no evaluation or weight update has started.
    from tasks import BUILD
    from af_data import seeds
    from ha_data import basic_tasks,composite_tasks,algorithm_tasks
    history=set()
    for directory in BUILD.iterdir():
        if not directory.is_dir()or directory==ROOT:continue
        for d in [directory,directory/'server-results']:
            for p in d.glob('*.jsonl'):
                if not any(x in p.name for x in ['train','validation','development','fresh','exam']):continue
                if any(x in p.name for x in ['lessons','seeds','onpolicy','preferences','sft']):continue
                for t in read(p):
                    if'task'in t:history.add((t.get('angle'),t['task']))
    used={(t['angle'],t['task'])for name in ['train.jsonl','development.jsonl','fresh.jsonl']for t in read(ROOT/name)};replaced={}
    for split,kind,seed in [('development','validation',914001),('fresh','fresh',914002)]:
        values=read(ROOT/(split+'.jsonl'));bad=[i for i,t in enumerate(values)if(t['angle'],t['task'])in history]
        if bad:
            candidates={1:basic_tasks(vm,kind,500,seed),2:composite_tasks(vm,kind,500,seed+1),3:algorithm_tasks(vm,kind,500,seed+2)}
            for i in bad:
                old=values[i];level=old['level']
                t=next(t for t in candidates[level]if(t['angle'],t['task'])not in history|used)
                t=copy.deepcopy(t);t.update(id=old['id'],level=level,constants=constants(t['task']),require_subroutine=t['group']=='algorithm_subroutine')
                cases=t['public_tests']+t['hidden_tests'];n=1+i%4;t['public_tests'],t['hidden_tests']=cases[:n],cases[n:]
                values[i]=t;used.add((t['angle'],t['task']))
            save_jsonl(ROOT/(split+'.jsonl'),values);save_jsonl(ROOT/(split+'-seeds.jsonl'),seeds(values,vm,913402 if split=='development'else 913403))
        replaced[split]=len(bad)
    for split,kind,n,seed in [('train','train',64,913601),('development','validation',16,913602),('fresh','fresh',24,913603)]:
        values=tasks(vm,kind,n,seed);items=twin_seeds(values,seed+1);save_jsonl(ROOT/(split+'-goals.jsonl'),values);save_jsonl(ROOT/(split+'-goal-seeds.jsonl'),items)
        if split=='train':
            save_jsonl(ROOT/'train.jsonl',read(ROOT/'train.jsonl')+values);save_jsonl(ROOT/'train-seeds.jsonl',read(ROOT/'train-seeds.jsonl')+items)
            lookup={t['id']:t for t in values}
            for at in range(0,len(items),2):
                seeds=items[at:at+2];states=[]
                for seed_ in seeds:
                    t=lookup[seed_['task_id']];s=make_session(t,seed_,vm);r=row(s,t,'same_code_opposite_goal');states.append(r);lessons+=follow(s,t,'same_code_opposite_goal')
                bad=next(r for r in states if not r['correctness']);good=next(r for r in states if r['correctness'])
                assert good['action']=='done';pairs.append({'bad':bad,'good':good})
    save_jsonl(ROOT/'lessons.jsonl',lessons);save_jsonl(ROOT/'pairs.jsonl',pairs)
    write(ROOT/'goals-added-before-SGD.json',{'train_tasks':128,'development_tasks':32,'fresh_tasks':48,'prior_exact_text_matches_replaced':replaced,'optimizer_updates_before_this_change':0})
    original.update(lessons=len(lessons),pairs=len(pairs));original['task_counts']['train']=len(read(ROOT/'train.jsonl'))
    original['files']={p.name:sha(p)for p in ROOT.iterdir()if p.suffix in ['.json','.jsonl']and p.name not in ['data-frozen.json','start-launch.json']}
    write(ROOT/'data-frozen.json',original);print(json.dumps({'frozen':True,'lessons':len(lessons),'pairs':len(pairs)}),flush=True)


if __name__=='__main__':main()
