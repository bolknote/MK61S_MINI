"""Stage own teacher data, release it, then pair two 3M students on full B200s."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import fcntl
import json
import os
import subprocess
import sys
import time
import urllib.request

from semantic_common import ROOT,ARMS,INITIAL,INITIAL_PACKET,INITIAL_MASTER_SHA,INITIAL_PACKET_SHA,sha,write_json
from run_experiment import REPO,SCRIPT,run


def status(phase,**extra):
    row={'phase':phase,'unix':time.time(),**extra};write_json(ROOT/'status.json',row);print(json.dumps(row),flush=True)


def data():
    if not(ROOT/'teacher/manifest.json').exists():
        status('waiting_for_own_teacher')
        ready=False
        for i in range(180):
            try:
                response=json.load(urllib.request.urlopen('http://127.0.0.1:8001/v1/models',timeout=5))
                ready=any(v['id']=='Qwen/Qwen3.8-Flash-Next-FP8'for v in response['data'])
                if ready:break
            except Exception:pass
            if i%6==0:print(json.dumps({'waiting_seconds':i*5}),flush=True)
            time.sleep(5)
        if not ready:raise RuntimeError('Own teacher not ready within 15 minutes')
        status('teacher_generating_and_blind_checking_new_data')
        subprocess.run([sys.executable,'-u',SCRIPT+'semantic_teacher.py'],cwd=REPO,check=True)
    # Stop only the container whose immutable ID and ownership label we created.
    marker=json.loads((ROOT/'teacher-container.json').read_text())
    info=json.loads(subprocess.check_output(['sudo','-n','docker','inspect',marker['container']],text=True))[0]
    assert info['Config']['Labels'].get('mk61.owner')=='semantic-3m-v1'
    if info['State']['Running']:subprocess.run(['sudo','-n','docker','stop','--time','30',marker['container']],check=True)
    status('verified_teacher_data_complete_own_teacher_released',partitions=json.loads((ROOT/'teacher/manifest.json').read_text())['partitions'])


def worker(arm,action):
    gpu=0 if arm=='direct'else 1
    with(ROOT/(arm+'-'+action+'-controller.log')).open('a')as stream:
        child=subprocess.run([sys.executable,'-u',SCRIPT+'semantic_round.py','worker',arm,action],cwd=REPO,
          env={**os.environ,'MK61_AGENT_GPU':str(gpu)},stdout=stream,stderr=subprocess.STDOUT)
    if child.returncode:raise RuntimeError('Own worker failed: '+arm+' '+action)


def main():
    ROOT.mkdir(exist_ok=True)
    if len(sys.argv)>1 and sys.argv[1]=='worker':
        arm,action=sys.argv[2:4]
        if action=='train':run('semantic-3m-v1/'+arm+'.log',SCRIPT+'semantic_train.py','--arm',arm,timeout=14400)
        elif action=='audit':run('semantic-3m-v1/'+arm+'-audit.log',SCRIPT+'semantic_eval.py','--arm',arm,timeout=14400)
        else:raise ValueError(action)
        return
    lock=(ROOT/'controller.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if sys.argv[1]=='data':data();return
    if(ROOT/'complete.json').exists():print('Semantic comparison already complete');return
    data()
    assert sha(INITIAL/'model.safetensors')==INITIAL_MASTER_SHA
    assert sha(INITIAL_PACKET)==INITIAL_PACKET_SHA
    if not(ROOT/'prepared.json').exists():
        status('preparing_frozen_shared_data_and_initial_student_error_replay')
        run('semantic-3m-v1/prepare.log',SCRIPT+'semantic_prepare.py',timeout=7200)
    status('two_parallel_3m_hex_trainings',steps_each=2000)
    with ThreadPoolExecutor(max_workers=2)as pool:
        for future in as_completed([pool.submit(worker,arm,'train')for arm in ARMS]):future.result()
    reports={arm:json.loads((ROOT/arm/'training.json').read_text())for arm in ARMS}
    assert reports['direct']['sample_plan_digest']==reports['auxiliary']['sample_plan_digest']
    assert reports['direct']['core_sample_counts']==reports['auxiliary']['core_sample_counts']
    selection={'frozen_sha256':sha(ROOT/'prepared.json'),'audit_frozen_sha256':sha(ROOT/'audit-frozen.json'),
      'choices':{a:{'best_step':v['best_step'],'best_key':v['best_key'],'master_sha256':sha(ROOT/a/'best/model.safetensors')}for a,v in reports.items()},
      'same_core_sample_plan':True,'audit_used_for_selection':False,'primary':'validation-best; endpoints secondary'}
    selection['primary_selected_arm']=max(ARMS,key=lambda a:reports[a]['best_key'])
    write_json(ROOT/'preselected.json',selection)
    status('closed_audit_frozen_baseline_and_selected_students')
    with ThreadPoolExecutor(max_workers=2)as pool:
        for future in as_completed([pool.submit(worker,arm,'audit')for arm in ARMS]):future.result()
    status('exporting_audited_q4_models')
    run('semantic-3m-v1/export.log',SCRIPT+'semantic_export.py',timeout=3600)
    assert sha(INITIAL/'model.safetensors')==INITIAL_MASTER_SHA and sha(INITIAL_PACKET)==INITIAL_PACKET_SHA
    write_json(ROOT/'complete.json',{'completed':True,'updates_each':2000,'arms':ARMS,'audit_used_for_selection':False,
      'original_checkpoint_unchanged':True,'physical_picocalc_measured':False});status('complete')


if __name__=='__main__':
    try:main()
    except BaseException as error:
        if len(sys.argv)<2 or sys.argv[1]!='worker':status('failed',error=repr(error))
        raise
