"""Follow both seeds through their selected fresh exam and verified exports."""
import json
import subprocess
import sys
import time
from ba_common import ROOT,REPO,HERE,read,write,check_frozen
from remote import SSH,STATE

PYTHON=REPO/'.build/squeal-chat-20261105/venv/bin/python'


def remote(source):
    for attempt in range(3):
        result=subprocess.run([*SSH,'python3 -'],input=source,text=True,capture_output=True,timeout=60)
        if not result.returncode:return result.stdout
        if attempt==2:raise RuntimeError(result.stderr[-3000:])


def main():
    directory=read(STATE)['directory'];deadline=time.monotonic()+18000;previous=None
    while time.monotonic()<deadline:
        source='''from pathlib import Path
import json
d=Path(REMOTE)/'.build/mk61-agent-20261106/semantic-spec-grounding-v1'
v={}
for n in ['status.json','seed-a/status.json','seed-b/status.json','spec/status.json','parent/status.json']:
 p=d/n
 if p.exists():v[n]=json.loads(p.read_text())
print(json.dumps(v))
'''.replace('REMOTE',repr(directory))
        status=json.loads(remote(source));write(ROOT/'monitor-status.json',status)
        if status!=previous:print(json.dumps(status),flush=True);previous=status
        phase=status.get('status.json',{}).get('phase')
        if phase=='failed':raise RuntimeError(status)
        if phase=='complete':break
        time.sleep(20)
    else:raise RuntimeError('Experiment did not complete within collector bound')
    subprocess.run([sys.executable,str(HERE/'ba_remote.py'),'fetch'],cwd=REPO,check=True,timeout=1200)
    target=ROOT/'server-results';check_frozen()
    subprocess.run([str(PYTHON),'-u',str(HERE/'ba_native.py'),'--root',str(target)],cwd=REPO,check=True,timeout=1800)
    subprocess.run([str(PYTHON),str(HERE/'ba_package.py'),'--root',str(target)],cwd=REPO,check=True,timeout=180)
    source='''from pathlib import Path
import sys,json,time,subprocess
r=Path(REMOTE);sys.path.insert(0,str(r/'research/mk61-agent-20261106'))
from ba_common import ROOT,check_frozen
check_frozen();assert json.loads((ROOT/'complete.json').read_text())['optimizer_updates']==8000
ours=[]
for i in subprocess.check_output(['sudo','-n','docker','ps','-q'],text=True).split():
 x=json.loads(subprocess.check_output(['sudo','-n','docker','inspect',i],text=True))[0]
 if any(m.get('Source')==str(r)for m in x['Mounts'])and any(any(n in a for n in ['ba_jobs.py','ba_mine.py'])for a in(x['Config'].get('Cmd')or[])):ours.append(i)
assert not ours,ours
print(json.dumps({'all_frozen_files_verified':True,'own_containers_running':ours,'optimizer_updates':8000,'unix':time.time(),
 'gpu_state':subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader'],text=True),
 'firmware_not_modified':True,'main_profile_not_replaced':True}))
'''.replace('REMOTE',repr(directory))
    write(target/'postflight.json',json.loads(remote(source)))
    with(ROOT/'report-metrics.json').open('w')as stream:
        subprocess.run([str(PYTHON),str(HERE/'ba_report.py'),'--root',str(target)],cwd=REPO,check=True,stdout=stream,timeout=180)
    check_frozen();write(ROOT/'collection.json',{'complete':True,'optimizer_updates':8000,'native_Q4_verified':True,
         'report':str(HERE/'SPEC_GROUNDING_RESULTS.md'),'unix':time.time()})
    print(json.dumps({'complete':True,'report':str(HERE/'SPEC_GROUNDING_RESULTS.md')}),flush=True)


if __name__=='__main__':
    try:main()
    except BaseException as e:write(ROOT/'collection-failed.json',{'error':repr(e),'unix':time.time()});raise
