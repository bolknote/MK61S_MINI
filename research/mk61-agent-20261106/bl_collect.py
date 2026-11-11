"""Follow both trainings and the sealed exam, then verify all three Q4 exports."""
import json
import subprocess
import sys
import time
from bl_common import ROOT,HERE,REPO,read,write
from remote import SSH,STATE

def main():
    remote=read(STATE)['directory'];deadline=time.monotonic()+28800;previous=None
    while time.monotonic()<deadline:
        code='''from pathlib import Path
import json
d=Path(REMOTE)/'.build/mk61-agent-20261106/spec-compact-own-errors-v1'
v={}
for n in ['status.json','lora/status.json','full/status.json','parent_lora/status.json','parent_full/status.json']:
 p=d/n
 if p.exists():v[n]=json.loads(p.read_text())
print(json.dumps(v))
'''.replace('REMOTE',repr(remote))
        result=subprocess.run([*SSH,'python3 -'],input=code,text=True,capture_output=True,timeout=60)
        if result.returncode:
            print(json.dumps({'temporary_SSH_failure':result.returncode}),flush=True);time.sleep(15);continue
        value=json.loads(result.stdout)
        if value!=previous:print(json.dumps(value),flush=True);previous=value
        if value.get('status.json',{}).get('phase')=='complete':break
        if value.get('status.json',{}).get('phase')=='failed':raise RuntimeError(value)
        time.sleep(20)
    else:raise RuntimeError('Training/evaluation deadline exceeded')
    subprocess.run([sys.executable,str(HERE/'bl_remote.py'),'fetch'],cwd=REPO,check=True)
    python=REPO/'.build/squeal-chat-20261105/venv/bin/python'
    subprocess.run([str(python),'-u',str(HERE/'bl_native.py'),'--root',str(ROOT/'server-results')],cwd=REPO,check=True)
    write(ROOT/'collection.json',{'complete':True,'optimizer_updates':6000,'unix':time.time()})

if __name__=='__main__':main()
