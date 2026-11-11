"""Matched two-GPU training; independent CPU-heavy audits share available GPUs."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import fcntl
import os
import shutil
import subprocess
import sys
import threading
import time
from bp_common import ROOT,ARMS,PRIOR_RESULTS,read,write,check_frozen
from run_experiment import REPO,SCRIPT,run


def status(phase,**extra):write(ROOT/'status.json',{'phase':phase,'unix':time.time(),**extra})


def worker(role,action,gpu):
    with(ROOT/(role+'-'+action+'-controller.log')).open('w')as log:
        result=subprocess.run([sys.executable,'-u',SCRIPT+'bp_round.py','worker',role,action],cwd=REPO,
                              env={**os.environ,'MK61_AGENT_GPU':str(gpu)},stdout=log,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError((role,action,result.returncode))


def main():
    if len(sys.argv)>1:
        role,action=sys.argv[2:4];run('spec-review-flag-fix-v1/'+role+'-'+action+'.log',SCRIPT+'bp_jobs.py',action,'--arm',role,timeout=28800);return
    lock=(ROOT/'controller.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    check_frozen();assert not(ROOT/'complete.json').exists();status('matched_parallel_training')
    with ThreadPoolExecutor(2)as pool:list(pool.map(lambda item:worker(item[1],'train',item[0]),enumerate(ARMS)))
    training={a:read(ROOT/a/'training.json')for a in ARMS};expected=read(ROOT/'repeat-plan.json')['original_draw_digest']
    assert all(x['optimizer_updates']==3000 and x['draw_digest']==expected for x in training.values())
    assert training['lora']['counts']==training['full']['counts']
    choices={a:read(ROOT/a/'best.json')for a in ARMS};preferred=max(ARMS,key=lambda a:choices[a]['key'])
    write(ROOT/'preselected.json',{'branches':choices,'preferred':preferred,'closed_used_for_selection':False,
          'original_development_only':True,'paired_final_step_endpoint':3000,'same_original_draw_digest':expected,'unix':time.time()})
    roles=['parent_lora','parent_full','bad_lora','bad_full','fixed3000_lora','fixed3000_full'];aliases={}
    for a in ARMS:
        if choices[a]['step']==0:aliases[a]='parent_'+a
        elif choices[a]['step']==3000:aliases[a]='fixed3000_'+a
        else:roles.append(a)
    write(ROOT/'closed-roles.json',{'evaluated':roles,'aliases':aliases,'no_closed_selection':True})
    semaphores=[threading.BoundedSemaphore(3),threading.BoundedSemaphore(3)]
    def audited(role,gpu):
        with semaphores[gpu]:worker(role,'audit',gpu)
        return role
    completed=[];status('fresh_closed_Q4_exam',completed=completed,total=len(roles))
    with ThreadPoolExecutor(6)as pool:
        futures={pool.submit(audited,role,i%2):role for i,role in enumerate(roles)}
        for future in as_completed(futures):
            completed.append(future.result());status('fresh_closed_Q4_exam',completed=completed,total=len(roles))
    for target,source in aliases.items():
        (ROOT/target).mkdir(exist_ok=True);shutil.copyfile(ROOT/source/'closed.json',ROOT/target/'closed.json')
        shutil.copytree(ROOT/'export'/source,ROOT/'export'/target,dirs_exist_ok=True)
        write(ROOT/target/'audit-reuse.json',{'source':source,'same_weights_and_runtime':True,'closed_used_for_selection':False})
        write(ROOT/target/'status.json',{'phase':'complete','audit_reused_from':source})
    check_frozen();write(ROOT/'complete.json',{'complete':True,'optimizer_updates':6000,'same_original_draws':True,'closed_used_for_selection':False})
    status('complete',optimizer_updates=6000)


if __name__=='__main__':
    try:main()
    except BaseException as error:
        if len(sys.argv)==1:status('failed',error=repr(error))
        raise
