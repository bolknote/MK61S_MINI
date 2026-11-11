"""Head-only and encoder-adapting critics, trained on the same balanced draws."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import fcntl
import json
import os
import shutil
import subprocess
import sys
import time
from ao_common import ROOT,ARMS,write,sha
from run_experiment import REPO,SCRIPT,run


def status(phase,**extra):write(ROOT/'status.json',{'phase':phase,'unix':time.time(),**extra})


def worker(arm,action):
    with(ROOT/f'{arm}-{action}-controller.log').open('a')as log:
        p=subprocess.run([sys.executable,'-u',SCRIPT+'ao_round.py','worker',arm,action],cwd=REPO,
            env={**os.environ,'MK61_AGENT_GPU':'0'if arm=='head'else'1'},stdout=log,stderr=subprocess.STDOUT)
    if p.returncode:raise RuntimeError((arm,action,p.returncode))


def parallel(action):
    with ThreadPoolExecutor(max_workers=2)as pool:
        for f in as_completed([pool.submit(worker,a,action)for a in ARMS]):f.result()


def main():
    if len(sys.argv)>1:
        arm,action=sys.argv[2:4];run(f'error-recognizer-v1/{arm}-{action}.log',SCRIPT+'ao_jobs.py',action,'--arm',arm,timeout=14400);return
    ROOT.mkdir(exist_ok=True);lock=(ROOT/'controller.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if(ROOT/'complete.json').exists():return
    status('preflight_and_frozen_features');run('error-recognizer-v1/prepare.log',SCRIPT+'ao_jobs.py','prepare',timeout=14400)
    status('balanced_diagnosis_training');parallel('train')
    records={a:json.loads((ROOT/a/'training.json').read_text())for a in ARMS};assert records['head']['same_draw_digest']==records['adapt']['same_draw_digest']
    choices={a:json.loads((ROOT/a/'best.json').read_text())for a in ARMS};selected=max(ARMS,key=lambda a:choices[a]['key'])
    write(ROOT/'preselected.json',{'selected_arm':selected,'choices':choices,'fresh_used_for_selection':False,'selection_split':'development'})
    status('sealed_fresh_Q4_exam');parallel('audit')
    shutil.copytree(ROOT/'export'/selected,ROOT/'export/selected-research',dirs_exist_ok=True)
    for manifest in ['data-frozen.json','prepared.json']:
        for n,d in json.loads((ROOT/manifest).read_text())['files'].items():assert sha(ROOT/n)==d,n
    for n,d in json.loads((ROOT/'prepared.json').read_text())['source_hashes'].items():assert sha(REPO/SCRIPT/n)==d,n
    write(ROOT/'complete.json',{'completed':True,'optimizer_updates':sum(r['steps']for r in records.values())});status('complete')


if __name__=='__main__':
    try:main()
    except BaseException as e:
        if len(sys.argv)==1:status('failed',error=repr(e))
        raise
