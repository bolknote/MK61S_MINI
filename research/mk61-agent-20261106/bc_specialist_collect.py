"""Collect only the supplementary profile, preserving previously verified exports."""
import json
import shlex
import subprocess
import sys
import tarfile
import time
from bc_common import ROOT,REPO,write,read
from remote import SSH,STATE


def main():
    remote=read(STATE)['directory'];target=ROOT/'server-results'
    prefix='from pathlib import Path\nimport json,sys,time\nr=Path('+repr(remote)+')\nd=r/".build/mk61-agent-20261106/semantic-spec-selfcheck-v1"\n'
    while True:
        command=prefix+'p=d/"safety/status.json"\nprint(p.read_text()if p.exists()else"{}")\n'
        result=subprocess.run([*SSH,'python3 -c '+shlex.quote(command)],text=True,capture_output=True)
        if result.returncode:
            print(json.dumps({'temporary_SSH_failure':result.returncode}),flush=True);time.sleep(15);continue
        status=json.loads(result.stdout);print(json.dumps(status),flush=True)
        if status.get('phase')=='complete':break
        time.sleep(20)
    command=prefix+'''import tarfile
t=tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz')
for base in ['specialist-policy.json','safety','export/safety']:
 p=d/base
 values=[p]if p.is_file()else sorted(p.rglob('*'))
 for f in values:
  if f.is_file():t.add(f,arcname=str(f.relative_to(d)),recursive=False)
t.close()
'''
    child=subprocess.Popen([*SSH,'python3 -c '+shlex.quote(command)],stdout=subprocess.PIPE)
    with tarfile.open(fileobj=child.stdout,mode='r|gz')as stream:stream.extractall(target,filter='data')
    assert child.wait()==0
    python=REPO/'.build/squeal-chat-20261105/venv/bin/python'
    subprocess.run([str(python),'research/mk61-agent-20261106/bc_native.py','--root',str(target),'--supplementary'],cwd=REPO,check=True)
    write(target/'supplementary-collection.json',{'complete':True,'optimizer_updates':0,'unix':time.time()})


if __name__=='__main__':main()
