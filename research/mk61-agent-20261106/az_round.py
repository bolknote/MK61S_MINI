"""Continue the two preselected branches on the two authorized B200 cards."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import fcntl
import os
import subprocess
import sys
import time
from az_common import ROOT,ARMS,read,write,check_frozen,sha
from run_experiment import REPO,SCRIPT,run


def status(phase,**extra):write(ROOT/'status.json',{'phase':phase,'unix':time.time(),**extra})


def worker(arm,action):
    done=ROOT/arm/('training.json'if action=='train'else'closed.json')if action!='baseline'else ROOT/('source-'+arm+'-closed.json')
    if done.exists()and(action!='audit'or(ROOT/'export'/arm/'manifest.json').exists()):return
    with(ROOT/f'{arm}-{action}-controller.log').open('a')as log:
        result=subprocess.run([sys.executable,'-u',SCRIPT+'az_round.py','worker',arm,action],cwd=REPO,
             env={**os.environ,'MK61_AGENT_GPU':'0'if arm=='hex'else'1'},stdout=log,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError((arm,action,result.returncode))


def parallel(action):
    with ThreadPoolExecutor(max_workers=2)as pool:
        for future in as_completed([pool.submit(worker,arm,action)for arm in ARMS]):future.result()


def main():
    if len(sys.argv)>1:
        arm,action=sys.argv[2:4]
        run('semantic-spec-distill-v2/'+arm+'-'+action+'.log',SCRIPT+'az_jobs.py',action,'--arm',arm,timeout=18000);return
    lock=(ROOT/'controller.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if(ROOT/'complete.json').exists():return
    check_frozen();assert(ROOT/'prepared.json').exists()
    status('continued_two_GPU_Q4_training');parallel('train')
    a,b=[read(ROOT/arm/'training.json')for arm in ARMS]
    assert a['same_draw_digest']==b['same_draw_digest']and a['counts']==b['counts']
    for arm,training in zip(ARMS,[a,b]):
        assert training['starting_checkpoint_sha256']==sha(ROOT/('parent-'+arm+'.safetensors'))
        assert training['actual_B200_initial_Q4_exact']
    choices={arm:read(ROOT/arm/'best.json')for arm in ARMS}
    write(ROOT/'preselected.json',{'choices':choices,'selection_split':'development only','closed_used_for_selection':False,
       'same_draw_digest':a['same_draw_digest'],'no_cross_arm_promotion':True,'unix':time.time()})
    status('opening_new_closed_Q4_exam');parallel('audit')
    status('previous_branch_Q4_baselines_on_same_new_exam');parallel('baseline')
    check_frozen();write(ROOT/'complete.json',{'completed':True,'optimizer_updates':a['steps']+b['steps'],
        'closed_used_for_selection':False,'continued_each_own_preselected_parent':True})
    status('complete',optimizer_updates=a['steps']+b['steps'])


if __name__=='__main__':
    try:main()
    except BaseException as error:
        if len(sys.argv)==1:status('failed',error=repr(error))
        raise
