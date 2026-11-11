"""Composition learning, binding augmentation, matched hard negatives and sealed exams."""
import collections
import copy
import hashlib
import json
import random
import shutil
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
from ae_common import ROOT,OLD,INITIAL,INITIAL_PACKET,COMPILER,COMPILER_PACKET,COMPILER_SOURCE,HERE,read,write,sha
from aa_common import ROOT as AA_ROOT
from ab_common import ROOT as AB_ROOT
from ad_common import ROOT as AD_ROOT
from ha_data import basic_tasks,composite_tasks,algorithm_tasks
from hr_data import boundary_tasks,hard_tasks
from hd_x_data import generate as x_tasks
from ha_protocol import constants,encode
from full_isa_math import literal
from full_isa_vm import FullVM
from full_isa_protocol import linear_instructions
from ac_data import goal_twins,twin_seeds
from ae_teacher import correct,make_session,follow
from tasks import BUILD

_VM=None
def init_worker():
    global _VM
    _VM=FullVM()
def label(value):
    task,seed=value;session=make_session(task,seed,_VM)
    rows=follow(session,task)
    for r in rows:r['binding_permuted']=seed.get('binding_permuted',False);r['pair_id']=seed['pair_id']
    return rows


def wrong(task,vm,salt):
    rng=random.Random(salt);code=list(task['reference_code']);positions=[i['pc']for i in linear_instructions(code)];rng.shuffle(positions)
    for at in positions:
        op=code[at];choices=list(range(10))if op<=9 else list(range(0x60,0x6F))if 0x60<=op<=0x6E else[0x10,0x11,0x12,0x13,0x1C,0x1D,0x22,0x31,0x54]
        rng.shuffle(choices)
        for value in choices[:6]:
            if value==op:continue
            candidate=code[:];candidate[at]=value
            if salt%3==0 and len(positions)>2:
                other=positions[(positions.index(at)+1)%len(positions)]
                if other!=at and candidate[other]!=0x50:candidate[other]=0x54
            if not correct(vm,task,encode(candidate,task['constants'],'asm'),task['constants']):return candidate
    for value in ['999','-999','0','1']:
        candidate=literal(value)+[0x50]
        if not correct(vm,task,encode(candidate,task['constants'],'asm'),task['constants']):return candidate
    raise ValueError('No verified wrong program')


def seeds(tasks,vm,seed,train=False,binding=False):
    rng=random.Random(seed);items=[]
    for i,t in enumerate(tasks):
        pool=t.get('constants')or constants(t['task']);bad=wrong(t,vm,seed+i);good=t['reference_code']
        if not t.get('check_pc')and i%4==0 and len(good)<100:
            candidate=good+[0x54,0x54]
            if correct(vm,t,encode(candidate,pool,'asm'),pool):good=candidate
        versions=[False,True]if train or binding else[False]
        for permuted in versions:
            values=pool[:]
            if permuted:rng.shuffle(values)
            phases=[0,1]if train else[rng.randrange(3)]
            for rev in phases:
                common={'task_id':t['id'],'pair_id':t['id']+f':pool{int(permuted)}:rev{rev}',
                    'pool':values,'binding_permuted':permuted,'prefill_revision':rev,
                    'pre_run_all':rng.random()<.7,'trace_before':rng.random()<.15,
                    'critic_warning':rng.random()<.2,'error_probe':rng.random()<.15,'initial_code':bad}
                for label_,candidate in [(False,bad),(True,good)]:
                    items.append({**common,'candidate_code':candidate,'intentionally_correct':label_})
    return items


def main():
    ROOT.mkdir(exist_ok=True)
    if(ROOT/'data-frozen.json').exists():return
    vm=FullVM();seen=set();sets={}
    for directory in [COMPILER_SOURCE,AA_ROOT,AB_ROOT,OLD,AD_ROOT]:
        if not(directory/'train.jsonl').exists()and(directory/'server-results').exists():directory=directory/'server-results'
        for name in ['train.jsonl','validation.jsonl','fresh.jsonl','development.jsonl','exam.jsonl','training-tasks.jsonl']:
            if(directory/name).exists():
                for t in read(directory/name):
                    if 'task'in t:seen.add((t.get('angle'),t['task']))
    for split,kind,count,seed in [('train','train',2000,711701),('development','validation',160,711702),('fresh','fresh',240,711703)]:
        path=ROOT/(split+'.jsonl')
        if path.exists():sets[split]=read(path);continue
        primitives=[]
        if split=='train':
            by=collections.defaultdict(list)
            for t in read(BUILD/'full-isa-v1/train.jsonl'):
                if t['kind']=='primitive'and t.get('catalog_risk')=='documented'and t['id'].endswith('wording0'):by[t['opcode']].append(t)
            for op,values in sorted(by.items()):
                t=copy.deepcopy(values[op%len(values)]);t.update(required_named_opcodes=[op],level=1)
                t['task']+=' Соблюдай заданную раскладку адресов без дополнительных НОП.';primitives.append(t)
            assert len(primitives)==216
        simple=basic_tasks(vm,kind,count,seed)+boundary_tasks(vm,kind,max(200,count//2),seed+1)
        compositions=composite_tasks(vm,kind,count,seed+2)+x_tasks(vm,kind,min(100,count//3),seed+3)
        hard=hard_tasks(vm,kind,max(80,count//5),seed+4)
        algorithms=algorithm_tasks(vm,kind,max(300,count),seed+5)
        quotas=[(1,primitives+simple,800),(2,compositions,600),(3,hard+algorithms,600)]if split=='train'else[(1,simple,int(count*.4)),(2,compositions,int(count*.4)),(3,hard+algorithms,count-2*int(count*.4))]
        tasks=[];rng=random.Random(seed)
        for level,candidates,limit in quotas:
            if primitives and level==1:
                rest=candidates[len(primitives):];rng.shuffle(rest);candidates=primitives+rest
            else:rng.shuffle(candidates)
            selected=[]
            for t in candidates:
                key=(t['angle'],t['task'])
                if key in seen and t['kind']!='primitive':continue
                seen.add(key);t=copy.deepcopy(t);t.update(id=f'ae:{split}:{len(tasks)+len(selected):05}',level=level,
                    constants=constants(t['task']),require_subroutine=t['group']=='algorithm_subroutine')
                cases=t['public_tests']+t['hidden_tests'];n=1+(len(tasks)+len(selected))%4
                t['public_tests'],t['hidden_tests']=cases[:n],cases[n:]
                assert correct(vm,t,encode(t['reference_code'],t['constants'],'asm'),t['constants'])
                selected.append(t)
                if len(selected)==limit:break
            assert len(selected)==limit,(split,level,len(selected));tasks+=selected
        from tasks import save_jsonl
        save_jsonl(path,tasks);sets[split]=tasks
        print(json.dumps({'split':split,'tasks':len(tasks),'levels':dict(collections.Counter(t['level']for t in tasks))}),flush=True)
    from tasks import save_jsonl
    for split,seed in [('train',711801),('development',711802),('fresh',711803)]:
        path=ROOT/(split+'-seeds.jsonl')
        if not path.exists():save_jsonl(path,seeds(sets[split],vm,seed,train=split=='train'))
    # Additional goal reversals: identical current code/input/facts, opposite labels.
    for split,kind,seed in [('train','train',711901),('development','validation',711902),('fresh','fresh',711903)]:
        path=ROOT/(split+'-twins.jsonl')
        twins=read(path)if path.exists()else goal_twins(vm,kind,40 if split=='train'else 8,seed)
        save_jsonl(path,twins);save_jsonl(ROOT/(split+'-twin-seeds.jsonl'),twin_seeds(twins,seed+1))
    for split,seed in [('development',712002),('fresh',712003)]:
        pool=[t for t in sets[split]if len(t['constants'])>=4][:32]+[t for t in sets[split]if t.get('source_kind')=='R'][:16]
        unique={t['id']:t for t in pool};values=list(unique.values())
        save_jsonl(ROOT/(split+'-binding.jsonl'),values);save_jsonl(ROOT/(split+'-binding-seeds.jsonl'),seeds(values,vm,seed,binding=True))
    jobs=[];lookup={t['id']:t for t in sets['train']}
    jobs+=[(lookup[s['task_id']],s)for s in read(ROOT/'train-seeds.jsonl')]
    twins={t['id']:t for t in read(ROOT/'train-twins.jsonl')};jobs+=[(twins[s['task_id']],s)for s in read(ROOT/'train-twin-seeds.jsonl')]
    lessons=[]
    with ProcessPoolExecutor(max_workers=4,mp_context=multiprocessing.get_context('spawn'),initializer=init_worker)as pool:
        for i,rows in enumerate(pool.map(label,jobs,chunksize=8)):
            lessons+=rows
            if i%1000==0:print(json.dumps({'episodes':i,'lessons':len(lessons)}),flush=True)
    # Body-less and current-program ambiguity cases use independent wording combinations.
    rng=random.Random(712101)
    for i in range(96):
        text=rng.choice(['Нужна программа для X. ','Нужно обработать число из R2. ','Помоги с расчётом на МК-61. ','Найди значение функции. '])+rng.choice([
          'Формулу я ещё не сообщил.','Требуемое действие уточню позже.','Операцию пока не выбрали.','Условие задачи отсутствует.'])
        t=copy.deepcopy(sets['train'][i]);t.update(id=f'ae:unknown:{i}',task=text,constants=constants(text),underspecified=True,level=1)
        seed={'initial_code':[0x50],'candidate_code':[0x50],'start_empty':i%2==0,'pair_id':t['id'],'pre_run_all':True}
        rows=follow(make_session(t,seed,vm),t,'underspecified');lessons+=rows
    save_jsonl(ROOT/'lessons.jsonl',lessons)
    for name in ['isa-audit.jsonl','legacy-development.jsonl','catalog.json']:shutil.copyfile(COMPILER_SOURCE/name,ROOT/name)
    shutil.copytree(COMPILER_SOURCE/'core-source',ROOT/'core-source',dirs_exist_ok=True)
    policy={'warmup_steps':200,'blocks':3,'steps_per_block':1000,'batch':64,'lr_lora':3e-4,'lr_full':2e-5,'lr_action':1e-4,'lr_correct':3e-4,
      'correctness_weight':1.,'incorrect_class_weight':4.,'false_DONE_penalty':1.,'context':1024,'max_turns':10,
      'stage_level_mix':{'1':[.5,.4,.1],'2':[.35,.4,.25],'3':[.3,.4,.3]},
      'curriculum_does_not_wait_for_zero_false_DONE':True,'SFT_no_DPO':True,'paired_same_draws':True,'binding_augmentation':True,
      'shared_warmup_correctness_only':True,'correctness_ids':[8199,8200],'no_semantic_oracle_at_runtime':True,
      'release':{'false_DONE':0,'strict_success':.8,'compiler_ISA':648,'compiler_legacy':69},'actual_Q4_every_update':True}
    write(ROOT/'policy.json',policy)
    files={p.name:sha(p)for p in ROOT.iterdir()if p.suffix in ['.json','.jsonl']and p.name not in ['data-frozen.json','prepare-launch.json','start-launch.json']}
    write(ROOT/'data-frozen.json',{'files':files,'task_counts':{k:len(v)for k,v in sets.items()},'lessons':len(lessons),
        'initial_tool_packet_sha256':sha(INITIAL_PACKET),'initial_tool_master_sha256':sha(INITIAL/'model.safetensors'),
        'compiler_packet_sha256':sha(COMPILER_PACKET),'compiler_master_sha256':sha(COMPILER/'model.safetensors'),
        'frozen_before_SGD':True,'teacher':'authored reference programs verified by full ROM execution plus explicit contracts',
        'runtime_view_excludes_expected_hidden_reference':True})
    print(json.dumps({'data_frozen':True,'lessons':len(lessons)}),flush=True)


if __name__=='__main__':main()
