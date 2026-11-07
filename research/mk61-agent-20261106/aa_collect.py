"""Follow this bounded experiment through collection and native verification."""
import json
from pathlib import Path
import subprocess
import sys
import time
from remote import SSH,STATE,REPO,HERE,BASE

ROOT=BASE/'action-alignment-v1'
PYTHON=REPO/'.build/squeal-chat-20261105/venv/bin/python'


def remote(source):
    last=None
    for attempt in range(3):
        result=subprocess.run([*SSH,'python3 -'],input=source,text=True,capture_output=True,timeout=60)
        if result.returncode==0:return result.stdout
        last=result.stderr[-2200:]
        if attempt<2:time.sleep(3)
    raise RuntimeError(last)


def main():
    root=json.loads(STATE.read_text())['directory'];deadline=time.monotonic()+8*3600;previous=None
    while time.monotonic()<deadline:
        source='''from pathlib import Path
import json
d=Path(REMOTE)/'.build/mk61-agent-20261106/action-alignment-v1'
value={}
for key,p in [('root',d/'status.json')]+[(a,d/a/'status.json')for a in ['warmup','sft','preference']]:
 if p.exists():value[key]=json.loads(p.read_text())
print(json.dumps(value))
'''.replace('REMOTE',repr(root))
        value=json.loads(remote(source));(ROOT/'monitor-status.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
        if value!=previous:print(json.dumps(value,ensure_ascii=False),flush=True);previous=value
        phase=value.get('root',{}).get('phase')
        if phase=='failed':raise RuntimeError(str(value['root']))
        if phase=='complete':break
        time.sleep(20)
    else:raise RuntimeError('Action experiment deadline exceeded')
    subprocess.run([sys.executable,str(HERE/'aa_remote.py'),'fetch'],cwd=REPO,check=True,timeout=1200)
    target=ROOT/'server-results'
    source='''from pathlib import Path
import json,hashlib,subprocess
r=Path(REMOTE);d=r/'.build/mk61-agent-20261106/action-alignment-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for n in ['data-frozen.json','prepared.json']:
 for name,digest in json.loads((d/n).read_text())['files'].items():assert sha(d/name)==digest,name
for name,digest in json.loads((d/'prepared.json').read_text())['source_hashes'].items():assert sha(r/'research/mk61-agent-20261106'/name)==digest,name
f=json.loads((d/'data-frozen.json').read_text());initial=r/'.build/mk61-agent-20261106/harness-debug-v3/export/selected-budget'
assert sha(initial/'hf/model.safetensors')==f['initial_master_sha256']
assert sha(initial/'model.mkqb')==f['initial_packet_sha256']
core={str(p.relative_to(d/'core-source')):sha(p)for p in(d/'core-source').rglob('*')if p.is_file()}
for name,digest in core.items():assert sha(r/'.build/mk61-agent-20261106/harness-debug-v3/core-source'/name)==digest,name
ours=[]
for identity in subprocess.check_output(['sudo','-n','docker','ps','-q'],text=True).split():
 item=json.loads(subprocess.check_output(['sudo','-n','docker','inspect',identity],text=True))[0]
 if any(m.get('Source')==str(r)for m in item['Mounts']):ours.append(identity)
assert not ours,ours
print(json.dumps({'all_frozen_files_and_sources_unchanged':True,'initial_master_and_packet_unchanged':True,
 'private_core_files':core,'own_running_containers':ours,
 'gpu_state':subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader'],text=True)}))
'''.replace('REMOTE',repr(root))
    (target/'postflight.json').write_text(json.dumps(json.loads(remote(source)),indent=2)+'\n')
    subprocess.run([str(PYTHON),str(HERE/'aa_verify.py'),'--root',str(target)],cwd=REPO,check=True,timeout=10800)
    subprocess.run([str(PYTHON),str(HERE/'aa_report.py'),'--root',str(target)],cwd=REPO,check=True,timeout=1200)
    (ROOT/'collection-failed.json').unlink(missing_ok=True)
    result={'completed':True,'root':str(target),'report':str(HERE/'ACTION_ALIGNMENT_RESULTS.md'),'unix':time.time()}
    (ROOT/'collection.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)


if __name__=='__main__':
    try:main()
    except BaseException as error:
        (ROOT/'collection-failed.json').write_text(json.dumps({'error':repr(error),'unix':time.time()})+'\n');raise
