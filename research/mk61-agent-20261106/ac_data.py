"""Matched real states, failed repairs, goal counterfactuals, sealed exams."""
import collections
import copy
import hashlib
import json
import random
import shutil
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
from transformers import AutoTokenizer
from ac_common import ROOT,SOURCE,INITIAL,INITIAL_PACKET,HERE,read,write,sha,output_ids
from aa_common import ROOT as AA_ROOT
from ab_common import ROOT as AB_ROOT
from aa_data import repartition
from ha_data import basic_tasks,composite_tasks,algorithm_tasks,verified
from hr_data import boundary_tasks,hard_tasks
from hd_x_data import generate as x_tasks
from ha_tools import corrupt
from ha_protocol import constants,encode
from full_isa_math import literal,UNARY
from full_isa_vm import FullVM,check_task
from full_isa_prepare import make_task,base_inputs
from ac_teacher import make_session,follow,preference
from tasks import BUILD,save_jsonl

_VM=None


def worker_init():
    global _VM
    _VM=FullVM()


def label(value):
    task,seed=value;s=make_session(task,seed,_VM)
    return follow(s),preference(task,seed,_VM)


def wrong_code(task,vm,salt):
    try:code,_=corrupt(task,vm,salt)
    except AssertionError:
        for v in ['999','-999','0','1']:
            code=literal(v)+[0x50]
            if not check_task(vm,code,task)['pass']:break
        else:raise RuntimeError('No true negative')
    assert not check_task(vm,code,task)['pass']
    return code


def make_seeds(tasks,vm,seed,train=False):
    rng=random.Random(seed);items=[]
    for i,t in enumerate(tasks):
        bad=wrong_code(t,vm,seed+i);good=t['reference_code']
        if not t.get('check_pc')and len(good)<105 and i%3==0:
            candidate=[0x54]+good
            if check_task(vm,candidate,t)['pass']:good=candidate
        # Every correctness pair has exactly the same revision/run/trace schedule.
        phases=[0,1,2]if train else [rng.randrange(3)]
        for rev in phases:
            common={'task_id':t['id'],'pair_id':t['id']+f':phase{rev}',
                    'prefill_revision':rev,'pre_run_all':rng.random()<.65,'trace_before':rng.random()<.2}
            for correct,code in [(False,bad),(True,good)]:
                items.append({**common,'initial_code':bad,'candidate_code':code,'intentionally_correct':correct,
                              'after_deliberately_failed_write':bool(rev and not correct)})
    return items


def goal_twins(vm,split,count,seed):
    rng=random.Random(seed);out=[]
    functions=[('sin','cos'),('square','abs'),('neg','abs')]
    for i in range(count):
        a,b=functions[i%len(functions)];n=str(rng.randrange(2,89))+'.'+str(rng.randrange(1,99)).zfill(2)
        angle=rng.choice(['DEG','RAD','GRAD']);inputs=[base_inputs(rng)for _ in range(6)]
        peers=[]
        for op in [a,b]:
            from natural_data import NAMES
            wording={'train':'Вычисли {f} числа {n}.','validation':'Получи {f} от {n}.','fresh':'Требуется {f}; аргумент равен {n}.'}[split]
            text=wording.format(f=NAMES[op],n=n)+' Память R0–RE сохрани.'
            code=literal(n)+[UNARY[op],0x50]
            t=make_task(vm,code,text,f'ac-{split}:twin:{i}:{op}','goal_counterfactual',split,angle,copy.deepcopy(inputs),
                        kind='ha_task',check_names=['X',*[f'R{x:X}'for x in range(15)]])
            t.update(constants=constants(text),level=1,goal_twin_group=f'{split}:twin:{i}')
            peers.append(t)
        cases=peers[0]['public_tests']+peers[0]['hidden_tests'];public=1+i%4
        for t in peers:
            cases=t['public_tests']+t['hidden_tests'];t['public_tests'],t['hidden_tests']=cases[:public],cases[public:]
            t['twin_current_code']=peers[0]['reference_code'];out.append(t)
    return out


def twin_seeds(tasks,seed):
    rng=random.Random(seed);out=[]
    groups=collections.defaultdict(list)
    for t in tasks:
        if 'goal_twin_group'in t:groups[t['goal_twin_group']].append(t)
    for group,peers in groups.items():
        for code_index,source in enumerate(peers):
            for rev in [0,1]:
                common={'pair_id':group+f':code{code_index}:rev{rev}','prefill_revision':rev,'pre_run_all':True,'trace_before':rng.random()<.2,
                        'initial_code':source['reference_code'],'candidate_code':source['reference_code']}
                for t in peers:
                    out.append({**common,'task_id':t['id'],'intentionally_correct':t is source,
                                'same_code_inputs_facts_different_goal':True})
    return out


def main():
    ROOT.mkdir(exist_ok=True)
    if(ROOT/'data-frozen.json').exists():return
    tokenizer=AutoTokenizer.from_pretrained(INITIAL,local_files_only=True);vm=FullVM();seen=set()
    for source in [SOURCE,AA_ROOT,AB_ROOT]:
        for n in ['train.jsonl','validation.jsonl','fresh.jsonl','training-tasks.jsonl']:
            if(source/n).exists():seen.update((t['angle'],t['task'])for t in read(source/n))
    sets={}
    for split,seed in [('train',811121),('validation',811122),('fresh',811123)]:
        path=ROOT/(split+'.jsonl')
        if path.exists():sets[split]=read(path);continue
        n=600 if split=='train'else 140
        simple=basic_tasks(vm,split,n,seed)+boundary_tasks(vm,split,n//2,seed+1)
        # Documented instruction families remain represented; no seven-opcode limit.
        primitives=[]
        if split=='train':
            primitives=[t for t in read(BUILD/'full-isa-v1/train.jsonl')if t['kind']=='primitive'and t.get('catalog_risk')=='documented'and t['id'].endswith('wording0')]
            # One training instance of every documented opcode, with rotating modes.
            byop=collections.defaultdict(list)
            for t in primitives:byop[t['opcode']].append(t)
            primitives=[byop[op][op%len(byop[op])]for op in sorted(byop)]
            assert len(primitives)==216
            for t in primitives:
                t['task']+=' Сохрани заданную раскладку адресов; дополнительных НОП перед остановом быть не должно.'
            simple=primitives+simple
        complex_=composite_tasks(vm,split,400 if split=='train'else 140,seed+2)
        complex_+=hard_tasks(vm,split,120 if split=='train'else 70,seed+3)
        complex_+=x_tasks(vm,split,100 if split=='train'else 30,seed+4)+algorithm_tasks(vm,split,60 if split=='train'else 30,seed+5)
        values=[]
        for level,candidates,limit in [(1,simple,900 if split=='train'else 100),(2,complex_,500 if split=='train'else 100 if split=='validation'else 150)]:
            rng=random.Random(seed+level)
            if split=='train'and level==1:
                rest=candidates[len(primitives):];rng.shuffle(rest);candidates=primitives+rest
            else:rng.shuffle(candidates)
            chosen=[]
            for t in candidates:
                key=(t['angle'],t['task'])
                if key in seen and t['kind']!='primitive':continue
                pc=t.get('check_pc',False)
                t=repartition(t,len(values)+len(chosen),split)
                t['id']='ac-'+t['id'];t['level']=level
                # Do not weaken explicit primitive fixtures' PC contract.
                if t['kind']=='primitive':t['check_pc']=pc
                seen.add(key);chosen.append(t)
                if len(chosen)==limit:break
            assert len(chosen)==limit,(split,level,len(chosen),limit)
            values+=chosen
        if split=='train':values+=goal_twins(vm,split,80,seed+20)
        save_jsonl(path,values);sets[split]=values
        print(json.dumps({'split':split,'tasks':len(values)}),flush=True)
    # Additional matched goals are kept in their own closed probes.
    for split,seed in [('validation',811222),('fresh',811223)]:
        twins=goal_twins(vm,split,20,seed);save_jsonl(ROOT/(split+'-goal-twins.jsonl'),twins)
        save_jsonl(ROOT/(split+'-twin-seeds.jsonl'),twin_seeds(twins,seed+1))
    for split,seed in [('train',811321),('validation',811322),('fresh',811323)]:
        tasks=sets[split];items=make_seeds(tasks,vm,seed,train=split=='train')
        if split=='train':items+=twin_seeds(tasks,seed+1)
        save_jsonl(ROOT/(split+'-seeds.jsonl'),items)
    lessons=[];preferences=[];tasks={t['id']:t for t in sets['train']};items=read(ROOT/'train-seeds.jsonl')
    with ProcessPoolExecutor(max_workers=4,mp_context=multiprocessing.get_context('spawn'),initializer=worker_init)as pool:
        for i,(rows,pair)in enumerate(pool.map(label,((tasks[x['task_id']],x)for x in items),chunksize=8)):
            lessons+=rows;preferences.append(pair)
            if i%1000==0:print(json.dumps({'labelled_episodes':i,'lessons':len(lessons),'preferences':len(preferences)}),flush=True)
    # Explicit ambiguity supervision uses no hidden expected value in its input.
    from ac_runtime import Session
    for i,text in enumerate(['Вычисли функцию от X. Какую функцию, я пока не указал.',
                             'Напиши расчёт результата; формулу сообщу позже.',
                             'Нужно обработать R1, требуемая операция ещё не задана.',
                             'Найди результат для числа 22. Выражение пока отсутствует.']):
        t=copy.deepcopy(sets['train'][i]);t.update(task=text,constants=constants(text),underspecified=True,level=1,id=f'ac-unknown:{i}')
        seed={'task_id':t['id'],'initial_code':[0x50],'candidate_code':[0x50],'intentionally_correct':False,'pre_run_all':True}
        s=make_session(t,seed,vm);lessons.append({'task_id':t['id'],'prompt':s.request(),'action':'unsure','body':[],'level':1,'origin':'underspecified'})
        preferences.append(preference(t,seed,vm))
    save_jsonl(ROOT/'lessons.jsonl',lessons);save_jsonl(ROOT/'preferences.jsonl',preferences)
    for n in ['catalog.json','isa-audit.jsonl','legacy-development.jsonl']:shutil.copyfile(SOURCE/n,ROOT/n)
    shutil.copytree(SOURCE/'core-source',ROOT/'core-source',dirs_exist_ok=True)
    write(ROOT/'output-token-ids.json',output_ids(tokenizer))
    policy={'rank':4,'alpha':8,'trainable_parameters':18560,'warmup_steps':200,'blocks':4,'steps_per_block':600,
            'lr':3e-4,'batch':64,'pref_pairs_per_update':2,'dpo_beta':.1,'dpo_weight':.1,'body_loss_weight':1.,
            'context':1024,'max_turns':10,'initial_curriculum_level':1,
            'advance_gate':{'simple_repair_rate':.9,'simple_correct_control_rate':.95,'false_DONE':0},
            'release':{'false_DONE':0,'strict_success_rate':.8,'compiler_ISA':648,'compiler_legacy':69},
            'compiler_frozen_and_adapter_off':True,'Q4_merged_forward_from_first_update':True,
            'preference_scope':'sum action and all argument token log-probabilities over full actual execution trajectories',
            'same_SFT_draws':True,'fresh_used_for_selection':False,'no_task_ID_teacher_actions':True,
            'failed_repairs_matched_to_successful_repairs':True,'single_weight_buffer_role_switch':True}
    write(ROOT/'policy.json',policy)
    files=[p for p in ROOT.iterdir()if p.suffix in ['.json','.jsonl']and p.name not in ['data-frozen.json','prepare-launch.json','start-launch.json']]
    write(ROOT/'data-frozen.json',{'files':{p.name:sha(p)for p in files},'initial_master_sha256':sha(INITIAL/'model.safetensors'),
            'initial_packet_sha256':sha(INITIAL_PACKET),'lessons':len(lessons),'preferences':len(preferences),
            'task_counts':{s:len(v)for s,v in sets.items()},'frozen_before_optimizer_updates':True,
            'new_exact_final_task_texts':True,'reference_outputs_in_runtime':False})
    print(json.dumps({'data_frozen':True,'lessons':len(lessons),'preferences':len(preferences)}),flush=True)


if __name__=='__main__':main()
