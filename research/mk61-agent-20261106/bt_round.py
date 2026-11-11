"""Wait for a single isolated inference worker alongside untouched Qwen."""
import fcntl
from bt_common import ROOT,read,write,check_frozen
from run_experiment import run,SCRIPT,GPU


if __name__=='__main__':
    lock=(ROOT/'controller.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    check_frozen();policy=read(ROOT/'policy.json');assert GPU==str(policy['host_gpu'])
    assert not(ROOT/'complete.json').exists()
    try:
        run('harness-symbolic-context-v1/worker.log',SCRIPT+'bt_jobs.py',timeout=43200)
        assert read(ROOT/'complete.json')['all_audits_complete']
        write(ROOT/'controller-complete.json',{'complete':True,'all_own_workers_joined':True,'optimizer_updates':0})
    except BaseException as e:
        write(ROOT/'controller-failure.json',{'error':repr(e)});raise
