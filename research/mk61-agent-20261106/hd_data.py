"""Full-ISA repetition, counterfactual repair states and a new sealed exam."""
import collections
import copy
import json
import random
import shutil
import time

from hd_common import ROOT,PREVIOUS,INITIAL,INITIAL_PACKET,read,sha,write
from hd_tools import seed,lessons
from ha_data import basic_tasks,composite_tasks,algorithm_tasks
from hr_data import boundary_tasks,hard_tasks
from ha_protocol import constants,assemble
from full_isa_prepare import base_inputs,make_task
from full_isa_vm import FullVM,check_task,state_match
from full_isa_protocol import REGISTERS
from tasks import save_jsonl


def stops(vm,split,rng):
    forms={
      'train':['Останови исполнение командой С/П.','Поручение для МК-61: остановить программу командой С/П; затем остановиться С/П.',
               'Нужна только команда остановки С/П.','Выполни С/П, не меняя X и память.','Введи программный останов С/П.',
               'Ничего не вычисляй: остановись на С/П.','Нужен HEX команды С/П и остановка.',
               'Заверши программу непосредственно командой С/П.','Команда запуска и остановки — С/П; сейчас нужен останов.'],
      'validation':['Составь программу немедленной остановки С/П.','Требуется останов С/П без изменения стека.','Выдай программный С/П.'],
      'fresh':['Программа должна сразу остановиться на С/П.','Не выполняя вычислений, сделай останов С/П.',
               'Исполнение нужно прервать командой С/П.','Первой командой должен быть останов С/П.']}
    rows=[]
    for angle in ['RAD','DEG','GRAD']:
        for text in forms[split]:
            t=make_task(vm,[0x50,0x50],text,f'hd-{split}:stop:{len(rows)}','stop_command',split,angle,
                        [base_inputs(rng)for _ in range(6)],kind='primitive',targets=[0x50],check_pc=True)
            t.update(opcode=0x50,catalog_risk='documented',constants=constants(text),debug_category='stop')
            rows.append(t)
    return rows


def sets(vm,split,spec,seed_):
    rng=random.Random(seed_);rows=[]
    for make,count,offset in [(basic_tasks,spec[0],0),(composite_tasks,spec[1],1),(algorithm_tasks,spec[2],2),
                              (boundary_tasks,spec[3],3),(hard_tasks,spec[4],4)]:
        values=make(vm,split,count,seed_+offset)
        for t in values:
            t['id']=f'hd-{split}:new:{len(rows)}';t['debug_category']='hard'if make==hard_tasks else'math'
            rows.append(t)
    rows+=stops(vm,split,rng)
    return rows


def near_miss(vm,task,item,index):
    """Find a real first input on which the wrong program happens to agree."""
    if item['intentionally_correct']:return None
    rng=random.Random(6120720+index);wrong=item['initial_code'];code=task['reference_code']
    for trial in range(12):
        state=base_inputs(rng)
        if trial<3:
            for r in REGISTERS:state[r]=str(trial)
            state['X']=str(trial)
        expected=vm.execute(code,state,angle=task['angle'])[0]
        if expected['status']!='stopped':continue
        actual=vm.execute(wrong,state,angle=task['angle'])[0]
        if not state_match(actual,expected,names=task.get('check_names'),check_pc=task.get('check_pc',False),raw=task.get('raw_compare',False)):continue
        t=copy.deepcopy(task);t['id']+=':near'
        t['public_tests'][0]={'segments':[{'inputs':state,'expected':expected}]}
        if check_task(vm,wrong,t)['pass']:continue
        # Require another public case to expose the defect, not merely a hidden grader.
        if check_task(vm,wrong,t,public=True)['pass']:continue
        s={**copy.deepcopy(item),'task_id':t['id'],'origin':{'source':'near_miss_first_input_agrees'},'pre_run_all':False,'inspect_first':True}
        return t,s
    return None


def actual_errors(vm):
    tasks={t['id']:t for t in read(PREVIOUS/'fresh.jsonl')};report=json.loads((PREVIOUS/'results/fast-best.json').read_text())
    values=[];seen=set()
    for row in report['language']['details']+report['tools']['details']:
        code=row.get('code');task=tasks.get(row['id'])
        if code is None or task is None or check_task(vm,code,task)['pass']:continue
        key=(task['id'],tuple(code))
        if key in seen:continue
        seen.add(key);t=copy.deepcopy(task);t['id']='hd-observed:'+task['id']+':'+str(len(values));t['split']='train'
        t['debug_category']='observed_error';values.append((t,code))
    return values


def main():
    ROOT.mkdir(exist_ok=True)
    if(ROOT/'data-frozen.json').exists():return
    vm=FullVM();parts={};started=time.monotonic()
    for split,spec,seed_ in [('train',(480,480,240,360,360),6120751),
                              ('validation',(40,40,24,40,40),6120752),('fresh',(80,80,60,80,80),6120753)]:
        path=ROOT/(split+'.jsonl')
        rows=read(path)if path.exists()else sets(vm,split,spec,seed_)
        save_jsonl(path,rows);parts[split]=rows
        print(json.dumps({'split':split,'rows':len(rows),'seconds':time.monotonic()-started}),flush=True)
    episodes=[];extra=[];rng=random.Random(6120754)
    groups=collections.defaultdict(list)
    for t in parts['train']:groups[t['group']].append(t)
    chosen=[]
    for values in groups.values():rng.shuffle(values);chosen+=values[:100]
    for i,t in enumerate(chosen):
        episodes.append(seed(t,vm,i,correct=False))
        if i%2==0:episodes.append(seed(t,vm,i+1,correct=True))
        if i%5==0:
            pair=near_miss(vm,t,episodes[-2]if i%2==0 else episodes[-1],i)
            if pair:extra.append(pair[0]);episodes.append(pair[1])
    for i,(task,wrong)in enumerate(actual_errors(vm)):
        extra.append(task);episodes.append(seed(task,vm,i+10000,wrong=wrong,origin={'initial_checkpoint':'harness-retention-v1/fast-best'}))
        episodes.append(seed(task,vm,i+10001,correct=True))
    parts['train']+=extra;save_jsonl(ROOT/'train.jsonl',parts['train'])
    lookup={t['id']:t for t in parts['train']};tool_rows=[]
    for i,item in enumerate(episodes):
        rows=lessons(lookup[item['task_id']],item,vm)
        for row in rows:row['id']+=f':episode{i}'
        tool_rows+=rows
        if i%200==0:print(json.dumps({'episodes':i,'lessons':len(tool_rows),'seconds':time.monotonic()-started}),flush=True)
    save_jsonl(ROOT/'tool-episodes.jsonl',episodes);save_jsonl(ROOT/'tool-lessons.jsonl',tool_rows)
    for split,per_group in [('validation',4),('fresh',12)]:
        by_group=collections.defaultdict(list)
        for t in parts[split]:by_group[t['group']].append(t)
        items=[];add=[]
        for values in by_group.values():
            rng.shuffle(values)
            for t in values[:per_group]:
                i=len(items);item=seed(t,vm,i+20000,correct=i%4==0);items.append(item)
                if i%5==1:
                    near=near_miss(vm,t,item,i+20000)
                    if near:add.append(near[0]);items.append(near[1])
        parts[split]+=add;save_jsonl(ROOT/(split+'.jsonl'),parts[split]);save_jsonl(ROOT/(split+'-tool-seeds.jsonl'),items)
    names=['catalog.json','output-token-ids.json','isa-audit.jsonl','isa-development.jsonl','legacy-development.jsonl',
           'observed-user-reproductions.jsonl','observed-previous-language.jsonl','retention-floors.json']
    for name in names:shutil.copyfile(PREVIOUS/name,ROOT/name)
    # The known stop regression belongs to observed validation, not a fresh claim.
    dev=read(ROOT/'isa-development.jsonl');ids={t['id']for t in dev}
    dev += [t for t in read(ROOT/'isa-audit.jsonl')if t.get('opcode')in [0x50,0x5F]and t['id']not in ids]
    save_jsonl(ROOT/'isa-development.jsonl',dev)
    shutil.copyfile(PREVIOUS/'fresh.jsonl',ROOT/'observed-retention.jsonl')
    shutil.copyfile(PREVIOUS/'observed-ablation.jsonl',ROOT/'observed-ablation.jsonl')
    shutil.copytree(PREVIOUS/'core-source',ROOT/'core-source',dirs_exist_ok=True)
    light=read(PREVIOUS/'sft-light.jsonl')
    for t in parts['train']:
        small={k:v for k,v in t.items()if k not in ['public_tests','hidden_tests','expression']}
        small['public_tests']=[{'segments':[{'inputs':s['inputs']}for s in case['segments']]}for case in t['public_tests']]
        light.append(small)
    save_jsonl(ROOT/'sft-light.jsonl',light)
    save_jsonl(ROOT/'development.jsonl',parts['validation'])
    policy={'steps_each':3000,'validation_interval':500,'effective_batch':128,'context':1024,'lr':2e-5,
            'embedding_lr_factor':.5,'warmup_updates':100,'weight_decay':.01,'learning_rate_scale':{'safe':.5,'active':1.},
            'quotas':{'tool':64,'semantic':32,'primitive':24,'stop':4,'language':4},'max_tool_turns':6,
            'DONE_gate':'all public cases executed on current revision, stopped status only; no expected state access',
            'selection':'retention guard first, then fewer false DONE and successful repair/completion',
            'no_new_neural_teacher_calls':True,'fresh_used_for_selection':False}
    write(ROOT/'policy.json',policy)
    files=names+['train.jsonl','validation.jsonl','fresh.jsonl','development.jsonl','sft-light.jsonl','tool-episodes.jsonl',
                 'tool-lessons.jsonl','validation-tool-seeds.jsonl','fresh-tool-seeds.jsonl','observed-retention.jsonl','observed-ablation.jsonl','policy.json']
    frozen={'before_optimizer_updates':True,'initial_master_sha256':sha(INITIAL/'model.safetensors'),'initial_packet_sha256':sha(INITIAL_PACKET),
            'files':{n:sha(ROOT/n)for n in files},'counts':{k:len(v)for k,v in parts.items()},'episodes':len(episodes),'tool_lessons':len(tool_rows),
            'actual_error_episodes':sum(s['origin']['source']=='actual_student_error'for s in episodes),
            'near_miss_episodes':sum(s['origin']['source']=='near_miss_first_input_agrees'for s in episodes),
            'private_core_files':{str(p.relative_to(ROOT/'core-source')):sha(p)for p in(ROOT/'core-source').rglob('*')if p.is_file()},
            'old_retention_exam_is_now_observed_and_partly_replayed':True,'synthetic_exam_not_independent_human_benchmark':True,
            'initial_checkpoint_may_have_prior_family_exposure':True,'oracle_answers_in_runtime_feedback':False}
    write(ROOT/'data-frozen.json',frozen);print(json.dumps({k:v for k,v in frozen.items()if k not in ['files','private_core_files']}),flush=True)


if __name__=='__main__':main()
