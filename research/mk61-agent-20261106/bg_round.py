"""Both branch baselines, matched continuations, then one sealed four-model exam."""
from concurrent.futures import ThreadPoolExecutor
import fcntl
import os
import subprocess
import sys
import time
from bg_common import ROOT,ARMS,read,write,check_frozen
from run_experiment import REPO,SCRIPT,run

def status(phase,**extra):write(ROOT/'status.json',{'phase':phase,'unix':time.time(),**extra})
def worker(arm,action,gpu):
    with(ROOT/(arm+'-'+action+'-controller.log')).open('w')as log:
        result=subprocess.run([sys.executable,'-u',SCRIPT+'bg_round.py','worker',arm,action],cwd=REPO,
            env={**os.environ,'MK61_AGENT_GPU':str(gpu)},stdout=log,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError((arm,action,result.returncode))
def parallel(arms,action):
    with ThreadPoolExecutor(2)as pool:list(pool.map(lambda x:worker(x[1],action,x[0]),enumerate(arms)))

def main():
    if len(sys.argv)>1:
        arm,action=sys.argv[2:4];run('spec-preserve-v1/'+arm+'-'+action+'.log',SCRIPT+'bg_jobs.py',action,'--arm',arm,timeout=28800);return
    lock=(ROOT/'controller.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert not(ROOT/'complete.json').exists();check_frozen();status('both_parent_development_before_SGD');parallel(ARMS,'baseline')
    status('parallel_natural_LoRA_and_full_Q4_training');parallel(ARMS,'train')
    training={a:read(ROOT/a/'training.json')for a in ARMS};steps=read(ROOT/'policy.json')['steps']
    assert all(v['optimizer_updates']==steps and v['initial_Q4_exact']for v in training.values())
    assert training['lora']['draw_digest']==training['full']['draw_digest']
    assert training['lora']['counts']==training['full']['counts']
    choices={a:read(ROOT/a/'best.json')for a in ARMS};preferred=max(ARMS,key=lambda a:choices[a]['key'])
    write(ROOT/'preselected.json',{'branches':choices,'preferred':preferred,'closed_used_for_selection':False,
        'selection_split':'new natural development only','same_data_draws':True,'continue_own_parent_weights':True,'unix':time.time()})
    status('new_closed_Q4_exam');parallel(ARMS,'audit');parallel(['parent_lora','parent_full'],'audit')
    check_frozen();write(ROOT/'complete.json',{'complete':True,'optimizer_updates':2*steps,'closed_used_for_selection':False,'same_data_draws':True})
    status('complete',optimizer_updates=2*steps)

if __name__=='__main__':
    try:main()
    except BaseException as error:
        if len(sys.argv)==1:status('failed',error=repr(error))
        raise
