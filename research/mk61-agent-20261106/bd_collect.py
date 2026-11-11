"""Wait for the entire zero-update diagnostic, then collect its unchanged model evidence."""
import json
import subprocess
import sys
import time
from bd_common import ROOT,HERE,REPO,read,write
from remote import SSH,STATE


def main():
    remote=read(STATE)['directory'];deadline=time.monotonic()+10800;previous=None
    while time.monotonic()<deadline:
        source='from pathlib import Path\nimport json\np=Path('+repr(remote)+')/".build/mk61-agent-20261106/spec-factorial-diagnostic-v1/status.json"\nprint(p.read_text()if p.exists()else"{}")\n'
        result=subprocess.run([*SSH,'python3 -'],input=source,text=True,capture_output=True,timeout=60)
        if result.returncode:
            print(json.dumps({'temporary_SSH_failure':result.returncode}),flush=True);time.sleep(15);continue
        value=json.loads(result.stdout)
        if value!=previous:print(json.dumps(value),flush=True);previous=value
        if value.get('phase')=='complete':break
        if value.get('phase')=='failed':raise RuntimeError(value)
        time.sleep(20)
    else:raise RuntimeError('Diagnostic deadline exceeded')
    subprocess.run([sys.executable,str(HERE/'bd_remote.py'),'fetch'],cwd=REPO,check=True)
    python=REPO/'.build/squeal-chat-20261105/venv/bin/python'
    subprocess.run([str(python),'-u',str(HERE/'bd_native.py'),'--root',str(ROOT/'server-results')],cwd=REPO,check=True)
    write(ROOT/'collection.json',{'complete':True,'optimizer_updates':0,'unix':time.time()})


if __name__=='__main__':main()
