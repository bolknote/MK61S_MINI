"""One frozen start, two GPUs, joint known/novel control, then sealed Q4 exam."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import fcntl
import json
import os
import shutil
import subprocess
import sys
import time
from ap_common import ROOT,ARMS,write,sha
from run_experiment import REPO,SCRIPT,run


def status(phase,**extra):write(ROOT/'status.json',{'phase':phase,'unix':time.time(),**extra})


def worker(arm,action):
    if action=='train'and(ROOT/arm/'training.json').exists():return
    if action=='audit'and(ROOT/arm/'fresh.json').exists()and(ROOT/'export'/arm/'manifest.json').exists():return
    if action=='baseline'and(ROOT/('initial-'+arm+'-fresh.json')).exists():return
    with(ROOT/f'{arm}-{action}-controller.log').open('a')as log:
        p=subprocess.run([sys.executable,'-u',SCRIPT+'ap_round.py','worker',arm,action],cwd=REPO,
          env={**os.environ,'MK61_AGENT_GPU':'0'if arm=='full'else'1'},stdout=log,stderr=subprocess.STDOUT)
    if p.returncode:raise RuntimeError((arm,action,p.returncode))


def parallel(action):
    with ThreadPoolExecutor(max_workers=2)as pool:
        for f in as_completed([pool.submit(worker,a,action)for a in ARMS]):f.result()


def main():
    if len(sys.argv)>1:
        arm,action=sys.argv[2:4];run(f'step-debug-v1/{arm}-{action}.log',SCRIPT+'ap_jobs.py',action,'--arm',arm,timeout=14400);return
    ROOT.mkdir(exist_ok=True);lock=(ROOT/'controller.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if(ROOT/'complete.json').exists():return
    if not(ROOT/'prepared.json').exists():
        status('preflight');run('step-debug-v1/prepare.log',SCRIPT+'ap_jobs.py','prepare',timeout=14400)
    status('paired_full_short_training');parallel('train')
    records={a:json.loads((ROOT/a/'training.json').read_text())for a in ARMS}
    assert records['full']['same_draw_digest']==records['short']['same_draw_digest']
    assert records['full']['starting_checkpoint_sha256']==records['short']['starting_checkpoint_sha256']
    choices={a:json.loads((ROOT/a/'best.json').read_text())for a in ARMS};selected=max(ARMS,key=lambda a:choices[a]['key'])
    write(ROOT/'preselected.json',{'selected_arm':selected,'choices':choices,'fresh_used_for_selection':False,'selection_split':'known and novel development'})
    status('sealed_fresh_Q4_exam');parallel('audit')
    status('source_fresh_Q4_comparison');parallel('baseline')
    shutil.copytree(ROOT/'export'/selected,ROOT/'export/selected-research',dirs_exist_ok=True)
    for name in ['data-frozen.json','prepared.json']:
        for n,d in json.loads((ROOT/name).read_text())['files'].items():assert sha(ROOT/n)==d,n
    for n,d in json.loads((ROOT/'prepared.json').read_text())['source_hashes'].items():assert sha(REPO/SCRIPT/n)==d,n
    write(ROOT/'complete.json',{'completed':True,'optimizer_updates':sum(r['steps']for r in records.values())});status('complete')


if __name__=='__main__':
    try:main()
    except BaseException as e:
        if len(sys.argv)==1:status('failed',error=repr(e))
        raise
