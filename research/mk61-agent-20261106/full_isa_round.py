"""Full-command data, two Q4 students and selection before exhaustive audit."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import fcntl
import json
import os
import subprocess
import sys
import time
import urllib.request

from full_isa_common import ROOT,ARMS,INITIAL,INITIAL_PACKET,INITIAL_MASTER_SHA,INITIAL_PACKET_SHA,sha,write
from run_experiment import REPO,SCRIPT,run


def status(phase,**extra):
    x={'phase':phase,'unix':time.time(),**extra};write(ROOT/'status.json',x);print(json.dumps(x),flush=True)


def data():
    if not(ROOT/'teacher/manifest.json').exists():
        status('full_isa_teacher_starting')
        for i in range(180):
            try:
                x=json.load(urllib.request.urlopen('http://127.0.0.1:8001/v1/models',timeout=5))
                if any(m['id']=='Qwen/Qwen3.8-Flash-Next-FP8'for m in x['data']):break
            except Exception:pass
            if i%6==0:print(json.dumps({'waiting_seconds':i*5}),flush=True)
            time.sleep(5)
        else:raise RuntimeError('Own full ISA teacher not ready')
        status('full_isa_teacher_generation_and_blind_execution_checks')
        subprocess.run([sys.executable,'-u',SCRIPT+'full_isa_teacher.py'],cwd=REPO,check=True)
    marker=json.loads((ROOT/'teacher-container.json').read_text())
    info=json.loads(subprocess.check_output(['sudo','-n','docker','inspect',marker['container']],text=True))[0]
    assert(info['Config'].get('Labels')or{}).get('mk61.owner')=='full-isa-v1'
    if info['State']['Running']:subprocess.run(['sudo','-n','docker','stop','--time','30',marker['container']],check=True)
    status('full_isa_data_ready_teacher_released',verified_teacher=json.loads((ROOT/'teacher/manifest.json').read_text())['verified'])


def worker(arm,action):
    with(ROOT/(arm+'-'+action+'-controller.log')).open('a')as log:
        result=subprocess.run([sys.executable,'-u',SCRIPT+'full_isa_round.py','worker',arm,action],cwd=REPO,
          env={**os.environ,'MK61_AGENT_GPU':str(ARMS.index(arm))},stdout=log,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError('Full ISA worker failed: '+arm+' '+action)


def main():
    ROOT.mkdir(exist_ok=True)
    if len(sys.argv)>1 and sys.argv[1]=='worker':
        arm,action=sys.argv[2:4]
        if action=='train':run('full-isa-v1/'+arm+'.log',SCRIPT+'full_isa_train.py','--arm',arm,timeout=21600)
        elif action=='audit':run('full-isa-v1/'+arm+'-audit.log',SCRIPT+'full_isa_eval.py','--arm',arm,timeout=14400)
        else:raise ValueError(action)
        return
    lock=(ROOT/'controller.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if sys.argv[1]=='data':data();return
    if(ROOT/'complete.json').exists():print('Full ISA run already complete');return
    data();assert sha(INITIAL/'model.safetensors')==INITIAL_MASTER_SHA and sha(INITIAL_PACKET)==INITIAL_PACKET_SHA
    if not(ROOT/'prepared.json').exists():
        status('full_isa_baseline_and_training_error_collection')
        run('full-isa-v1/prepare-run.log',SCRIPT+'full_isa_prepare_run.py',timeout=10800)
    status('two_full_command_3m_q4_trainings',steps_each=8000)
    with ThreadPoolExecutor(max_workers=2)as pool:
        for f in as_completed([pool.submit(worker,a,'train')for a in ARMS]):f.result()
    reports={a:json.loads((ROOT/a/'training.json').read_text())for a in ARMS}
    assert reports['full']['sample_plan_digest']==reports['protected']['sample_plan_digest']
    assert reports['full']['counts']==reports['protected']['counts']
    selection={'choices':{a:{'best_step':r['best_step'],'best_key':r['best_key'],'master_sha256':sha(ROOT/a/'best/model.safetensors')}for a,r in reports.items()},
      'primary_selected_arm':max(ARMS,key=lambda a:reports[a]['best_key']),'audit_used_for_selection':False,
      'prepared_sha256':sha(ROOT/'prepared.json'),'matched_example_plan':True}
    write(ROOT/'preselected.json',selection);status('full_isa_closed_exhaustive_and_natural_audit')
    with ThreadPoolExecutor(max_workers=2)as pool:
        for f in as_completed([pool.submit(worker,a,'audit')for a in ARMS]):f.result()
    status('full_isa_exporting_audited_q4_packets')
    run('full-isa-v1/export.log',SCRIPT+'full_isa_export.py',timeout=3600)
    assert sha(INITIAL/'model.safetensors')==INITIAL_MASTER_SHA and sha(INITIAL_PACKET)==INITIAL_PACKET_SHA
    write(ROOT/'complete.json',{'completed':True,'updates_each':8000,'audit_used_for_selection':False,'original_checkpoint_unchanged':True,'full_opcode_reference_coverage':1.})
    status('complete')


if __name__=='__main__':
    try:main()
    except BaseException as e:
        if len(sys.argv)<2 or sys.argv[1]!='worker':status('failed',error=repr(e))
        raise
