"""Parallel matched training; fix both choices before opening the fresh exam."""
from concurrent.futures import ThreadPoolExecutor
import fcntl
import os
import subprocess
import sys
import time
from be_common import ROOT,ARMS,read,write,check_frozen
from run_experiment import REPO,SCRIPT,run

def status(phase,**extra):write(ROOT/'status.json',{'phase':phase,'unix':time.time(),**extra})

def worker(arm,action,gpu):
    with(ROOT/(arm+'-'+action+'-controller.log')).open('w')as log:
        result=subprocess.run([sys.executable,'-u',SCRIPT+'be_round.py','worker',arm,action],cwd=REPO,
            env={**os.environ,'MK61_AGENT_GPU':str(gpu)},stdout=log,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError((arm,action,result.returncode))

def main():
    if len(sys.argv)>1:
        arm,action=sys.argv[2:4];run('spec-translation-clean-v1/'+arm+'-'+action+'.log',SCRIPT+'be_jobs.py',action,'--arm',arm,timeout=21600);return
    lock=(ROOT/'controller.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert not(ROOT/'complete.json').exists();check_frozen();status('parent_development_before_SGD');worker('parent','baseline',0)
    status('parallel_LoRA_and_full3M_Q4_training')
    with ThreadPoolExecutor(2)as pool:list(pool.map(lambda item:worker(item[1],'train',item[0]),enumerate(ARMS)))
    training={a:read(ROOT/a/'training.json')for a in ARMS}
    assert all(v['optimizer_updates']==4000 and v['initial_Q4_exact']for v in training.values())
    assert training['lora']['draw_digest']==training['full']['draw_digest']
    assert training['lora']['counts']==training['full']['counts']
    choices={a:read(ROOT/a/'best.json')for a in ARMS};preferred=max(ARMS,key=lambda a:choices[a]['key'])
    write(ROOT/'preselected.json',{'branches':choices,'preferred':preferred,'closed_used_for_selection':False,
        'selection_split':'new development only','data_draws_identical':True,'unix':time.time()})
    status('new_closed_Q4_exam')
    with ThreadPoolExecutor(2)as pool:list(pool.map(lambda item:worker(item[1],'audit',item[0]),enumerate(ARMS)))
    worker('parent','audit',0);check_frozen()
    write(ROOT/'complete.json',{'complete':True,'optimizer_updates':8000,'closed_used_for_selection':False,'data_draws_identical':True})
    status('complete',optimizer_updates=8000)

if __name__=='__main__':
    try:main()
    except BaseException as error:
        if len(sys.argv)==1:status('failed',error=repr(error))
        raise
