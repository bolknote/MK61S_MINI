"""Complete the authorized classifier correction and native verification."""
import json
import subprocess
import sys
import time
from pathlib import Path
from remote import SSH,STATE,REPO,HERE,BASE

ROOT=BASE/'semantic-cross-v1'
PYTHON=REPO/'.build/squeal-chat-20261105/venv/bin/python'


def remote(source):
    for attempt in range(3):
        p=subprocess.run([*SSH,'python3 -'],input=source,text=True,capture_output=True,timeout=60)
        if p.returncode==0:return p.stdout
        if attempt==2:raise RuntimeError(p.stderr[-2000:])


def main():
    directory=json.loads(STATE.read_text())['directory'];previous=None;deadline=time.monotonic()+6*3600
    while time.monotonic()<deadline:
        s='''from pathlib import Path
import json
r=Path(REMOTE)/'.build/mk61-agent-20261106/semantic-cross-v1';v={}
for n,p in [('root',r/'status.json'),('coupling',r/'coupling-status.json'),('late',r/'late/status.json'),('all',r/'all/status.json')]:
 if p.exists():v[n]=json.loads(p.read_text())
print(json.dumps(v))
'''.replace('REMOTE',repr(directory))
        value=json.loads(remote(s));(ROOT/'monitor-status.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
        if value!=previous:print(json.dumps(value,ensure_ascii=False),flush=True);previous=value
        phase=value.get('root',{}).get('phase')
        if phase=='failed':raise RuntimeError(value['root'])
        coupling=value.get('coupling',{}).get('phase')
        if coupling=='failed':raise RuntimeError(value['coupling'])
        if phase=='complete'and coupling=='complete':break
        time.sleep(20)
    else:raise RuntimeError('Classifier correction deadline exceeded')
    subprocess.run([sys.executable,str(HERE/'al_remote.py'),'fetch'],cwd=REPO,check=True,timeout=1800);target=ROOT/'server-results'
    source='''from pathlib import Path
import json,hashlib,subprocess
r=Path(REMOTE);d=r/'.build/mk61-agent-20261106/semantic-cross-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for n in ['data-frozen.json','prepared.json']:
 for name,digest in json.loads((d/n).read_text())['files'].items():assert sha(d/name)==digest,name
p=json.loads((d/'prepared.json').read_text())
for name,digest in p['source_hashes'].items():assert sha(r/'research/mk61-agent-20261106'/name)==digest,name
f=json.loads((d/'data-frozen.json').read_text());parent=r/'.build/mk61-agent-20261106/completion-retention-v2/export/lr10-terminal'
assert sha(parent/'hf/model.safetensors')==f['source_master_sha256']and sha(parent/'model.mkqb')==f['source_packet_sha256']
ours=[]
for identity in subprocess.check_output(['sudo','-n','docker','ps','-q'],text=True).split():
 v=json.loads(subprocess.check_output(['sudo','-n','docker','inspect',identity],text=True))[0]
 if any(m.get('Source')==str(r)for m in v['Mounts']):ours.append(identity)
assert not ours
print(json.dumps({'all_frozen_data_sources_verified':True,'own_running_containers':ours,
 'gpu_state':subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader'],text=True)}))
'''.replace('REMOTE',repr(directory))
    (target/'postflight.json').write_text(json.dumps(json.loads(remote(source)),indent=2)+'\n')
    for script in ['al_verify.py','al_report.py']:subprocess.run([str(PYTHON),str(HERE/script),'--root',str(target)],cwd=REPO,check=True,timeout=7200)
    (ROOT/'collection-failed.json').unlink(missing_ok=True);result={'completed':True,'root':str(target),'report':str(HERE/'SEMANTIC_CROSS_RESULTS.md'),'unix':time.time()}
    (ROOT/'collection.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)


if __name__=='__main__':
    try:main()
    except BaseException as error:
        (ROOT/'collection-failed.json').write_text(json.dumps({'error':repr(error),'unix':time.time()})+'\n');raise
