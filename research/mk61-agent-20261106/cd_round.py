"""Join the one bounded actor-training worker through all fresh closed audits."""
import fcntl
from cd_common import ROOT,read,write,check_frozen
from run_experiment import run,SCRIPT,GPU


if __name__=='__main__':
    lock=(ROOT/'controller.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);check_frozen()
    assert GPU==str(read(ROOT/'policy.json')['host_gpu'])and not(ROOT/'complete.json').exists()
    try:
        run('spec-review-utility-v1/worker.log',SCRIPT+'cd_jobs.py',timeout=43200)
        assert read(ROOT/'complete.json')['all_audits_complete']
        write(ROOT/'controller-complete.json',{'complete':True,'all_own_workers_joined':True,'optimizer_updates':read(ROOT/'training.json')['optimizer_updates']})
    except BaseException as error:write(ROOT/'controller-failure.json',{'error':repr(error)});raise
