"""Read back only our remote jobs/artifacts and shared teacher availability."""
import argparse
import json
from pathlib import Path
import subprocess

from remote import SSH,STATE


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args()
    remote=json.loads(STATE.read_text())['directory']
    source='''from pathlib import Path
import hashlib,json,subprocess,urllib.request
r=Path('''+repr(remote)+''');d=r/'.build/mk61-agent-20261106/native-mixed-v1'
assert (d/'finish.json').exists()
ids=subprocess.check_output(['sudo','-n','docker','ps','-q'],text=True).split()
own=[]
if ids:
 entries=json.loads(subprocess.check_output(['sudo','-n','docker','inspect',*ids],text=True))
 for entry in entries:
  if any(m.get('Source')==str(r)for m in entry.get('Mounts',[])):
   own.append({'id':entry['Id'][:12],'command':entry['Config'].get('Cmd')})
controllers=[]
for marker in d.glob('*-launch.json'):
 try:
  item=json.loads(marker.read_text());proc=Path('/proc')/str(item['pid'])
  if proc.exists()and(proc/'cwd').resolve()==r and item['script'].encode()in(proc/'cmdline').read_bytes():
   controllers.append(item)
 except (FileNotFoundError,PermissionError):pass
with urllib.request.urlopen('http://127.0.0.1:8000/v1/models',timeout=10)as response:
 teacher_status=response.status
original=r/'.build/mk61-agent-20261106/flourish-original/model.safetensors'
digest=hashlib.sha256(original.read_bytes()).hexdigest()
assert digest=='3bd64747ce1d4709f58d1522c95e390fd2dc5b1bc21b7e02ab18a99e9c676990'
result={'all_own_jobs_complete':not own and not controllers,'own_containers':own,
 'own_active_controllers':controllers,'shared_teacher_http_status':teacher_status,
 'original_checkpoint_unchanged':True,'original_sha256':digest,
 'comparison_complete':json.loads((d/'complete.json').read_text())['completed'],
 'native_device_measured':False}
print(json.dumps(result))
'''
    result=subprocess.run([*SSH,'python3 -'],input=source,text=True,capture_output=True)
    if result.returncode:raise RuntimeError(result.stderr[-2000:])
    report=json.loads(result.stdout);assert report['all_own_jobs_complete'],report
    a.root.mkdir(parents=True,exist_ok=True)
    (a.root/'postflight.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
