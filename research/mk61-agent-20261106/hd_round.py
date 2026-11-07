from concurrent.futures import ThreadPoolExecutor,as_completed
import fcntl
import json
import os
import subprocess
import sys
import time
from hd_common import ROOT,INITIAL,INITIAL_PACKET,ARMS,sha,write
from run_experiment import REPO,SCRIPT,run


def status(phase,**extra):write(ROOT/'status.json',{'phase':phase,'unix':time.time(),**extra})
def worker(arm,action):
    with(ROOT/(arm+'-'+action+'-controller.log')).open('a')as log:
        p=subprocess.run([sys.executable,'-u',SCRIPT+'hd_round.py','worker',arm,action],cwd=REPO,
          env={**os.environ,'MK61_AGENT_GPU':str(ARMS.index(arm))},stdout=log,stderr=subprocess.STDOUT)
    if p.returncode:raise RuntimeError('Correction worker failed: '+arm+' '+action)


def main():
    ROOT.mkdir(exist_ok=True)
    if len(sys.argv)>1 and sys.argv[1]=='worker':
        arm,action=sys.argv[2:4];run('harness-debug-v1/'+arm+'-'+action+'.log',SCRIPT+('hd_train.py'if action=='train'else'hd_eval.py'),'--arm',arm,timeout=14400);return
    lock=(ROOT/'controller.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if(ROOT/'complete.json').exists():return
    frozen=json.loads((ROOT/'data-frozen.json').read_text());assert sha(INITIAL/'model.safetensors')==frozen['initial_master_sha256']and sha(INITIAL_PACKET)==frozen['initial_packet_sha256']
    if not(ROOT/'prepared.json').exists():
        status('debugging_preflight');run('harness-debug-v1/prepare-run.log',SCRIPT+'hd_prepare_run.py',timeout=10800)
    status('two_debugging_q4_trainings',steps_each=3000)
    with ThreadPoolExecutor(max_workers=2)as pool:
        for f in as_completed([pool.submit(worker,a,'train')for a in ARMS]):f.result()
    reports={a:json.loads((ROOT/a/'training.json').read_text())for a in ARMS};assert reports['safe']['sample_plan_digest']==reports['active']['sample_plan_digest']and reports['safe']['counts']==reports['active']['counts']
    selection={'choices':{a:{'best_step':r['best_step'],'best_key':r['best_key'],'master_sha256':sha(ROOT/a/'best/model.safetensors')}for a,r in reports.items()},
      'primary_selected_arm':max(ARMS,key=lambda a:reports[a]['best_key']),'fresh_used_for_selection':False,'prepared_sha256':sha(ROOT/'prepared.json')}
    write(ROOT/'preselected.json',selection);status('new_debugging_exam_and_observed_regressions')
    with ThreadPoolExecutor(max_workers=2)as pool:
        for f in as_completed([pool.submit(worker,a,'audit')for a in ARMS]):f.result()
    status('exporting');run('harness-debug-v1/export.log',SCRIPT+'hd_export.py',timeout=3600)
    assert sha(INITIAL/'model.safetensors')==frozen['initial_master_sha256']and sha(INITIAL_PACKET)==frozen['initial_packet_sha256']
    write(ROOT/'complete.json',{'completed':True,'updates_each':3000,'same_examples_different_learning_rates':True,'fresh_used_for_selection':False});status('complete')


if __name__=='__main__':
    try:main()
    except BaseException as e:
        if len(sys.argv)<2 or sys.argv[1]!='worker':status('failed',error=repr(e))
        raise
