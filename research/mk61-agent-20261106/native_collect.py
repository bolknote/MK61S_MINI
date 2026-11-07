"""Collect and verify the completed run; never starts or extends training."""
import fcntl
import json
from pathlib import Path
import subprocess
import sys
import time

from remote import SSH,STATE,REPO,BASE,HERE


def main():
    local=BASE/'native-mixed-v1';lock=(local/'collect.lock').open('a+')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    remote=json.loads(STATE.read_text())['directory']
    source='''from pathlib import Path
import json
r=Path('''+repr(remote)+''')/'.build/mk61-agent-20261106/native-mixed-v1'
out={'phase':json.loads((r/'status.json').read_text())['phase'],'finished':(r/'finish.json').exists()}
for arm in ['q4','mixed']:
 x=json.loads((r/(arm+'-sft/status.json')).read_text());out[arm]=x.get('step',x.get('phase'))
p=r/'finish-controller.log'
if p.exists()and'Traceback (most recent call last)'in p.read_text():out['finish_error']=p.read_text()[-2000:]
print(json.dumps(out))
'''
    started=time.monotonic();previous=None
    while True:
        response=subprocess.run([*SSH,'python3 -'],input=source,text=True,capture_output=True,timeout=60)
        if response.returncode:raise RuntimeError(response.stderr[-1500:])
        status=json.loads(response.stdout)
        if status!=previous:print(json.dumps(status),flush=True);previous=status
        if status.get('finish_error')or status['phase']=='failed':raise RuntimeError(status)
        if status['finished']:break
        if time.monotonic()-started>7200:raise TimeoutError('Comparison did not finish')
        time.sleep(20)
    root=local/'server-results'
    commands=[
      [sys.executable,str(HERE/'native_remote.py'),'fetch-review'],
      [sys.executable,str(HERE/'native_postflight.py'),'--root',str(root)],
      [str(REPO/'.build/squeal-chat-20261105/venv/bin/python'),str(HERE/'native_verify.py'),'--root',str(root)],
      [sys.executable,str(HERE/'native_report.py'),'--root',str(root)]]
    for command in commands:subprocess.run(command,cwd=REPO,check=True)
    (local/'collection.json').write_text(json.dumps({'completed':True,'root':str(root)})+'\n')


if __name__=='__main__':main()
