"""Prepare, train both formats on separate B200s, freeze selection, then audit."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import fcntl
import json
import os
import subprocess
import sys
import time

from ha_common import ROOT,INITIAL,INITIAL_PACKET,ARMS,sha,write
from run_experiment import REPO,SCRIPT,run


def status(phase,**extra):write(ROOT/'status.json',{'phase':phase,'unix':time.time(),**extra})


def worker(arm,action):
    with(ROOT/(arm+'-'+action+'-controller.log')).open('a')as log:
        result=subprocess.run([sys.executable,'-u',SCRIPT+'ha_round.py','worker',arm,action],cwd=REPO,
          env={**os.environ,'MK61_AGENT_GPU':str(ARMS.index(arm))},stdout=log,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError('Harness worker failed: '+arm+' '+action)


def main():
    ROOT.mkdir(exist_ok=True)
    if len(sys.argv)>1 and sys.argv[1]=='worker':
        arm,action=sys.argv[2:4];script='ha_train.py'if action=='train'else'ha_eval.py'
        run('harness-ablation-v1/'+arm+'-'+action+'.log',SCRIPT+script,'--arm',arm,timeout=21600);return
    lock=(ROOT/'controller.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if(ROOT/'complete.json').exists():return
    frozen=json.loads((ROOT/'data-frozen.json').read_text())
    assert sha(INITIAL/'model.safetensors')==frozen['initial_master_sha256']and sha(INITIAL_PACKET)==frozen['initial_packet_sha256']
    if not(ROOT/'prepared.json').exists():
        status('paired_error_collection_and_preflight');run('harness-ablation-v1/prepare-run.log',SCRIPT+'ha_prepare_run.py',timeout=14400)
    status('paired_q4_training',steps_each=4000)
    with ThreadPoolExecutor(max_workers=2)as pool:
        for f in as_completed([pool.submit(worker,a,'train')for a in ARMS]):f.result()
    reports={a:json.loads((ROOT/a/'training.json').read_text())for a in ARMS}
    assert reports['direct']['sample_plan_digest']==reports['asm']['sample_plan_digest']
    assert reports['direct']['counts']==reports['asm']['counts']
    selection={'choices':{a:{'best_step':r['best_step'],'best_key':r['best_key'],'master_sha256':sha(ROOT/a/'best/model.safetensors')}for a,r in reports.items()},
      'primary_selected_arm':max(ARMS,key=lambda a:reports[a]['best_key']),'fresh_used_for_selection':False,
      'prepared_sha256':sha(ROOT/'prepared.json'),'identical_semantic_sample_plan':True}
    write(ROOT/'preselected.json',selection);status('sealed_fresh_exam_and_full_isa_audit')
    with ThreadPoolExecutor(max_workers=2)as pool:
        for f in as_completed([pool.submit(worker,a,'audit')for a in ARMS]):f.result()
    status('exporting_audited_packets');run('harness-ablation-v1/export.log',SCRIPT+'ha_export.py',timeout=3600)
    assert sha(INITIAL/'model.safetensors')==frozen['initial_master_sha256']and sha(INITIAL_PACKET)==frozen['initial_packet_sha256']
    write(ROOT/'complete.json',{'completed':True,'updates_each':4000,'fresh_used_for_selection':False,
      'initial_checkpoint_unchanged':True,'paired_semantic_examples_identical':True,'oracle_free_tool_observations':True})
    status('complete')


if __name__=='__main__':
    try:main()
    except BaseException as error:
        if len(sys.argv)<2 or sys.argv[1]!='worker':status('failed',error=repr(error))
        raise

