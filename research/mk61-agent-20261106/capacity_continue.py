"""Preserve the matched pilot and recover formal replay before precision trials."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import time

from capacity_round import ROOT,CAP,REL,INITIAL,status,prepare,assess
from run_experiment import BASE,REPO,SCRIPT,run


def replay():
    path=ROOT/'recovery-replay.jsonl'
    if path.exists():return
    rng=random.Random(6111101);rows=[];counts={}
    for filename,kind in [('sft-train.jsonl','synthesis'),('control-v2-sft.jsonl',None)]:
        pool=[json.loads(s)for s in(BASE/'training'/filename).read_text().splitlines()]
        if kind:pool=[x for x in pool if x['kind']==kind]
        rng.shuffle(pool);pool=pool[:3500]
        for x in pool:
            rows.append({**x,'prompt':re.sub(r'<plan>.*?</plan>','',x['prompt'],flags=re.S),
                         'answer':re.sub(r'<plan>.*?</plan>','',x['answer'],flags=re.S)})
        counts[filename]=len(pool)
    rng.shuffle(rows);path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n'for r in rows))
    (ROOT/'recovery-policy.json').write_text(json.dumps({'reason':'Observed loss of composed arithmetic; initial replay contained control tasks only',
      'new_teacher_or_manual_evaluation_text_in_replay':False,'source_counts':counts,'replay_fraction':.3,'steps_per_size':2000,
      'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'fresh_opened':False},indent=2)+'\n')


def continuation(arm,label,initial,level,mode='q4',steps=2000):
    output=CAP+label
    run('capacity-v1/'+label+'.log',SCRIPT+'capacity_train.py','--initial',initial,'--root',CAP,
        '--output',output,'--level',str(level),'--steps',str(steps),'--format',mode,
        '--lr','3e-5','--eval-every','250'if steps==500 else'500',
        '--replay-file',CAP+'recovery-replay.jsonl','--replay-fraction','.3')
    return output+'/best'


def arm_job(arm,phase):
    if phase=='recovery':continuation(arm,arm+'-recovery',CAP+arm+'-stage1/last',1)
    elif phase=='stage2':
        choice=json.loads((ROOT/'stage1-recovered.json').read_text())
        continuation(arm,arm+'-stage2',choice['models'][arm],2,steps=4000)
    elif phase=='precision':
        choice=json.loads((ROOT/'capacity-selected.json').read_text());level=choice['level'];model=choice['models'][arm]
        for mode in ['q3','q2','mixed']:
            assess(model,arm+'-'+mode+'-ptq-validation',level,mode,'validation')
            trained=continuation(arm,arm+'-'+mode+'-qat',model,level,mode,500)
            assess(trained,arm+'-'+mode+'-qat-validation',level,mode,'validation')
    else:
        choice=json.loads((ROOT/'preselected.json').read_text());level=choice['level'];model=choice['models'][arm]
        for mode in ['fp32','q4']:assess(model,arm+'-'+mode+'-fresh',level,mode,'fresh')
        for mode in ['q3','q2','mixed']:
            assess(model,arm+'-'+mode+'-ptq-fresh',level,mode,'fresh')
            assess(CAP+arm+'-'+mode+'-qat/best',arm+'-'+mode+'-qat-fresh',level,mode,'fresh')


def parallel(phase):
    def worker(arm,gpu):
        with(ROOT/(arm+'-'+phase+'-controller.log')).open('a')as log:
            r=subprocess.run([sys.executable,'-u',SCRIPT+'capacity_continue.py','--arm',arm,'--phase',phase],
                cwd=REPO,env={**os.environ,'MK61_AGENT_GPU':str(gpu)},stdout=log,stderr=subprocess.STDOUT)
        if r.returncode:raise RuntimeError('Failed '+arm+' '+phase)
    with ThreadPoolExecutor(max_workers=2)as pool:
        futures=[pool.submit(worker,a,g)for a,g in [('small',0),('grown',1)]]
        for f in futures:f.result()


def best_record(folder):
    report=json.loads((ROOT/folder/'training.json').read_text())
    return next(r for r in report['history']if r['step']==report['best_step'])


def main():
    p=argparse.ArgumentParser();p.add_argument('--arm',choices=['small','grown']);p.add_argument('--phase');a=p.parse_args()
    if a.arm:arm_job(a.arm,a.phase);return
    lock=(ROOT/'controller.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    status('waiting_for_matched_stage1_to_finish',recovery_planned=True)
    started=time.monotonic()
    while not all((ROOT/(a+'-stage1/training.json')).exists()for a in INITIAL):
        if time.monotonic()-started>3600:raise TimeoutError('Stage1 did not complete')
        time.sleep(10)
    replay();status('matched_formal_recovery',steps_each=2000,replay_fraction=.3);parallel('recovery')
    models={};records={}
    for arm in INITIAL:
        # The old parent is a regression control, not a useful untrained parser
        # to substitute for the trained candidate in a capacity/precision test.
        # Recovery includes its own zero-step (stage1/last) fallback. Any failed
        # formal guard remains explicit and still prevents stage2 progression.
        folder=arm+'-recovery'
        models[arm]=CAP+folder+'/best';records[arm]=best_record(folder)
    reached=any(r['gate']for r in records.values())
    (ROOT/'stage1-recovered.json').write_text(json.dumps({'models':models,'records':records,'gate_met':reached},indent=2)+'\n')
    if reached:
        status('teacher_level2_generation')
        if not(ROOT/'teacher-level2/teacher-manifest.json').exists():
            with(ROOT/'teacher-level2.log').open('a')as log:
                subprocess.run([sys.executable,'-u',SCRIPT+'course_teacher.py','--root',CAP+'teacher-level2','--level','2','--workers','4'],cwd=REPO,stdout=log,stderr=subprocess.STDOUT,check=True)
        prepare(2);status('matched_stage2_training',steps_each=4000);parallel('stage2')
        models={arm:CAP+arm+'-stage2/best'for arm in INITIAL}
    level=2 if reached else 1
    choice={'level':level,'models':models,'stage1_gate_met':reached,'fresh_opened':False,
      'matched_updates_per_size':6000+(4000 if reached else 0),'formal_recovery_before_precision':True}
    (ROOT/'capacity-selected.json').write_text(json.dumps(choice,indent=2)+'\n')
    status('low_bit_ptq_and_matched_qat',formats=['q3','q2','mixed'],steps_each=500);parallel('precision')
    formats={}
    for arm,model in models.items():
        primary=assess(model,arm+'-q4-final-validation',level,'q4','validation')
        candidates=[{'format':'q4','kind':'primary','model':model,'key':primary['key'],'packed':primary['packed']}]
        for mode in ['q3','q2','mixed']:
            for kind in ['ptq','qat']:
                r=json.loads((ROOT/'results'/(arm+'-'+mode+'-'+kind+'-validation.json')).read_text())
                candidates.append({'format':mode,'kind':kind,'model':r['model'],'key':r['key'],'packed':r['packed']})
        within=[r for r in candidates if r['packed']['bytes']<=int(1.8*1024**2)]
        formats[arm]={'all':candidates,'best_any_weight_size':max(candidates,key=lambda r:r['key']),
                     'best_under_1_8_mib_weights':max(within,key=lambda r:r['key'])}
    selected={**choice,'formats':formats,'selection':'Validation only; formal guard, worst parse/program partition, mean score',
      'weight_only_comparison_ceiling_bytes':int(1.8*1024**2),'ceiling_is_experimental_not_complete_device_RAM':True,
      'closed_fresh_hashes':json.loads((ROOT/'frozen.json').read_text())['files']}
    (ROOT/'preselected.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2)+'\n')
    status('final_fresh_scoring',selection_frozen=True);parallel('final')
    summary={p.stem:{k:v for k,v in json.loads(p.read_text()).items()if k!='metrics'}for p in sorted((ROOT/'results').glob('*.json'))}
    (ROOT/'comparison.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'complete.json').write_text(json.dumps({'completed':True,'selection_used_fresh':False,'level':level,'stage1_gate_met':reached,
      'formal_recovery':True,'native_runtime_measured':False,'result_files':len(summary)},indent=2)+'\n')
    status('complete',level=level,stage1_gate_met=reached)


if __name__=='__main__':
    try:main()
    except BaseException as e:
        if '--arm'not in sys.argv:status('failed',error=str(e))
        raise
