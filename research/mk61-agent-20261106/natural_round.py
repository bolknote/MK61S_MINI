"""Two authorized B200s: ordinary-language continuation and a sealed new exam."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import fcntl
import json
import os
import subprocess
import sys
import time

from natural_common import ROOT,INITIAL,INITIAL_PACKET,sha,write
from run_experiment import REPO,SCRIPT,run

ARMS=['full','protected']


def status(phase,**extra):
    write(ROOT/'status.json',{'phase':phase,'unix':time.time(),**extra})


def worker(arm,action):
    with(ROOT/(arm+'-'+action+'-controller.log')).open('a')as log:
        result=subprocess.run([sys.executable,'-u',SCRIPT+'natural_round.py','worker',arm,action],cwd=REPO,
          env={**os.environ,'MK61_AGENT_GPU':str(ARMS.index(arm))},stdout=log,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError('Natural worker failed: '+arm+' '+action)


def main():
    ROOT.mkdir(exist_ok=True)
    if len(sys.argv)>1 and sys.argv[1]=='worker':
        arm,action=sys.argv[2:4];script='natural_train.py'if action=='train'else'natural_eval.py'
        run('full-isa-natural-v1/'+arm+'-'+action+'.log',SCRIPT+script,'--arm',arm,timeout=14400);return
    lock=(ROOT/'controller.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if(ROOT/'complete.json').exists():return
    frozen=json.loads((ROOT/'data-frozen.json').read_text())
    assert sha(INITIAL/'model.safetensors')==frozen['initial_master_sha256']and sha(INITIAL_PACKET)==frozen['initial_packet_sha256']
    if not(ROOT/'prepared.json').exists():
        status('natural_language_error_collection_and_preflight')
        run('full-isa-natural-v1/prepare-run.log',SCRIPT+'natural_prepare_run.py',timeout=10800)
    status('two_natural_language_q4_trainings',steps_each=3000)
    with ThreadPoolExecutor(max_workers=2)as pool:
        for f in as_completed([pool.submit(worker,a,'train')for a in ARMS]):f.result()
    reports={a:json.loads((ROOT/a/'training.json').read_text())for a in ARMS}
    assert reports['full']['sample_plan_digest']==reports['protected']['sample_plan_digest']
    assert reports['full']['counts']==reports['protected']['counts']
    selection={'choices':{a:{'best_step':r['best_step'],'best_key':r['best_key'],'master_sha256':sha(ROOT/a/'best/model.safetensors')}for a,r in reports.items()},
      'primary_selected_arm':max(ARMS,key=lambda a:reports[a]['best_key']),'audit_used_for_selection':False,
      'prepared_sha256':sha(ROOT/'prepared.json'),'matched_example_plan':True}
    write(ROOT/'preselected.json',selection);status('new_natural_language_exam_and_full_isa_regression')
    with ThreadPoolExecutor(max_workers=2)as pool:
        for f in as_completed([pool.submit(worker,a,'audit')for a in ARMS]):f.result()
    status('exporting_audited_packets')
    run('full-isa-natural-v1/export.log',SCRIPT+'natural_export.py',timeout=3600)
    assert sha(INITIAL/'model.safetensors')==frozen['initial_master_sha256']and sha(INITIAL_PACKET)==frozen['initial_packet_sha256']
    write(ROOT/'complete.json',{'completed':True,'updates_each':3000,'fresh_exam_used_for_selection':False,'base_checkpoint_unchanged':True})
    status('complete')


if __name__=='__main__':
    try:main()
    except BaseException as error:
        if len(sys.argv)<2 or sys.argv[1]!='worker':status('failed',error=repr(error))
        raise

