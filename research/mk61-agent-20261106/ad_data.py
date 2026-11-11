"""Freeze new local development/exam instances before generating candidates."""
import collections
import copy
import json
import random
from ad_common import ROOT,PREVIOUS,MODEL,PRIOR_ROOT,HERE,read,write,save,sha
from aa_common import SOURCE,ROOT as AA_ROOT
from ab_common import ROOT as AB_ROOT
from ha_data import basic_tasks,composite_tasks,algorithm_tasks
from hr_data import boundary_tasks,hard_tasks
from hd_x_data import generate as x_tasks
from ac_data import make_seeds,goal_twins,twin_seeds
from full_isa_vm import FullVM


def main():
    ROOT.mkdir(exist_ok=True)
    if(ROOT/'data-frozen.json').exists():return
    seen=set()
    for directory in [SOURCE,AA_ROOT,AB_ROOT,PREVIOUS]:
        for name in ['train.jsonl','validation.jsonl','fresh.jsonl','development.jsonl','training-tasks.jsonl']:
            if(directory/name).exists():
                for t in read(directory/name):
                    if 'task'in t:seen.add((t.get('angle'),t['task']))
    vm=FullVM();counts={}
    for split,n,seed in [('development',64,1071121),('exam',128,1071122)]:
        kind='validation'if split=='development'else'fresh';rng=random.Random(seed)
        simple=basic_tasks(vm,kind,n*2,seed)+boundary_tasks(vm,kind,n*2,seed+1)
        complex_=composite_tasks(vm,kind,n,seed+2)+hard_tasks(vm,kind,n//2,seed+3)+x_tasks(vm,kind,n//2,seed+4)+algorithm_tasks(vm,kind,n,seed+5)
        tasks=[]
        for level,values in [(1,simple),(2,complex_)]:
            rng.shuffle(values);chosen=[]
            for t in values:
                key=(t['angle'],t['task'])
                if key in seen:continue
                seen.add(key);t=copy.deepcopy(t);t.update(id=f'ad:{split}:{len(tasks)+len(chosen):04}',level=level)
                bank=t['public_tests']+t['hidden_tests'];public=1+(len(tasks)+len(chosen))%4
                t['public_tests'],t['hidden_tests']=bank[:public],bank[public:];chosen.append(t)
                if len(chosen)==n//2:break
            assert len(chosen)==n//2;tasks+=chosen
        seeds=make_seeds(tasks,vm,seed+10)
        save(ROOT/(split+'.jsonl'),tasks);save(ROOT/(split+'-seeds.jsonl'),seeds)
        twins=goal_twins(vm,kind,8,seed+20)
        for t in twins:
            assert(t['angle'],t['task'])not in seen;seen.add((t['angle'],t['task']))
        save(ROOT/(split+'-twins.jsonl'),twins);save(ROOT/(split+'-twin-seeds.jsonl'),twin_seeds(twins,seed+21))
        counts[split]={'tasks':len(tasks),'paired_states':len(seeds),'goal_twin_states':len(twin_seeds(twins,seed+21)),
                       'groups':dict(collections.Counter(t['group']for t in tasks))}
    policy={'candidate_count':4,'temperature':.8,'top_p':.95,'context':1024,'max_turns':10,
       'development_before_selection':True,'exam_not_used_for_selection':True,'inference_only_no_SGD':True,
       'model':'frozen SFT block4 merged Q4','backend':'local CPU FP32 execution of actual Q4 weights',
       'selection_grid':{'prior':['verified_training','combined'],'weight':[.25,.5,1.], 'repeat':[0.,1.], 'unreachable':[0.,1.]},
       'full_harness_arms':['greedy_raw','greedy_guard','best4_likelihood','best4_statistics','best4_feedback'],
       'additional_scratch_tasks':32,'note':'new instances, not all-new mathematical families; past final sets are diagnostic only'}
    write(ROOT/'policy.json',policy)
    frozen={p.name:sha(p)for p in ROOT.iterdir()if p.suffix in ['.json','.jsonl']and p.name!='data-frozen.json'}
    write(ROOT/'data-frozen.json',{'files':frozen,'counts':counts,'model_packet_sha256':sha(MODEL/'model.mkqb'),
       'compiler_packet_sha256':sha(PREVIOUS/'export/compiler/model.mkqb'),'prior_files':{p.name:sha(p)for p in PRIOR_ROOT.glob('*-counts.json')},
       'created_before_model_generation':True,'fresh_numeric_instances_with_shared_families':True})
    print(json.dumps(counts,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
