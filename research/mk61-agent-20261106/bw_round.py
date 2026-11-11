"""Join one bounded inference worker, leaving Qwen untouched."""
import fcntl
from bw_common import ROOT,read,write,check_frozen
from run_experiment import run,SCRIPT,GPU

if __name__=='__main__':
    lock=(ROOT/'controller.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);check_frozen()
    assert GPU==str(read(ROOT/'policy.json')['host_gpu'])and not(ROOT/'complete.json').exists()
    try:
        run('spec-phase-routing-v1/worker.log',SCRIPT+'bw_jobs.py',timeout=43200)
        assert read(ROOT/'complete.json')['all_audits_complete']
        write(ROOT/'controller-complete.json',{'complete':True,'all_own_workers_joined':True,'optimizer_updates':0})
    except BaseException as e:write(ROOT/'controller-failure.json',{'error':repr(e)});raise
