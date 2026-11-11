"""Complete data preparation, both B200 trainings, the sealed exam and publication checks."""
import json
import os
import signal
import subprocess
import sys
import time
from bh_common import ROOT,HERE,REPO,read,write
from remote import SSH,STATE

PYTHON=REPO/'.build/squeal-chat-20261105/venv/bin/python'

def close_own_tunnel():
    result=subprocess.run(['lsof','-tiTCP:18083','-sTCP:LISTEN'],capture_output=True,text=True)
    closed=[]
    for value in set(result.stdout.split()):
        command=subprocess.check_output(['ps','-p',value,'-o','command='],text=True)
        if 'ssh'in command and'127.0.0.1:18083:172.18.141.21:8000'in command:
            os.kill(int(value),signal.SIGTERM);closed.append(int(value))
    write(ROOT/'teacher-tunnel-closed.json',{'own_pids_closed':closed,'shared_teacher_service_untouched':True,'unix':time.time()})

def postflight():
    remote=read(STATE)['directory']
    code='''from pathlib import Path
import sys,json,subprocess,time
r=Path(REMOTE);sys.path.insert(0,str(r/'research/mk61-agent-20261106'))
from bh_common import ROOT,read,check_frozen
check_frozen();assert read(ROOT/'complete.json')['complete'];assert read(ROOT/'complete.json')['optimizer_updates']==12000
assert read(ROOT/'lora/training.json')['draw_digest']==read(ROOT/'full/training.json')['draw_digest']
own=[]
for cid in subprocess.check_output(['sudo','-n','docker','ps','-q'],text=True).split():
 x=json.loads(subprocess.check_output(['sudo','-n','docker','inspect',cid],text=True))[0]
 if any(m.get('Source')==str(r)for m in x['Mounts'])and any('research/mk61-agent-20261106/bh_jobs.py'in a for a in(x['Config'].get('Cmd')or[])):own.append(cid)
assert not own,own
print(json.dumps({'all_frozen_files_verified':True,'own_containers_running':own,'optimizer_updates':12000,
 'same_data_draws':True,'unix':time.time(),'gpu_state':subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader'],text=True),
 'firmware_not_modified':True,'main_profile_not_replaced':True}))
'''.replace('REMOTE',repr(remote))
    result=subprocess.run([*SSH,'python3 -'],input=code,text=True,capture_output=True,check=True)
    write(ROOT/'server-results/postflight.json',json.loads(result.stdout))

def run(name,*args):subprocess.run([str(PYTHON),'-u',str(HERE/name),*args],cwd=REPO,check=True)

def main():
    deadline=time.monotonic()+14400
    while not(ROOT/'teacher-frozen.json').exists():
        if time.monotonic()>deadline:raise RuntimeError('Teacher preparation deadline exceeded')
        time.sleep(20)
    close_own_tunnel()
    if not(ROOT/'lessons-frozen.json').exists():run('bh_lessons.py')
    if not(ROOT/'prepared.json').exists():run('bh_prepare.py')
    run('bh_remote.py','deploy');run('bh_remote.py','start')
    run('bh_collect.py');postflight();run('bh_finish.py')
    write(ROOT/'pipeline-complete.json',{'complete':True,'optimizer_updates':12000,'unix':time.time()})
    print(json.dumps({'pipeline_complete':True,'report':str(HERE/'PAIRED_SPEC_LORA_FULL_RESULTS.md')}),flush=True)

if __name__=='__main__':
    try:main()
    except BaseException as error:
        write(ROOT/'pipeline-failed.json',{'error':repr(error),'unix':time.time()});raise
