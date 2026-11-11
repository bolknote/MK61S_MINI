"""One bounded inference/training worker, joined before reporting completion."""
import fcntl
from bv_common import ROOT,read,write,check_frozen
from run_experiment import run,SCRIPT,GPU


if __name__=='__main__':
    lock=(ROOT/'controller.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);check_frozen();assert GPU==str(read(ROOT/'policy.json')['host_gpu'])
    assert not(ROOT/'complete.json').exists()
    try:
        run('spec-retention-recovery-v1/worker.log',SCRIPT+'bv_jobs.py',timeout=43200)
        result=read(ROOT/'complete.json');assert result['all_audits_complete']
        write(ROOT/'controller-complete.json',{'complete':True,'all_own_workers_joined':True,'optimizer_updates':result['optimizer_updates']})
    except BaseException as e:write(ROOT/'controller-failure.json',{'error':repr(e)});raise
