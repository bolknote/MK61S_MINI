"""False-DONE hard negatives and new task-disjoint calibration/exam panels."""
import collections
import copy
import json
import random
import shutil
from ak_common import ROOT,PARENT,INITIAL,INITIAL_PACKET,read,write,sha
from ak_skills import build as skill_pairs
from ah_data import history as older_history
from ai_data import completion_seeds,select
from af_data import seeds as ordinary_seeds
from ha_data import basic_tasks,composite_tasks,algorithm_tasks
from hr_data import boundary_tasks,hard_tasks
from ha_protocol import constants,encode
from ac_data import twin_seeds
from aj_teacher import correct
from full_isa_vm import FullVM
from tasks import BUILD,save_jsonl


def main():
    ROOT.mkdir(exist_ok=True)
    if(ROOT/'data-frozen.json').exists():return
    vm=FullVM();rng=random.Random(131301);seen=older_history()
    for directory in [PARENT,BUILD/'retention-debug-v1/server-results']:
        for p in directory.glob('*.jsonl'):
            if any(x in p.name for x in ['train','development','fresh'])and not any(x in p.name for x in ['seeds','lessons','onpolicy']):
                seen.update((t.get('angle'),t['task'])for t in read(p)if isinstance(t.get('task'),str))
    sources=[]
    for name in ['lessons.jsonl','hard-lessons.jsonl','completion.jsonl','anchors.jsonl','retention.jsonl','onpolicy-union-4.jsonl']:
        rows=read(PARENT/name);rng.shuffle(rows);sources+=rows[:16000 if name=='retention.jsonl'else len(rows)]
    # These viewed exams are now training. Only actual proposed DONE decisions
    # are added here, with correctness determined offline by the ROM grader.
    for prefix in ['initial','lr20','lr10']:
        path=PARENT/('initial-fresh-audit.json'if prefix=='initial'else prefix+'/terminal-fresh-audit.json')
        report=json.loads(path.read_text())
        for part in ['main','skills','goals','completion']:
            for episode in report[part]['raw']['details']:
                if not episode['finished']:continue
                h=next(h for h in reversed(episode['history'])if h.get('generation',{}).get('action')=='done')
                import re
                remaining=int(re.search(r'Осталось действий: (-?\d+)',h['prompt'])[1]);truth=int(episode['program_correct']);eligible=episode['eligible']
                if truth and not eligible:continue
                action='done'if truth else'write'if remaining>1 else'unsure'
                sources.append({'task_id':episode['id'],'prompt':h['prompt'],'action':action,'body':[],
                  'correctness':truth,'eligible_for_DONE':eligible,'origin':'actual_DONE_correct'if truth else'actual_false_DONE',
                  'runtime_has_expected':False})
    pools=collections.defaultdict(list);unique={};conflicts=set()
    for row in sources:
        prompt=row['prompt'];key=(row['action'],bool(row['correctness']),bool(row.get('eligible_for_DONE')))
        if prompt in unique and unique[prompt][0]!=key:conflicts.add(prompt)
        if prompt not in unique or row.get('origin')=='actual_false_DONE':unique[prompt]=(key,row)
    for prompt,(key,row)in unique.items():
        if prompt in conflicts:continue
        ready=row['action']=='done'and row['correctness']and row.get('eligible_for_DONE')
        category='danger'if row.get('origin')=='actual_false_DONE'else'ready'if ready else'checking'if row['correctness']and not row.get('eligible_for_DONE')else'other'
        pools[category].append(row)
    training=[]
    for category,n in [('danger',3000),('ready',3000),('checking',2500),('other',3500)]:
        rng.shuffle(pools[category]);training += [{**r,'risk_group':category}for r in pools[category][:n]]
    assert len(pools['danger'])>=100
    for r in training:
        if r['risk_group']=='danger':r['risk_group']='proposal'
        elif r['risk_group']=='other'and not r['correctness']and r.get('eligible_for_DONE'):r['risk_group']='danger'
    save_jsonl(ROOT/'training-states.jsonl',training)
    for split,kind,n,seed in [('development','validation',80,131302),('fresh','fresh',160,131303)]:
        path=ROOT/(split+'.jsonl')
        if path.exists():tasks=read(path)
        else:
            candidates=[(1,basic_tasks(vm,kind,400,seed)+boundary_tasks(vm,kind,100,seed+1),int(n*.4)),
              (2,composite_tasks(vm,kind,500,seed+2),int(n*.4)),
              (3,algorithm_tasks(vm,kind,300,seed+3)+hard_tasks(vm,kind,80,seed+4),n-2*int(n*.4))]
            tasks=[]
            for level,values,quota in candidates:
                rng.shuffle(values);tasks+=select(values,quota,level,split,seen)
            for t in tasks:t['id']='ak:'+t['id'];assert correct(vm,t,encode(t['reference_code'],t['constants'],'asm'),t['constants'])
            save_jsonl(path,tasks)
        save_jsonl(ROOT/(split+'-seeds.jsonl'),ordinary_seeds(tasks,vm,seed+10))
        selected=[t for level in [1,2,3]for t in[t for t in tasks if t['level']==level][:8 if split=='development'else 16]]
        save_jsonl(ROOT/(split+'-completion-seeds.jsonl'),completion_seeds(selected,2))
        skills=skill_pairs(vm,kind,12 if split=='development'else 24,seed+11,seen)
        save_jsonl(ROOT/(split+'-skills.jsonl'),skills);save_jsonl(ROOT/(split+'-skill-seeds.jsonl'),twin_seeds(skills,seed+12))
        print(json.dumps({'split':split,'main_tasks':len(tasks),'skill_tasks':len(skills)}),flush=True)
    # Positive and negative states are both explicit; the action prior is no
    # longer driven by the frequency of completion examples in a large course.
    policy={'arms':['done','actions'],'trainable_parameters':{'done':128,'actions':640},'steps':1000,'checkpoints':[250,500,1000],
      'batch':256,'lr':.001,'false_DONE_weight':4.,'keep_weight':.5,'head_distance_weight':.1,
      'quotas':{'proposal':64,'danger':64,'ready':64,'checking':32,'other':32},'generator_frozen':True,
      'risk_first_selection':True,'nonregression':['false_DONE','passed','correct_controls_completed'],
      'all_training_in_real_Q4':True,'context':1024,'max_turns':10,'new_controls_frozen_before_SGD':True,
      'old_exams_now_training':True,'no_runtime_veto_or_external_expected_result':True}
    write(ROOT/'policy.json',policy);shutil.copytree(PARENT/'core-source',ROOT/'core-source',dirs_exist_ok=True)
    files={p.name:sha(p)for p in ROOT.iterdir()if p.suffix in ['.json','.jsonl']and p.name!='data-frozen.json'}
    write(ROOT/'data-frozen.json',{'files':files,'training_states':len(training),'risk_groups':dict(collections.Counter(r['risk_group']for r in training)),
      'conflicting_prompts_removed':len(conflicts),'source_master_sha256':sha(INITIAL/'model.safetensors'),'source_packet_sha256':sha(INITIAL_PACKET),
      'generator_parameters_frozen':True,'frozen_before_SGD':True})
    print(json.dumps({'frozen':True,'training_states':len(training),'groups':dict(collections.Counter(r['risk_group']for r in training))}),flush=True)


if __name__=='__main__':main()
