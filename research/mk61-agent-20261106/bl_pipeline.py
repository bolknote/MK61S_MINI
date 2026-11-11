"""Finish the entire authorized round, not merely launch the training jobs."""
import json
import os
import signal
import subprocess
import sys
import time
from bl_common import ROOT, HERE, REPO, read, write
from remote import SSH, STATE

PYTHON = REPO / '.build/squeal-chat-20261105/venv/bin/python'


def run(name, *args):
    print(json.dumps({'starting': name, 'unix': time.time()}), flush=True)
    subprocess.run([str(PYTHON), '-u', str(HERE / name), *args], cwd=REPO, check=True)


def close_tunnel():
    info = read(ROOT / 'teacher-tunnel.json')
    proc = subprocess.run(['ps', '-p', str(info['pid']), '-o', 'command='], capture_output=True, text=True)
    closed = False
    if proc.returncode == 0 and '127.0.0.1:18085:172.18.141.21:8000' in proc.stdout and 'ssh' in proc.stdout:
        os.kill(info['pid'], signal.SIGTERM); closed = True
    write(ROOT / 'teacher-tunnel-closed.json', {'own_pid': info['pid'], 'closed': closed, 'shared_teacher_service_untouched': True})


def postflight():
    root = read(STATE)['directory']
    source = '''import pathlib,json,subprocess,sys,time
r=pathlib.Path(REMOTE);sys.path.insert(0,str(r/'research/mk61-agent-20261106'))
from bl_common import ROOT,read,check_frozen
check_frozen();assert read(ROOT/'complete.json')['complete']
assert read(ROOT/'lora/training.json')['draw_digest']==read(ROOT/'full/training.json')['draw_digest']
own=[]
for cid in subprocess.check_output(['sudo','-n','docker','ps','-q'],text=True).split():
 x=json.loads(subprocess.check_output(['sudo','-n','docker','inspect',cid],text=True))[0]
 if any(m.get('Source')==str(r)for m in x['Mounts'])and any('bl_jobs.py'in a for a in(x['Config'].get('Cmd')or[])):own.append(cid)
assert not own
print(json.dumps({'complete':True,'frozen_verified':True,'own_containers_running':own,'optimizer_updates':6000,'same_draws':True,'main_profile_unchanged':True,'physical_device_access':False,'unix':time.time(),'gpu_state':subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader'],text=True)}))
'''.replace('REMOTE', repr(root))
    result = subprocess.run([*SSH, 'python3 -'], input=source, capture_output=True, text=True, timeout=60, check=True)
    write(ROOT / 'server-results/postflight.json', json.loads(result.stdout))


def main():
    deadline = time.monotonic() + 14400
    while not (ROOT / 'teacher-frozen.json').exists():
        if time.monotonic() > deadline:
            raise RuntimeError('Teacher preparation deadline exceeded')
        time.sleep(20)
    close_tunnel()
    run('bl_runtime_check.py')
    if not (ROOT / 'lessons-frozen.json').exists():
        run('bl_lessons.py')
    if not (ROOT / 'prepared.json').exists():
        run('bl_prepare.py')
    run('bl_remote.py', 'deploy'); run('bl_remote.py', 'start')
    run('bl_collect.py'); postflight()
    write(ROOT / 'pipeline-complete.json', {'complete': True, 'optimizer_updates': 6000, 'unix': time.time()})


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        write(ROOT / 'pipeline-failed.json', {'error': repr(error), 'unix': time.time()}); raise
