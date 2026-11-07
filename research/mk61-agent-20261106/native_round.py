"""Full target-precision language and MK-61 curricula with a closed final audit."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from run_experiment import run,BASE,REPO,SCRIPT

ROOT=BASE/'native-mixed-v1';REL='.build/mk61-agent-20261106/native-mixed-v1/'


def status(phase,**extra):
    d={'phase':phase,'unix':time.time(),**extra};(ROOT/'status.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(d),flush=True)


def arm_job(arm,phase):
    if phase=='language':
        run('native-mixed-v1/'+arm+'-language.log',SCRIPT+'native_language_train.py','--arm',arm,timeout=21600)
    elif phase=='sft':
        run('native-mixed-v1/'+arm+'-sft.log',SCRIPT+'native_sft.py','--arm',arm,timeout=21600)
    elif phase=='final':
        run('native-mixed-v1/'+arm+'-final.log',SCRIPT+'native_eval.py','--arm',arm,'--split','fresh',timeout=10800)


def parallel(phase):
    def worker(arm,gpu):
        with(ROOT/(arm+'-'+phase+'-controller.log')).open('a')as log:
            p=subprocess.run([sys.executable,'-u',SCRIPT+'native_round.py','--arm',arm,'--phase',phase],cwd=REPO,
              env={**os.environ,'MK61_AGENT_GPU':str(gpu)},stdout=log,stderr=subprocess.STDOUT)
        if p.returncode:raise RuntimeError('Failed '+arm+' '+phase)
    with ThreadPoolExecutor(max_workers=2)as pool:
        futures=[pool.submit(worker,a,g)for a,g in [('q4',0),('mixed',1)]]
        for f in futures:f.result()


def main():
    p=argparse.ArgumentParser();p.add_argument('--arm',choices=['q4','mixed']);p.add_argument('--phase');a=p.parse_args()
    if a.arm:arm_job(a.arm,a.phase);return
    ROOT.mkdir(exist_ok=True);lock=(ROOT/'controller.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if(ROOT/'complete.json').exists():print('Already complete');return
    status('waiting_for_language_data');started=time.monotonic()
    while not(ROOT/'language/manifest.json').exists():
        if time.monotonic()-started>10800:raise TimeoutError('Language data did not complete')
        time.sleep(10)
    assert(ROOT/'initial/manifest.json').exists()and(ROOT/'frozen.json').exists()
    assert(ROOT/'initial-active/manifest.json').exists(),'Validate activated hidden directions before continuing'
    status('matched_language_training',token_exposures_each=100000000,formats=['q4','mixed']);parallel('language')
    status('waiting_for_teacher');started=time.monotonic()
    while not(ROOT/'teacher/manifest.json').exists():
        if time.monotonic()-started>7200:raise TimeoutError('Verified teacher data did not complete')
        time.sleep(10)
    status('preparing_mk61_course')
    run('native-mixed-v1/prepare.log',SCRIPT+'native_prepare.py')
    status('matched_mk61_sft',steps_each=8000,context_training=[512,1024,2048]);parallel('sft')
    choices={}
    for arm in ['q4','mixed']:
        data=json.loads((ROOT/(arm+'-sft/training.json')).read_text());choices[arm]={'model':REL+arm+'-sft/best','step':data['best_step'],'key':data['best_key']}
    (ROOT/'preselected.json').write_text(json.dumps({'choices':choices,'fresh_used_for_selection':False,
        'frozen':json.loads((ROOT/'frozen.json').read_text())},ensure_ascii=False,indent=2)+'\n')
    status('closed_fresh_evaluation',selection_frozen=True);parallel('final')
    results={a:json.loads((ROOT/(a+'-fresh.json')).read_text())for a in choices}
    (ROOT/'complete.json').write_text(json.dumps({'completed':True,'results':{a:r['summary']for a,r in results.items()},
      'selected_without_fresh':choices,'native_device_measured':False},ensure_ascii=False,indent=2)+'\n')
    status('complete')


if __name__=='__main__':
    try:main()
    except BaseException as e:
        if '--arm'not in sys.argv:status('failed',error=str(e))
        raise
