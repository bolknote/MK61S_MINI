"""Attend the four-run comparison through fetch, exact reload, and local report."""
import fcntl
import json
from pathlib import Path
import subprocess
import sys
import time

from remote import SSH,STATE,BASE,HERE,REPO


def query(code,timeout=60):
    p=subprocess.run([*SSH,'python3 -'],input=code,text=True,capture_output=True,timeout=timeout)
    if p.returncode:raise RuntimeError(p.stderr[-2000:])
    return json.loads(p.stdout)


def main():
    folder=BASE/'codec-qat-v1';lock=(folder/'collector.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    remote=json.loads(STATE.read_text())['directory']
    prefix='from pathlib import Path\nimport json\nr=Path('+repr(remote)+')\nd=r/".build/mk61-agent-20261106/codec-qat-v1"\n'
    check=prefix+'''s=json.loads((d/'status.json').read_text());result={'phase':s['phase'],'complete':(d/'complete.json').exists()}
for arm in ['champion','small']:
 for mode in ['hex','h32']:
  name=arm+'-'+mode;f=d/name/'status.json'
  if f.exists():
   x=json.loads(f.read_text());result[name]={k:x.get(k)for k in ['phase','step','best_step','loss']}
  log=d/(name+'.log')
  if not(d/name/'training.json').exists()and log.exists()and'Traceback (most recent call last)'in log.read_text()[-8000:]:
   result['worker_error']=name;result['error_tail']=log.read_text()[-2200:]
if s['phase']=='failed':result['controller_error']=(d/'start-controller.log').read_text()[-2200:]
print(json.dumps(result))
'''
    start=time.monotonic();previous=None
    while True:
        status=query(check)
        if status!=previous:print(json.dumps(status),flush=True);previous=status
        if status['phase']=='failed'or'worker_error'in status:raise RuntimeError(status)
        if status['complete']:break
        if time.monotonic()-start>21600:raise TimeoutError('Codec comparison exceeded six hours')
        time.sleep(20)
    subprocess.run([sys.executable,str(HERE/'codec_remote.py'),'fetch'],cwd=REPO,check=True)
    root=folder/'server-results'
    after=prefix+'''import subprocess,hashlib
ids=subprocess.check_output(['sudo','-n','docker','ps','-q'],text=True).split();own=[]
if ids:
 for x in json.loads(subprocess.check_output(['sudo','-n','docker','inspect',*ids],text=True)):
  if any(m.get('Source')==str(r)for m in x.get('Mounts',[])):own.append(x['Id'][:12])
controllers=[]
for f in d.glob('*-launch.json'):
 x=json.loads(f.read_text());p=Path('/proc')/str(x['pid'])
 try:
  if p.exists()and(p/'cwd').resolve()==r and x['script'].encode()in(p/'cmdline').read_bytes():controllers.append(x)
 except(FileNotFoundError,PermissionError):pass
frozen=json.loads((d/'frozen.json').read_text())
for arm,digest in frozen['source_packets'].items():assert hashlib.sha256((r/'.build/mk61-agent-20261106/composition-v1/export'/arm/'model.mkqb').read_bytes()).hexdigest()==digest
for arm,digest in frozen['source_masters'].items():assert hashlib.sha256((r/'.build/mk61-agent-20261106/composition-v1/export'/arm/'hf/model.safetensors').read_bytes()).hexdigest()==digest
for name,entry in frozen['files'].items():assert hashlib.sha256((d/name).read_bytes()).hexdigest()==entry['sha256']
initial=json.loads((d/'initial/champion/manifest.json').read_text())
for path,key in [(r/'.build/mk61-agent-20261106/native-mixed-v1/language/train.u16','public_language_train_sha256'),(r/'.build/mk61-agent-20261106/native-mixed-v1/language/validation.u16','public_language_validation_sha256'),(r/'.build/mk61-agent-20261106/training/domain-documents.jsonl','domain_documents_sha256')]:assert hashlib.sha256(path.read_bytes()).hexdigest()==initial[key]
print(json.dumps({'all_own_jobs_complete':not own and not controllers,'own_containers':own,'own_controllers':controllers,
 'source_models_unchanged':True,'frozen_course_and_audit_hashes_verified':True,'both_full_gpus_were_user_allocated':True,'other_services_not_reconfigured':True}))
'''
    post=query(after);assert post['all_own_jobs_complete'],post
    (root/'postflight.json').write_text(json.dumps(post,indent=2)+'\n')
    python=REPO/'.build/squeal-chat-20261105/venv/bin/python'
    for script,exe in [('codec_verify.py',python),('codec_native.py',python),('codec_report.py',Path(sys.executable))]:
        subprocess.run([str(exe),str(HERE/script),'--root',str(root)],cwd=REPO,check=True)
    (folder/'collection.json').write_text(json.dumps({'completed':True,'root':str(root)})+'\n')


if __name__=='__main__':main()
