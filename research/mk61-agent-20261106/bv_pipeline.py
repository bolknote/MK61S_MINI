"""Wait through repair, sealed audit and native checks, with bounded SSH reads."""
import json
import os
import signal
import subprocess
import time
from bv_common import ROOT,HERE,REPO,read,write
from remote import SSH,STATE

PYTHON=REPO/'.build/squeal-chat-20261105/venv/bin/python'


def run(name,*args):
    print({'starting':name,'unix':time.time()},flush=True);subprocess.run([str(PYTHON),'-u',str(HERE/name),*args],cwd=REPO,check=True)


def remote(source):
    p=subprocess.run([*SSH,'python3 -'],input=source,text=True,capture_output=True,timeout=40)
    if p.returncode:raise RuntimeError('SSH read failed: '+p.stderr[-500:])
    return p.stdout


def main():
    deadline=time.monotonic()+43200
    while not(ROOT/'teacher-frozen.json').exists():
        if'Traceback (most recent call last)'in(ROOT/'teacher.log').read_text():raise RuntimeError('Teacher failed')
        if time.monotonic()>deadline:raise RuntimeError('Teacher preparation deadline')
        time.sleep(15)
    info=read(ROOT/'teacher-tunnel.json');p=subprocess.run(['ps','-p',str(info['pid']),'-o','command='],capture_output=True,text=True);closed=False
    if p.returncode==0 and'127.0.0.1:18088:172.18.141.21:8000'in p.stdout and'ssh'in p.stdout:os.kill(info['pid'],signal.SIGTERM);closed=True
    write(ROOT/'teacher-tunnel-closed.json',{'own_pid':info['pid'],'closed':closed,'shared_service_unchanged':True})
    if not(ROOT/'prepared.json').exists():run('bv_prepare.py')
    location=read(STATE)['directory'];prefix='from pathlib import Path\nimport json\nr=Path('+repr(location)+')/".build/mk61-agent-20261106/spec-retention-recovery-v1"\n'
    launched=remote(prefix+"print((r/'launch.json').exists())").strip()=='True'
    if not launched:run('bv_remote.py','deploy');run('bv_remote.py','start')
    query=prefix+'''def read(n):return json.loads((r/n).read_text())if(r/n).exists()else None
out={'status':read('status.json'),'best':read('best.json'),'selection':read('preselected.json'),'training':read('training.json'),'complete':read('controller-complete.json'),'failure':read('controller-failure.json'),'fit':{},'development':{},'closed':{}}
for p in sorted(r.glob('fit-*.json')):
 v=json.loads(p.read_text());out['fit'][p.stem]={k:v[k]['summary']for k in ['hard','retention','composition']}
for p in [r/'parent-development.json',*sorted(r.glob('development-*.json'))]:
 if p.exists():
  v=json.loads(p.read_text());out['development'][p.stem]={k:v[k]['summary']for k in ['primary','own','wrong']}
for p in sorted(r.glob('closed-*.json')):
 v=json.loads(p.read_text());out['closed'][p.stem]={k:v[k]['summary']for k in ['primary','own','wrong']}
print(json.dumps(out))
'''
    last=None
    while True:
        try:v=json.loads(remote(query))
        except(RuntimeError,subprocess.TimeoutExpired,json.JSONDecodeError)as e:
            print({'remote_snapshot_retry':type(e).__name__},flush=True);time.sleep(15);continue
        write(ROOT/'live-summary.json',v);key=json.dumps(v['status'],sort_keys=True)
        if key!=last:
            print({'status':v['status'],'fit_complete':list(v['fit']),'development_complete':list(v['development']),
                   'closed_complete':list(v['closed']),'best_step':v['best']['step']if v['best']else None},flush=True);last=key
            s=read(HERE/'work-state.json');entry=s.get('latest_retention_spec_training',{});entry['phase']=(v['status']or{}).get('phase','remote_starting')
            if v['training']:entry['observed_completed_steps']=v['training']['optimizer_updates']
            elif(v['status']or{}).get('phase')=='training':entry['observed_completed_steps']=v['status']['step']
            s.update(phase='spec_retention_recovery_'+entry['phase'],latest_retention_spec_training=entry);write(HERE/'work-state.json',s)
        if v['failure']:raise RuntimeError(v['failure'])
        if v['complete']:break
        if time.monotonic()>deadline:raise RuntimeError('Recovery course deadline')
        time.sleep(20)
    run('bv_remote.py','postflight');run('bv_remote.py','fetch');run('bv_native.py');run('bv_finish.py')
    write(ROOT/'pipeline-complete.json',{'complete':True,'optimizer_updates':read(ROOT/'server-results/training.json')['optimizer_updates'],'unix':time.time()});print('ALL_RETENTION_RECOVERY_WORK_COMPLETE',flush=True)


if __name__=='__main__':
    try:main()
    except BaseException as e:write(ROOT/'pipeline-failure.json',{'error':repr(e),'unix':time.time()});raise
