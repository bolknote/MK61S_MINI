"""Two seeds of SPEC; select once on development before opening closed."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import fcntl
import os
import subprocess
import sys
import time
from bc_common import ROOT,RUNS,read,write,sha,check_frozen
from run_experiment import REPO,SCRIPT,run


def status(phase,**extra):write(ROOT/'status.json',{'phase':phase,'unix':time.time(),**extra})


def worker(name,action,gpu):
    done=ROOT/name/('training.json'if action=='train'else'closed.json')if action!='baseline-development'else ROOT/'parent-development.json'
    if done.exists()and(action!='audit'or(ROOT/'export'/name/'manifest.json').exists()):return
    with(ROOT/f'{name}-{action}-controller.log').open('a')as log:
        result=subprocess.run([sys.executable,'-u',SCRIPT+'bc_round.py','worker',name,action],cwd=REPO,
            env={**os.environ,'MK61_AGENT_GPU':str(gpu)},stdout=log,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError((name,action,result.returncode))


def parallel(action,names):
    with ThreadPoolExecutor(2)as pool:
        for future in as_completed([pool.submit(worker,name,action,i)for i,name in enumerate(names)]):future.result()


def main():
    if len(sys.argv)>1:
        name,action=sys.argv[2:4];args=([action,'--run',name]if action=='train'else[action,'--which',name]if action=='audit'else[action])
        run('semantic-spec-selfcheck-v1/'+name+'-'+action+'.log',SCRIPT+'bc_jobs.py',*args,timeout=21600);return
    lock=(ROOT/'controller.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if(ROOT/'complete.json').exists():return
    check_frozen();status('parent_development_baseline_before_SGD');worker('parent','baseline-development',0)
    status('two_SPEC_seeds_Q4_training');parallel('train',RUNS)
    for name in RUNS:
        t=read(ROOT/name/'training.json');assert t['optimizer_updates']==4000 and t['initial_Q4_exact']
        assert t['starting_checkpoint_sha256']==sha(ROOT/'parent.safetensors')
    choices={name:read(ROOT/name/'best.json')for name in RUNS};selected_name=max(RUNS,key=lambda n:choices[n]['key'])
    write(ROOT/'preselected.json',{'selected':{'run':selected_name,**choices[selected_name]},'choices':choices,
        'closed_used_for_selection':False,'selection_split':'new development only','one_closed_candidate_from_two_seeds':True,'unix':time.time()})
    status('new_closed_Q4_comparison');parallel('audit',['spec','parent'])
    check_frozen();write(ROOT/'complete.json',{'completed':True,'optimizer_updates':8000,'closed_used_for_selection':False})
    status('complete',optimizer_updates=8000)


if __name__=='__main__':
    try:main()
    except BaseException as error:
        if len(sys.argv)==1:status('failed',error=repr(error))
        raise
