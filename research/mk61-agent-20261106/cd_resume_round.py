"""Join one evaluation-only recovery worker and preserve all original SGD files."""
import fcntl
from cd_common import ROOT,HERE,read,write,sha,check_frozen
from run_experiment import run,SCRIPT,GPU

if __name__=='__main__':
    lock=(ROOT/'controller.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);check_frozen()
    plan=read(ROOT/'recovery-frozen.json')
    for n,d in plan['sources'].items():assert sha(HERE/n)==d,n
    assert GPU==str(read(ROOT/'policy.json')['host_gpu'])
    try:
        run('spec-review-utility-v1/evaluation-recovery.log',SCRIPT+'cd_resume.py',timeout=43200)
        assert read(ROOT/'complete.json')['all_audits_complete']and read(ROOT/'recovery-complete.json')['additional_optimizer_updates']==0
        write(ROOT/'controller-complete.json',{'complete':True,'all_own_workers_joined':True,'optimizer_updates':800,'evaluation_only_recovery':True})
    except BaseException as error:write(ROOT/'controller-failure.json',{'error':repr(error),'evaluation_only_recovery':True});raise
