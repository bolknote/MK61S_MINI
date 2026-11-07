"""Complete the capacity comparison and precision matrix in an isolated folder."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from run_experiment import run,SCRIPT,BASE,REPO

ROOT=BASE/'capacity-v1';REL='.build/mk61-agent-20261106/';CAP=REL+'capacity-v1/'
INITIAL={'small':REL+'distill-v1/direct-clean/best','grown':CAP+'grown-initial/hf'}


def status(phase,**extra):
    value={'phase':phase,'unix':time.time(),**extra};(ROOT/'status.json').write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps(value),flush=True)


def train(arm,level,initial,mode='q4',steps=4000):
    label=arm+f'-stage{level}'if mode=='q4'else arm+'-'+mode+'-qat'
    output=CAP+label
    run('capacity-v1/'+label+'.log',SCRIPT+'capacity_train.py','--initial',initial,'--root',CAP,
        '--output',output,'--level',str(level),'--steps',str(steps),'--format',mode,
        '--lr','6e-5'if mode=='q4'else'3e-5','--eval-every','500'if mode=='q4'else'250')
    return output+'/best'


def assess(model,label,level,mode,split):
    output=ROOT/'results'/(label+'.json')
    if output.exists():return json.loads(output.read_text())
    run('capacity-v1/'+label+'.log',SCRIPT+'course_eval.py','--model',model,'--root',CAP,
        '--output',str(output.relative_to(REPO)),'--level',str(level),'--format',mode,'--split',split)
    return json.loads(output.read_text())


def parallel(phase):
    def worker(arm,gpu):
        env={**os.environ,'MK61_AGENT_GPU':str(gpu)}
        with(ROOT/(arm+'-'+phase+'-controller.log')).open('a')as log:
            result=subprocess.run([sys.executable,'-u',SCRIPT+'capacity_round.py','--arm',arm,'--phase',phase],
                                  cwd=REPO,env=env,stdout=log,stderr=subprocess.STDOUT)
        if result.returncode:raise RuntimeError('Failed '+arm+' '+phase)
    with ThreadPoolExecutor(max_workers=2)as pool:
        futures=[pool.submit(worker,arm,gpu)for arm,gpu in [('small',0),('grown',1)]]
        for future in futures:future.result()


def arm_job(arm,phase):
    if phase=='stage1':
        assess(INITIAL[arm],arm+'-initial-validation',1,'q4','validation')
        train(arm,1,INITIAL[arm])
    elif phase=='stage2':train(arm,2,CAP+arm+'-stage1/best')
    elif phase=='precision':
        choice=json.loads((ROOT/'capacity-selected.json').read_text());level=choice['level'];model=choice['models'][arm]
        for mode in ['q3','q2','mixed']:
            assess(model,arm+'-'+mode+'-ptq-validation',level,mode,'validation')
            trained=train(arm,level,model,mode,500)
            assess(trained,arm+'-'+mode+'-qat-validation',level,mode,'validation')
    else:
        selected=json.loads((ROOT/'preselected.json').read_text());level=selected['level'];model=selected['models'][arm]
        for mode in ['fp32','q4']:
            assess(model,arm+'-'+mode+'-fresh',level,mode,'fresh')
        for mode in ['q3','q2','mixed']:
            # PTQ and QAT are both reported; neither fresh score changes selection.
            assess(model,arm+'-'+mode+'-ptq-fresh',level,mode,'fresh')
            assess(CAP+arm+'-'+mode+'-qat/best',arm+'-'+mode+'-qat-fresh',level,mode,'fresh')


def prepare(level):
    run('capacity-v1/prepare-level'+str(level)+'.log',SCRIPT+'course_prepare.py','--root',CAP,'--level',str(level))


def main():
    p=argparse.ArgumentParser();p.add_argument('--arm',choices=['small','grown']);p.add_argument('--phase');a=p.parse_args()
    ROOT.mkdir(parents=True,exist_ok=True)
    if a.arm:arm_job(a.arm,a.phase);return
    lock=(ROOT/'controller.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if(ROOT/'complete.json').exists():print('Experiment already complete');return
    status('waiting_for_teacher_level1')
    start=time.monotonic()
    while not(ROOT/'teacher-level1/teacher-manifest.json').exists():
        if(ROOT/'teacher-level1/insufficient-data.json').exists():raise ValueError('Teacher corpus insufficient')
        if time.monotonic()-start>7200:raise TimeoutError('Teacher level1 did not complete')
        time.sleep(10) # Detached controller only; does not block conversation.
    status('preparing_level1');prepare(1)
    status('matched_stage1_training',steps_each=4000,parameters=[3017984,4492544]);parallel('stage1')
    # Best snapshots use only manual and language-family held-out validation.
    stage1={}
    for arm in INITIAL:
        report=json.loads((ROOT/(arm+'-stage1/training.json')).read_text())
        stage1[arm]=next(r for r in report['history']if r['step']==report['best_step'])
    reached=any(r['gate']for r in stage1.values());level=2 if reached else 1
    (ROOT/'progression.json').write_text(json.dumps({'stage1':stage1,'level2_authorized_by_gate':reached,
      'both_sizes_receive_same_next_course':True,'fresh_opened':False},ensure_ascii=False,indent=2)+'\n')
    if reached:
        status('teacher_level2_generation')
        if not(ROOT/'teacher-level2/teacher-manifest.json').exists():
            with(ROOT/'teacher-level2.log').open('a')as log:
                subprocess.run([sys.executable,'-u',SCRIPT+'course_teacher.py','--root',CAP+'teacher-level2','--level','2','--workers','4'],
                               cwd=REPO,stdout=log,stderr=subprocess.STDOUT,check=True)
        prepare(2);status('matched_stage2_training',steps_each=4000);parallel('stage2')
    models={arm:CAP+arm+f'-stage{level}/best'for arm in INITIAL}
    choice={'level':level,'models':models,'stage1_gate_met':reached,'fresh_opened':False}
    (ROOT/'capacity-selected.json').write_text(json.dumps(choice,indent=2)+'\n')
    status('low_bit_ptq_and_matched_qat',formats=['q3','q2','mixed'],steps_per_format_per_size=500);parallel('precision')
    formats={}
    # Freeze a deployment candidate within approximately the original weight
    # envelope, plus unconstrained format comparisons. No fresh scores read here.
    for arm in INITIAL:
        report=json.loads((ROOT/(arm+f'-stage{level}/training.json')).read_text())
        primary=next(r for r in report['history']if r['step']==report['best_step'])
        candidates=[{'format':'q4','kind':'primary','model':models[arm],'key':primary['key'],'packed':primary['packed']}]
        for mode in ['q3','q2','mixed']:
            for kind in ['ptq','qat']:
                path=ROOT/'results'/(arm+'-'+mode+'-'+kind+'-validation.json');result=json.loads(path.read_text())
                candidates.append({'format':mode,'kind':kind,'model':result['model'],'key':result['key'],'packed':result['packed']})
        within=[r for r in candidates if r['packed']['bytes']<=int(1.8*1024**2)]
        formats[arm]={'all':candidates,'best_any_weight_size':max(candidates,key=lambda r:r['key']),
                      'best_under_1_8_mib_weights':max(within,key=lambda r:r['key'])if within else None}
    selected={**choice,'formats':formats,'selection':'Validation only; lexicographic formal guard, worst parse/program partition, mean score',
      'weight_only_comparison_ceiling_bytes':int(1.8*1024**2),'ceiling_is_experimental_not_complete_device_RAM':True,
      'closed_fresh_hashes':json.loads((ROOT/'frozen.json').read_text())['files']}
    (ROOT/'preselected.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2)+'\n')
    status('final_fresh_scoring',selection_frozen=True);parallel('final')
    summary={p.stem:{k:v for k,v in json.loads(p.read_text()).items()if k!='metrics'}for p in sorted((ROOT/'results').glob('*.json'))}
    (ROOT/'comparison.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'complete.json').write_text(json.dumps({'completed':True,'selection_used_fresh':False,
       'level':level,'native_runtime_measured':False,'result_files':len(summary)},indent=2)+'\n')
    status('complete',level=level,stage1_gate_met=reached)


if __name__=='__main__':
    try:main()
    except BaseException as e:
        # Worker failures must not silently look like completed comparisons.
        if '--arm'not in sys.argv:status('failed',error=str(e))
        raise
