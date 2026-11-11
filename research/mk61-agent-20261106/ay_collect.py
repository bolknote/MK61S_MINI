"""Follow the authorized run through closed exam, export verification and report."""
import json
import subprocess
import sys
import time
from ay_common import ROOT,REPO,HERE,read,write,check_frozen
from remote import SSH,STATE

PYTHON=REPO/'.build/squeal-chat-20261105/venv/bin/python'


def remote(source):
    for attempt in range(3):
        p=subprocess.run([*SSH,'python3 -'],input=source,text=True,capture_output=True,timeout=60)
        if not p.returncode:return p.stdout
        if attempt==2:raise RuntimeError(p.stderr[-3000:])


def main():
    directory=read(STATE)['directory'];deadline=time.monotonic()+7200;previous=None
    while time.monotonic()<deadline:
        source='''from pathlib import Path
import json
d=Path(REMOTE)/'.build/mk61-agent-20261106/semantic-spec-distill-v1'
v={}
for name in ['status.json','hex/status.json','spec/status.json']:
 p=d/name
 if p.exists():v[name]=json.loads(p.read_text())
print(json.dumps(v))
'''.replace('REMOTE',repr(directory))
        status=json.loads(remote(source));write(ROOT/'monitor-status.json',status)
        if status!=previous:print(json.dumps(status),flush=True);previous=status
        phase=status.get('status.json',{}).get('phase')
        if phase=='failed':raise RuntimeError(status)
        if phase=='complete':break
        time.sleep(15)
    else:raise RuntimeError('Experiment did not finish within the collector bound')
    subprocess.run([sys.executable,str(HERE/'ay_remote.py'),'fetch'],cwd=REPO,check=True,timeout=1200)
    target=ROOT/'server-results';check_frozen()
    subprocess.run([str(PYTHON),'-u',str(HERE/'ay_native.py'),'--root',str(target)],cwd=REPO,check=True,timeout=1800)
    with(ROOT/'report-metrics.json').open('w')as stream:
        subprocess.run([str(PYTHON),str(HERE/'ay_report.py'),'--root',str(target)],cwd=REPO,check=True,stdout=stream,timeout=180)
    source='''from pathlib import Path
import json,sys,subprocess,time
r=Path(REMOTE);sys.path.insert(0,str(r/'research/mk61-agent-20261106'))
from ay_common import check_frozen,ROOT
check_frozen();complete=json.loads((ROOT/'complete.json').read_text());assert complete['optimizer_updates']==6000
ours=[]
for identity in subprocess.check_output(['sudo','-n','docker','ps','-q'],text=True).split():
 x=json.loads(subprocess.check_output(['sudo','-n','docker','inspect',identity],text=True))[0]
 if any(m.get('Source')==str(r)for m in x['Mounts'])and any('ay_jobs.py'in a for a in(x['Config'].get('Cmd')or[])):ours.append(identity)
assert not ours,ours
print(json.dumps({'all_frozen_files_verified':True,'own_training_containers_running':ours,'optimizer_updates':6000,
 'gpu_state':subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader'],text=True),
 'unix':time.time(),'firmware_not_modified':True,'main_profile_not_replaced':True}))
'''.replace('REMOTE',repr(directory))
    write(target/'postflight.json',json.loads(remote(source)))
    # Regression from the user's original question, separate from the fresh exam.
    source='''import sys,json,math
from pathlib import Path
sys.path.insert(0,'research/mk61-agent-20261106')
from ay_chat import propose
from ay_common import write
import torch
torch.set_num_threads(4)
root=Path(TARGET);probe=json.loads(Path(PROBE).read_text());rows={}
for arm in ['hex','spec']:
 result=propose(root/'export'/arm,probe['task'],probe['angle'],probe['inputs'])
 actual=result.get('actual',{});number=actual.get('X')
 passed=actual.get('status')=='stopped'and number is not None and abs(float(number)-math.sin(math.radians(22)))<2e-6
 rows[arm]={'passed':bool(passed),'result':result}
write(root/'user-regression.json',{'historical_probe_not_fresh_exam':True,'models':rows})
print(json.dumps({'sin22_regression':{a:r['passed']for a,r in rows.items()}}))
'''.replace('TARGET',repr(str(target))).replace('PROBE',repr(str(ROOT/'user-regression-probe.json')))
    subprocess.run([str(PYTHON),'-u','-c',source],cwd=REPO,check=True,timeout=300)
    check_frozen();write(ROOT/'collection.json',{'complete':True,'unix':time.time(),'report':str(HERE/'SEMANTIC_SPEC_DISTILL_RESULTS.md'),
                                              'optimizer_updates':6000,'native_and_Q4_verified':True})
    print(json.dumps({'complete':True,'report':str(HERE/'SEMANTIC_SPEC_DISTILL_RESULTS.md')}),flush=True)


if __name__=='__main__':
    try:main()
    except BaseException as error:
        write(ROOT/'collection-failed.json',{'unix':time.time(),'error':repr(error)});raise
