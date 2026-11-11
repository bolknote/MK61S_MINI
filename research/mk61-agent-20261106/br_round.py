"""Two independent full GPUs, equal draws, and a barrier before held-out access."""
import fcntl
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from br_common import ROOT,ARMS,read,write,check_frozen
from run_experiment import REPO,SCRIPT,run


def status(phase,**extra):write(ROOT/'status.json',{'phase':phase,'unix':time.time(),**extra})


def worker(item):
    gpu,arm,action=item
    with(ROOT/(arm+'-'+action+'-controller.log')).open('w')as log:
        r=subprocess.run([sys.executable,'-u',SCRIPT+'br_round.py','worker',arm,action],cwd=REPO,
                         env={**os.environ,'MK61_AGENT_GPU':str(gpu)},stdout=log,stderr=subprocess.STDOUT)
    if r.returncode:raise RuntimeError((arm,action,r.returncode))


def main():
    if len(sys.argv)>1:
        arm,action=sys.argv[2:4];run('capacity-clean-cycles-v1/'+arm+'-'+action+'.log',SCRIPT+'br_jobs.py',action,'--arm',arm,timeout=43200);return
    lock=(ROOT/'controller.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    check_frozen();assert not(ROOT/'complete.json').exists();status('parallel_training')
    with ThreadPoolExecutor(2)as pool:list(pool.map(worker,[(i,a,'train')for i,a in enumerate(ARMS)]))
    t={a:read(ROOT/a/'training.json')for a in ARMS};policy=read(ROOT/'policy.json')
    assert t['small']['counts']==t['large']['counts']
    assert t['small']['draw_digest']==t['large']['draw_digest']==read(ROOT/'prepared.json')['expected_draw_digest']
    assert all(x['optimizer_updates']==policy['steps']for x in t.values())
    probes={a:read(ROOT/a/'initial-receipt.json')['probes']for a in ARMS}
    assert all(x['generation']['generated_token_ids']==y['generation']['generated_token_ids']for x,y in zip(probes['small'],probes['large']))
    choices={a:read(ROOT/a/'best.json')for a in ARMS}
    write(ROOT/'preselected.json',{'branches':choices,'selection':'training states and cycles only; earliest on exact ties',
          'held_out_seen':False,'same_draw_digest':t['small']['draw_digest'],'unix':time.time()})
    status('held_out_audits')
    with ThreadPoolExecutor(2)as pool:list(pool.map(worker,[(i,a,'audit')for i,a in enumerate(ARMS)]))
    check_frozen();write(ROOT/'complete.json',{'complete':True,'all_workers_joined':True,'optimizer_updates':2*policy['steps'],
        'same_draws':True,'held_out_used_for_selection':False,'unix':time.time()});status('complete')


if __name__=='__main__':
    try:main()
    except BaseException as e:
        if len(sys.argv)==1:status('failed',error=repr(e))
        raise
