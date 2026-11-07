"""Keep the foreground task running through collection, verification and report."""
import fcntl
import json
from pathlib import Path
import subprocess
import sys
import time

from remote import SSH,STATE,BASE,HERE,REPO


def remote_read(source,timeout=60):
    response=subprocess.run([*SSH,'python3 -'],input=source,text=True,capture_output=True,timeout=timeout)
    if response.returncode:raise RuntimeError(response.stderr[-2000:])
    return json.loads(response.stdout)


def main():
    local=BASE/'composition-v1';lock=(local/'collection.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    directory=json.loads(STATE.read_text())['directory']
    prefix='from pathlib import Path\nimport json\nr=Path('+repr(directory)+')\nd=r/".build/mk61-agent-20261106/composition-v1"\n'
    source=prefix+'''x=json.loads((d/'status.json').read_text());result={'phase':x['phase'],'course_phase':x.get('course_phase'),'complete':(d/'complete.json').exists()}
for arm in ['champion','small']:
 p=d/(arm+'-phase'+str(x.get('course_phase',1))) /'status.json'
 if p.exists():
  v=json.loads(p.read_text());result[arm]={k:v.get(k)for k in ['phase','step','best_step','loss']}
if x['phase']=='failed':result['error']=(d/'start-controller.log').read_text()[-2500:]
print(json.dumps(result))
'''
    started=time.monotonic();previous=None
    while True:
        status=remote_read(source)
        if status!=previous:print(json.dumps(status),flush=True);previous=status
        if status['phase']=='failed':raise RuntimeError(status)
        if status['complete']:break
        if time.monotonic()-started>21600:raise TimeoutError('Composition comparison did not complete')
        time.sleep(20)
    checks=prefix+'''import subprocess
with(d/'postselection-regression.log').open('a')as log:
 subprocess.run(['python3','research/mk61-agent-20261106/compose_regression.py'],cwd=r,stdout=log,stderr=subprocess.STDOUT,check=True)
print(json.dumps({'postselection_formal_regression_complete':True}))
'''
    print(json.dumps(remote_read(checks,timeout=10800)),flush=True)
    subprocess.run([sys.executable,str(HERE/'compose_remote.py'),'fetch'],cwd=REPO,check=True)
    root=local/'server-results'
    source=prefix+'''import subprocess,urllib.request,hashlib
ids=subprocess.check_output(['sudo','-n','docker','ps','-q'],text=True).split();own=[]
if ids:
 for item in json.loads(subprocess.check_output(['sudo','-n','docker','inspect',*ids],text=True)):
  if any(m.get('Source')==str(r)for m in item.get('Mounts',[])):own.append(item['Id'][:12])
controllers=[]
for marker in d.glob('*-launch.json'):
 item=json.loads(marker.read_text());proc=Path('/proc')/str(item['pid'])
 try:
  if proc.exists()and(proc/'cwd').resolve()==r and item['script'].encode()in(proc/'cmdline').read_bytes():controllers.append(item)
 except (FileNotFoundError,PermissionError):pass
with urllib.request.urlopen('http://127.0.0.1:8000/v1/models',timeout=10)as f:teacher=f.status
frozen=json.loads((d/'frozen.json').read_text());sources={'champion':r/'.build/mk61-agent-20261106/native-mixed-v1/export/selected-budget/model.mkqb','small':r/'.build/mk61-agent-20261106/capacity-v1/export/selected-budget/model.mkq4'}
for arm,path in sources.items():assert hashlib.sha256(path.read_bytes()).hexdigest()==frozen['source_packets'][arm]
print(json.dumps({'all_own_jobs_complete':not own and not controllers,'own_containers':own,'own_active_controllers':controllers,'shared_teacher_http_status':teacher,'both_source_packets_unchanged':True,'native_device_measured':False}))
'''
    report=remote_read(source);assert report['all_own_jobs_complete'],report
    (root/'postflight.json').write_text(json.dumps(report,indent=2)+'\n')
    subprocess.run([str(REPO/'.build/squeal-chat-20261105/venv/bin/python'),str(HERE/'compose_verify.py'),'--root',str(root)],cwd=REPO,check=True)
    subprocess.run([sys.executable,str(HERE/'compose_report.py'),'--root',str(root)],cwd=REPO,check=True)
    (local/'collection.json').write_text(json.dumps({'completed':True,'root':str(root)})+'\n')


if __name__=='__main__':main()
