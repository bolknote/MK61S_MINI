"""Finish the authorized full ISA training and verification, with no GPU orphans."""
import json
import subprocess
import sys
import time

from remote import SSH,STATE,REPO,HERE,BASE

ROOT=BASE/'full-isa-v1'
PYTHON=REPO/'.build/squeal-chat-20261105/venv/bin/python'


def remote(source):
    result=subprocess.run([*SSH,'python3 -'],input=source,text=True,capture_output=True,timeout=90)
    if result.returncode:raise RuntimeError(result.stderr[-2600:])
    return result.stdout


def main():
    source_root=json.loads(STATE.read_text())['directory'];deadline=time.monotonic()+8*3600;started=False;previous=None
    while time.monotonic()<deadline:
        source='''from pathlib import Path
import json
d=Path(REMOTE)/'.build/mk61-agent-20261106/full-isa-v1'
result={}
for name,path in [('root',d/'status.json'),('teacher',d/'teacher/status.json'),('full',d/'full/status.json'),('protected',d/'protected/status.json')]:
 if path.exists():result[name]=json.loads(path.read_text())
print(json.dumps(result))
'''.replace('REMOTE',repr(source_root))
        value=json.loads(remote(source));(ROOT/'monitor-status.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
        thin={name:{k:v for k,v in row.items()if k not in ['counts','files','errors','sample_plan_digest']}for name,row in value.items()}
        if thin!=previous:print(json.dumps(thin,ensure_ascii=False),flush=True);previous=thin
        phase=value.get('root',{}).get('phase')
        if phase=='failed':raise RuntimeError('Own full ISA controller failed: '+str(value['root']))
        if phase=='full_isa_data_ready_teacher_released'and not started:
            subprocess.run([sys.executable,str(HERE/'full_isa_remote.py'),'start'],cwd=REPO,check=True);started=True
        if phase=='complete':break
        time.sleep(20)
    else:raise RuntimeError('Full ISA monitor exceeded deadline')
    subprocess.run([sys.executable,str(HERE/'full_isa_remote.py'),'fetch'],cwd=REPO,check=True,timeout=1200)
    root=ROOT/'server-results'
    source='''from pathlib import Path
import hashlib,json,subprocess
r=Path(REMOTE);d=r/'.build/mk61-agent-20261106/full-isa-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
prepared=json.loads((d/'prepared.json').read_text());base=json.loads((d/'data-frozen.json').read_text());policy=json.loads((d/'run-policy-frozen.json').read_text())
for names in [prepared['files'],base['files'],policy['files']]:
 for name,digest in names.items():assert sha(d/name)==digest,name
for name,digest in policy['private_core_files'].items():assert sha(d/'core-source'/name)==digest
initial=r/'.build/mk61-agent-20261106/codec-qat-v1/export/best/small-hex'
assert sha(initial/'hf/model.safetensors')==prepared['initial_master_sha256']
assert sha(initial/'model.mkqb')==prepared['initial_packet_sha256']
for name,digest in prepared['language_streams'].items():assert sha(r/'.build/mk61-agent-20261106/native-mixed-v1/language'/name)==digest
ours=[]
for identity in subprocess.check_output(['sudo','-n','docker','ps','-q'],text=True).split():
 item=json.loads(subprocess.check_output(['sudo','-n','docker','inspect',identity],text=True))[0]
 if(item['Config'].get('Labels')or{}).get('mk61.owner')=='full-isa-v1'or any(m.get('Source')==str(r)for m in item['Mounts']):ours.append(identity)
assert not ours,ours
active=[]
for marker in ['data-launch.json','start-launch.json']:
 item=json.loads((d/marker).read_text());p=Path('/proc')/str(item['pid'])
 if p.exists()and b'full_isa_round.py'in(p/'cmdline').read_bytes()and(p/'cwd').resolve()==r:active.append(item['pid'])
assert not active,active
print(json.dumps({'all_frozen_files_unchanged':True,'source_checkpoint_unchanged':True,'language_streams_unchanged':True,'private_core_unchanged':True,
 'own_running_containers':ours,'own_running_controllers':active,'gpu_state':subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader'],text=True)}))
'''.replace('REMOTE',repr(source_root))
    post=json.loads(remote(source));(root/'postflight.json').write_text(json.dumps(post,indent=2)+'\n')
    subprocess.run([str(PYTHON),str(HERE/'full_isa_verify.py'),'--root',str(root)],cwd=REPO,check=True,timeout=10800)
    subprocess.run([str(PYTHON),str(HERE/'full_isa_report.py'),'--root',str(root)],cwd=REPO,check=True,timeout=1200)
    (ROOT/'collection-failed.json').unlink(missing_ok=True)
    result={'completed':True,'root':str(root),'report':str(HERE/'FULL_ISA_RESULTS.md'),'unix':time.time()}
    (ROOT/'collection.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)


if __name__=='__main__':
    try:main()
    except BaseException as e:
        (ROOT/'collection-failed.json').write_text(json.dumps({'error':repr(e),'unix':time.time()})+'\n');raise
