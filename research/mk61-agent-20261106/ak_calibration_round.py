"""Development-only correction strength, then an untouched final exam."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import fcntl
import json
import os
import shutil
import subprocess
import sys
import time
from ak_common import ROOT,ARMS,write
from run_experiment import run,REPO,SCRIPT


def worker(arm,action):
    with(ROOT/f'{arm}-calibration-{action}-controller.log').open('a')as log:
        p=subprocess.run([sys.executable,'-u',SCRIPT+'ak_calibration_round.py','worker',arm,action],cwd=REPO,
          env={**os.environ,'MK61_AGENT_GPU':'0'if arm=='done'else'1'},stdout=log,stderr=subprocess.STDOUT)
    if p.returncode:raise RuntimeError((arm,action,p.returncode))


def parallel(action):
    with ThreadPoolExecutor(max_workers=2)as pool:
        for f in as_completed([pool.submit(worker,a,action)for a in ARMS]):f.result()


def main():
    if len(sys.argv)>1:
        arm,action=sys.argv[2:4];run(f'done-risk-v1/{arm}-calibration-{action}.log',SCRIPT+'ak_calibrate.py',action,'--arm',arm,timeout=7200);return
    lock=(ROOT/'calibration.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if(ROOT/'calibration-complete.json').exists():return
    write(ROOT/'calibration-status.json',{'phase':'development_closed_loop','unix':time.time()});parallel('control')
    choices={a:json.loads((ROOT/a/'calibrated.json').read_text())for a in ARMS};selected=max(ARMS,key=lambda a:choices[a]['key'])
    write(ROOT/'calibration-preselected.json',{'choices':choices,'selected_arm':selected,'fresh_used_for_selection':False,
      'development_only':True,'strict_original_nonregression':True})
    write(ROOT/'calibration-status.json',{'phase':'sealed_fresh_exam','unix':time.time()});parallel('audit')
    shutil.copytree(ROOT/'export'/(selected+'-calibrated'),ROOT/'export/selected-correction',dirs_exist_ok=True)
    write(ROOT/'calibration-complete.json',{'completed':True,'optimizer_updates':0,'selected_arm':selected})
    write(ROOT/'calibration-status.json',{'phase':'complete','unix':time.time()})


if __name__=='__main__':
    try:main()
    except BaseException as error:
        if len(sys.argv)==1:write(ROOT/'calibration-status.json',{'phase':'failed','error':repr(error)})
        raise
