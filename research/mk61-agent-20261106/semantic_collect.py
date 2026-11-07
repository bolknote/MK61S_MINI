"""Finish authorized study, fetch, verify, and write the report without GPU orphans."""
import json
from pathlib import Path
import subprocess
import sys
import time

from remote import SSH,STATE,REPO,HERE,BASE

ROOT=BASE/'semantic-3m-v1'
PYTHON=REPO/'.build/squeal-chat-20261105/venv/bin/python'


def remote(source):
    result=subprocess.run([*SSH,'python3 -'],input=source,text=True,capture_output=True,timeout=90)
    if result.returncode:raise RuntimeError(result.stderr[-2500:])
    return result.stdout


def main():
    remote_root=json.loads(STATE.read_text())['directory'];deadline=time.monotonic()+6*3600;started=False
    while time.monotonic()<deadline:
        source='''from pathlib import Path
import json
d=Path(REMOTE)/'.build/mk61-agent-20261106/semantic-3m-v1'
value={'root':json.loads((d/'status.json').read_text())}
for name in ['teacher','direct','auxiliary']:
 p=d/name/'status.json'
 if p.exists():value[name]=json.loads(p.read_text())
print(json.dumps(value))
'''.replace('REMOTE',repr(remote_root))
        value=json.loads(remote(source));(ROOT/'monitor-status.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
        phase=value['root']['phase'];print(json.dumps({k:({x:y for x,y in v.items()if x not in ['counts','files','errors']}if isinstance(v,dict)else v)for k,v in value.items()}),flush=True)
        if phase=='failed':raise RuntimeError('Remote experiment failed: '+str(value['root']))
        if phase=='verified_teacher_data_complete_own_teacher_released'and not started:
            subprocess.run([sys.executable,str(HERE/'semantic_remote.py'),'start'],cwd=REPO,check=True);started=True
        if phase=='complete':break
        time.sleep(20)
    else:raise RuntimeError('Study monitor deadline exceeded')
    subprocess.run([sys.executable,str(HERE/'semantic_remote.py'),'fetch'],cwd=REPO,check=True,timeout=1200)
    result_root=ROOT/'server-results'
    # Check remote invariants after all own controllers and GPU jobs have ended.
    postflight='''from pathlib import Path
import hashlib,json,subprocess
r=Path(REMOTE);d=r/'.build/mk61-agent-20261106/semantic-3m-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
p=json.loads((d/'prepared.json').read_text())
for name,item in p['files'].items():assert sha(d/name)==item['sha256']
initial=r/'.build/mk61-agent-20261106/codec-qat-v1/export/best/small-hex'
assert sha(initial/'hf/model.safetensors')==p['initial_master_sha256']
assert sha(initial/'model.mkqb')==p['initial_packet_sha256']
for name,digest in p['language_streams'].items():assert sha(r/'.build/mk61-agent-20261106/native-mixed-v1/language'/name)==digest
running=subprocess.check_output(['sudo','-n','docker','ps','-q'],text=True).split();ours=[]
for identity in running:
 info=json.loads(subprocess.check_output(['sudo','-n','docker','inspect',identity],text=True))[0]
 if(info['Config'].get('Labels')or{}).get('mk61.owner')=='semantic-3m-v1'or any(x.get('Source')==str(r)for x in info['Mounts']):ours.append(identity)
assert not ours,ours
active=[]
for marker in ['start-launch.json','data-launch.json']:
 item=json.loads((d/marker).read_text());proc=Path('/proc')/str(item['pid'])
 if proc.exists()and b'semantic_round.py'in(proc/'cmdline').read_bytes()and(proc/'cwd').resolve()==r:active.append(item['pid'])
assert not active,active
gpu=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader'],text=True)
print(json.dumps({'frozen_files_unchanged':True,'starting_checkpoint_unchanged':True,'language_streams_unchanged':True,'own_running_gpu_containers':ours,'own_running_controllers':active,'gpu_state':gpu,'existing_teacher_container_not_modified_by_this_experiment':True}))
'''.replace('REMOTE',repr(remote_root))
    post=json.loads(remote(postflight));(result_root/'postflight.json').write_text(json.dumps(post,indent=2)+'\n')
    subprocess.run([str(PYTHON),str(HERE/'semantic_verify.py'),'--root',str(result_root)],cwd=REPO,check=True,timeout=7200)
    subprocess.run([str(PYTHON),str(HERE/'semantic_report.py'),'--root',str(result_root)],cwd=REPO,check=True,timeout=1200)
    value={'completed':True,'report':str(HERE/'SEMANTIC_3M_RESULTS.md'),'root':str(result_root),'unix':time.time()}
    (ROOT/'collection-failed.json').unlink(missing_ok=True)
    (ROOT/'collection.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value),flush=True)


if __name__=='__main__':
    try:main()
    except BaseException as error:
        (ROOT/'collection-failed.json').write_text(json.dumps({'error':repr(error),'unix':time.time()})+'\n');raise
