"""Freeze corrected, disjoint task texts and variable-size public input sets."""
import collections
import copy
import hashlib
import json
import random
import shutil
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
from transformers import AutoTokenizer
from aa_common import ROOT, BASE, SOURCE, INITIAL, INITIAL_PACKET, HERE, read, write, sha, output_ids
from aa_teacher import trajectory
from ha_data import basic_tasks, composite_tasks, algorithm_tasks
from hr_data import boundary_tasks, hard_tasks
from hd_x_data import generate as x_tasks
from ha_tools import corrupt
from full_isa_vm import FullVM, check_task
from full_isa_math import literal
from tasks import save_jsonl

_WORKER_VM=None
_WORKER_TOKENIZER=None


def worker_init():
    global _WORKER_VM,_WORKER_TOKENIZER
    _WORKER_VM=FullVM()
    _WORKER_TOKENIZER=AutoTokenizer.from_pretrained(INITIAL,local_files_only=True)


def label_episode(value):
    task,item=value
    return trajectory(task,item,_WORKER_VM,_WORKER_TOKENIZER)


def repartition(task, index, split):
    t = copy.deepcopy(task)
    t['id'] = f'aa-{split}:{index:05d}'
    t['split'] = split
    cases = t['public_tests'] + t['hidden_tests']
    random.Random(712000+index+{'train':0,'validation':100000,'fresh':200000}[split]).shuffle(cases)
    n = 1 + index%4
    t['public_tests'],t['hidden_tests'] = cases[:n],cases[n:]
    # Match the stated semantic contract; PC is not an implicit requirement.
    if t.get('check_pc') and 'перв' not in t['task'].lower() and 'одн' not in t['task'].lower():
        t['check_pc'] = False
    if t.get('check_names') and any(x.startswith('R') for x in t['check_names']) and not any(w in t['task'].lower() for w in ['памят','регистр']):
        t['task'] += ' Регистры памяти R0–RE сохрани.'
    return t


def seeds(tasks, vm):
    out=[]
    for i,t in enumerate(tasks):
        try: wrong, origin = corrupt(t, vm, salt=712301+i)
        except AssertionError:
            # With one public case, both NOP and clear-X can coincidentally match.
            # Find a genuinely wrong program instead of labelling either negative.
            for value in ['999','-999','0','1','2']:
                wrong=literal(value)+[0x50]
                if not check_task(vm,wrong,t)['pass']:break
            else:raise RuntimeError('Could not build a semantic negative')
            origin={'source':'verified_constant_counterexample','constant':value}
        assert not check_task(vm,wrong,t)['pass']
        # Exactly one wrong and one correct episode per task, balanced public counts.
        out.append({'task_id':t['id'],'initial_code':wrong,'intentionally_correct':False,'origin':origin,'pre_run_all':i%2==0})
        code=t['reference_code']
        # NOP alternatives are valid when no exact PC/length contract was stated.
        if i%3==0 and len(code)<105 and not t.get('check_pc'):
            candidate=[0x54]+code
            if check_task(vm,candidate,t)['pass']: code=candidate
        out.append({'task_id':t['id'],'initial_code':code,'intentionally_correct':True,
                    'origin':{'source':'semantically_correct_control','alternative':code!=t['reference_code']},'pre_run_all':i%2!=0})
    return out


def main():
    ROOT.mkdir(exist_ok=True)
    if (ROOT/'data-frozen.json').exists(): return
    tokenizer=AutoTokenizer.from_pretrained(INITIAL,local_files_only=True)
    vm=FullVM();seen=set();sets={}
    for name in ['train.jsonl','validation.jsonl','fresh.jsonl','sft-light.jsonl']:
        for t in read(BASE/name): seen.add((t['angle'],t['task']))
    for split,seed in [('train',712111),('validation',712112),('fresh',712113)]:
        path=ROOT/(split+'.jsonl')
        if path.exists():
            rows=read(path);seen.update((t['angle'],t['task'])for t in rows);sets[split]=rows;continue
        multiplier=3 if split=='train' else 1
        candidates=basic_tasks(vm,split,120*multiplier,seed)+boundary_tasks(vm,split,80*multiplier,seed+1)
        candidates+=composite_tasks(vm,split,80*multiplier,seed+2)+hard_tasks(vm,split,60*multiplier,seed+3)
        candidates+=x_tasks(vm,split,100 if split=='train' else 35,seed+4)+algorithm_tasks(vm,split,40*multiplier,seed+5)
        random.Random(seed+6).shuffle(candidates)
        rows=[];target=1000 if split=='train' else 250
        # Keep the same task family mix in train/development/final exam.
        for t in candidates:
            key=(t['angle'],t['task'])
            if key in seen: continue
            seen.add(key);rows.append(repartition(t,len(rows),split))
            if len(rows)>=target: break
        if len(rows)<target: raise RuntimeError(f'Too few independent tasks {split}: {len(rows)}')
        save_jsonl(path,rows);sets[split]=rows
        print(json.dumps({'data_split':split,'tasks':len(rows)},ensure_ascii=False),flush=True)
    for name in ['catalog.json','isa-audit.jsonl','legacy-development.jsonl']:
        shutil.copyfile(BASE/name,ROOT/name)
    shutil.copytree(BASE/'core-source',ROOT/'core-source',dirs_exist_ok=True)
    train=read(BASE/'train.jsonl')
    # Training replay keeps original reference fixtures but now varies public count.
    train=[repartition(t,i+10000,'train')for i,t in enumerate(train)]+sets['train']
    save_jsonl(ROOT/'training-tasks.jsonl',train)
    all_lessons=[]
    for split in ['train','validation','fresh']:
        tasks=sets[split] if split!='train' else train
        items=seeds(tasks,vm);save_jsonl(ROOT/(split+'-seeds.jsonl'),items)
        if split=='train':
            lookup={t['id']:t for t in tasks}
            with ProcessPoolExecutor(max_workers=4,mp_context=multiprocessing.get_context('spawn'),initializer=worker_init)as pool:
                jobs=((lookup[item['task_id']],item)for item in items)
                for i,values in enumerate(pool.map(label_episode,jobs,chunksize=8)):
                    all_lessons+=values
                    if i%500==0:print(json.dumps({'expert_episodes':i,'lessons':len(all_lessons)}),flush=True)
    # Ambiguity is supervised explicitly, not used to label all difficult tasks UNSURE.
    unclear=['Вычисли нужную функцию от X. Какую функцию, я пока не указал.',
             'Напиши программу для расчёта результата; формулу сообщу позже.',
             'Нужно обработать R1. Требуемая операция ещё не задана.',
             'Вычисли синус. Аргумент и единицы угла пока неизвестны.']
    for i in range(32):
        t=copy.deepcopy(train[i]);t['task']=unclear[i%4];t['underspecified']=True
        from aa_runtime import initial_prompt
        all_lessons.append({'task_id':f'unclear-train:{i}','prompt':initial_prompt(t),'action':'unsure','body':[],
                            'rejected':'done','bucket':'underspecified','origin':'underspecified_contract'})
    save_jsonl(ROOT/'expert-lessons.jsonl',all_lessons)
    save_jsonl(ROOT/'replay-light.jsonl',read(BASE/'sft-light.jsonl'))
    write(ROOT/'output-token-ids.json',output_ids(tokenizer))
    policy={'context':1024,'batch':128,'format_warmup_steps':600,'stages':4,'steps_per_stage':400,
            'warmup_lr':2e-5,'lr':1e-5,'action_embedding_lr_factor':4.,'weight_decay':.01,
            'body_loss_weight':.5,'action_loss_weight':1.,'dpo_beta':.2,'dpo_weight':.5,'dpo_rows':24,
            'seed':712411,'max_turns':10,'mining_episodes_per_arm_per_stage':160,
            'shared_on_policy_union':True,'same_sft_draws_both_arms':True,
            'release':{'validation_episodes':500,'false_DONE':0,'strict_solved_rate_min':.8,
                       'documented_opcodes_required':648,'legacy_min':66},
            'selection_order':['release_eligible','solved_minus_false_DONE','minus_false_DONE','legacy'],
            'fresh_used_for_selection':False,'action_preferences_only':True}
    write(ROOT/'policy.json',policy)
    files=[p for p in ROOT.iterdir()if p.suffix in ['.json','.jsonl']and p.name!='data-frozen.json']
    frozen={'files':{p.name:sha(p)for p in files},'initial_master_sha256':sha(INITIAL/'model.safetensors'),
            'initial_packet_sha256':sha(INITIAL_PACKET),'new_counts':{s:len(t)for s,t in sets.items()},
            'training_task_count':len(train),'expert_lessons':len(all_lessons),
            'lesson_actions':dict(collections.Counter(t['action']for t in all_lessons)),
            'original_exam_results_unchanged':True,'new_exact_task_texts_disjoint_from_v3':True,
            'public_cases_1_to_4':True,'frozen_before_updates':True,'semantic_alternative_programs_accepted':True}
    write(ROOT/'data-frozen.json',frozen);print(json.dumps(frozen['lesson_actions']),flush=True)


if __name__=='__main__':main()
