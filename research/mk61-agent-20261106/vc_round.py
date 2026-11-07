from concurrent.futures import ThreadPoolExecutor,as_completed
import fcntl
import json
import os
import shutil
import subprocess
import sys
import time
from vc_common import ROOT,INITIAL,INITIAL_PACKET,HERE,ARMS,sha,write
from run_experiment import REPO,SCRIPT,run


def status(phase,**extra):write(ROOT/'status.json',{'phase':phase,'unix':time.time(),**extra})
def worker(arm,action):
    p=subprocess.run([sys.executable,'-u',SCRIPT+'vc_round.py','worker',arm,action],cwd=REPO,
      env={**os.environ,'MK61_AGENT_GPU':str(ARMS.index(arm))})
    if p.returncode:raise RuntimeError('Verifier worker failed '+arm+' '+action)


def main():
    ROOT.mkdir(exist_ok=True)
    if len(sys.argv)>1 and sys.argv[1]=='worker':
        arm,action=sys.argv[2:4];run('harness-verifier-v1/'+arm+'-'+action+'.log',SCRIPT+('vc_train.py'if action=='train'else'vc_eval.py'),'--arm',arm,timeout=14400);return
    lock=(ROOT/'controller.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    frozen=json.loads((ROOT/'data-frozen.json').read_text())
    for n,d in frozen['files'].items():assert sha(ROOT/n)==d
    assert sha(INITIAL/'model.safetensors')==frozen['initial_master_sha256']and sha(INITIAL_PACKET)==frozen['initial_packet_sha256']
    names=['vc_common.py','vc_protocol.py','vc_train.py','vc_eval.py','vc_data.py','native_quant.py','lowbit.py','quantization.py','full_isa_vm.py','hf_runtime.py','ha_runtime.py','ha_protocol.py']
    source=ROOT/'training-source';source.mkdir(exist_ok=True)
    for n in names:shutil.copyfile(HERE/n,source/n)
    write(ROOT/'prepared.json',{'files':{**frozen['files'],**{str(p.relative_to(ROOT)):sha(p)for p in source.iterdir()}},
      'source_hashes':{n:sha(HERE/n)for n in names},'before_optimizer_updates':True,
      'initial_master_sha256':frozen['initial_master_sha256'],'initial_packet_sha256':frozen['initial_packet_sha256'],'language_streams':{}})
    status('training_two_semantic_verifiers',steps_each=2000)
    with ThreadPoolExecutor(max_workers=2)as pool:
        for f in as_completed([pool.submit(worker,a,'train')for a in ARMS]):f.result()
    reports={a:json.loads((ROOT/a/'training.json').read_text())for a in ARMS};assert reports['slow']['sample_plan_digest']==reports['fast']['sample_plan_digest']
    details={a:json.loads((ROOT/a/f'development-{r["best_step"]}.json').read_text())['details']for a,r in reports.items()}
    assert [r['id']for r in details['slow']]==[r['id']for r in details['fast']]
    negative=[i for i,r in enumerate(details['slow'])if not r['label']];positive=[i for i,r in enumerate(details['slow'])if r['label']]
    best_pair=None
    for threshold_slow in [-1e6]+sorted({details['slow'][i]['score']+.01 for i in negative}):
        remaining=[i for i in negative if details['slow'][i]['score']>=threshold_slow]
        threshold_fast=max([details['fast'][i]['score']for i in remaining],default=-1e6)+.01
        accepted=[i for i in positive if details['slow'][i]['score']>=threshold_slow and details['fast'][i]['score']>=threshold_fast]
        candidate={'slow':threshold_slow,'fast':threshold_fast,'coverage':len(accepted)/len(positive),'false_positive':0,'positive':len(positive),'negative':len(negative)}
        if best_pair is None or candidate['coverage']>best_pair['coverage']:best_pair=candidate
    write(ROOT/'preselected.json',{'selected_arm':max(ARMS,key=lambda a:reports[a]['best_key']),
      'choices':{a:{'best_step':r['best_step'],'best_key':r['best_key']}for a,r in reports.items()},'ensemble':best_pair,'fresh_used_for_selection':False})
    status('sealed_verifier_exam')
    with ThreadPoolExecutor(max_workers=2)as pool:
        for f in as_completed([pool.submit(worker,a,'audit')for a in ARMS]):f.result()
    run('harness-verifier-v1/export.log',SCRIPT+'vc_export.py',timeout=3600)
    assert sha(INITIAL/'model.safetensors')==frozen['initial_master_sha256']and sha(INITIAL_PACKET)==frozen['initial_packet_sha256']
    write(ROOT/'complete.json',{'completed':True,'steps_each':2000,'source_coder_unchanged':True});status('complete')


if __name__=='__main__':
    try:main()
    except BaseException as error:
        if len(sys.argv)<2 or sys.argv[1]!='worker':status('failed',error=repr(error))
        raise
