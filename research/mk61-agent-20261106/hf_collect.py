"""Wait for both learners, collect immutable results and verify native packages."""
import json
import subprocess
import sys
import time

from remote import SSH,STATE,REPO,HERE,BASE

ROOT=BASE/'harness-debug-v3'
PYTHON=REPO/'.build/squeal-chat-20261105/venv/bin/python'


def remote(source):
    last=None
    for attempt in range(3):
        result=subprocess.run([*SSH,'python3 -'],input=source,text=True,capture_output=True,timeout=90)
        if result.returncode==0:return result.stdout
        last=result.stderr[-2500:]
        if attempt<2:time.sleep(5)
    raise RuntimeError(last)


def main():
    source_root=json.loads(STATE.read_text())['directory'];deadline=time.monotonic()+8*3600;previous=None
    while time.monotonic()<deadline:
        source='''from pathlib import Path
import json
d=Path(REMOTE)/'.build/mk61-agent-20261106/harness-debug-v3'
result={}
for name,path in [('root',d/'status.json'),('safe',d/'safe/status.json'),('active',d/'active/status.json')]:
 if path.exists():result[name]=json.loads(path.read_text())
print(json.dumps(result))
'''.replace('REMOTE',repr(source_root))
        value=json.loads(remote(source));(ROOT/'monitor-status.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
        thin={name:{k:v for k,v in row.items()if k not in ['counts','sample_plan_digest']}for name,row in value.items()}
        if thin!=previous:print(json.dumps(thin,ensure_ascii=False),flush=True);previous=thin
        phase=value.get('root',{}).get('phase')
        if phase=='failed':raise RuntimeError(str(value['root']))
        if phase=='complete':break
        time.sleep(20)
    else:raise RuntimeError('Harness experiment deadline exceeded')
    subprocess.run([sys.executable,str(HERE/'hf_remote.py'),'fetch'],cwd=REPO,check=True,timeout=1200)
    root=ROOT/'server-results'
    source='''from pathlib import Path
import hashlib,json,subprocess
r=Path(REMOTE);d=r/'.build/mk61-agent-20261106/harness-debug-v3'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
prepared=json.loads((d/'prepared.json').read_text());base=json.loads((d/'data-frozen.json').read_text())
for names in [prepared['files'],base['files']]:
 for name,digest in names.items():assert sha(d/name)==digest,name
for name,digest in base['private_core_files'].items():assert sha(d/'core-source'/name)==digest
initial=r/'.build/mk61-agent-20261106/harness-debug-v2/export/selected-budget'
assert sha(initial/'hf/model.safetensors')==prepared['initial_master_sha256']
assert sha(initial/'model.mkqb')==prepared['initial_packet_sha256']
for name,digest in prepared['language_streams'].items():assert sha(r/'.build/mk61-agent-20261106/native-mixed-v1/language'/name)==digest
ours=[]
for identity in subprocess.check_output(['sudo','-n','docker','ps','-q'],text=True).split():
 item=json.loads(subprocess.check_output(['sudo','-n','docker','inspect',identity],text=True))[0]
 if any(m.get('Source')==str(r)for m in item['Mounts']):ours.append(identity)
assert not ours,ours
item=json.loads((d/'launch.json').read_text());p=Path('/proc')/str(item['pid'])
assert not(p.exists()and b'hf_round.py'in(p/'cmdline').read_bytes()and(p/'cwd').resolve()==r)
print(json.dumps({'all_frozen_files_unchanged':True,'source_checkpoint_unchanged':True,'language_streams_unchanged':True,
 'private_core_unchanged':True,'own_running_containers':ours,'own_running_controllers':[],
 'gpu_state':subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader'],text=True)}))
'''.replace('REMOTE',repr(source_root))
    (root/'postflight.json').write_text(json.dumps(json.loads(remote(source)),indent=2)+'\n')
    subprocess.run([str(PYTHON),str(HERE/'hf_verify.py'),'--root',str(root)],cwd=REPO,check=True,timeout=10800)
    subprocess.run([str(PYTHON),str(HERE/'hf_report.py'),'--root',str(root)],cwd=REPO,check=True,timeout=1200)
    (ROOT/'collection-failed.json').unlink(missing_ok=True)
    result={'completed':True,'root':str(root),'report':str(HERE/'HARNESS_DEBUG_V3_RESULTS.md'),'unix':time.time()}
    (ROOT/'collection.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)


if __name__=='__main__':
    try:main()
    except BaseException as error:
        (ROOT/'collection-failed.json').write_text(json.dumps({'error':repr(error),'unix':time.time()})+'\n');raise
