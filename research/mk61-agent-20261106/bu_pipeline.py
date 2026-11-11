"""Stay with the authorized course through teacher, SGD, sealed audit, and export."""
import json
import os
import signal
import subprocess
import time
from pathlib import Path
from bu_common import ROOT,HERE,REPO,read,write
from remote import remote_python,STATE

PYTHON=REPO/'.build/squeal-chat-20261105/venv/bin/python'


def run(name,*args):
    print({'starting':name,'unix':time.time()},flush=True)
    subprocess.run([str(PYTHON),'-u',str(HERE/name),*args],cwd=REPO,check=True)


def close_tunnel():
    info=read(ROOT/'teacher-tunnel.json');probe=subprocess.run(['ps','-p',str(info['pid']),'-o','command='],capture_output=True,text=True)
    closed=False
    if probe.returncode==0 and'127.0.0.1:18087:172.18.141.21:8000'in probe.stdout and'ssh'in probe.stdout:
        os.kill(info['pid'],signal.SIGTERM);closed=True
    write(ROOT/'teacher-tunnel-closed.json',{'own_pid':info['pid'],'closed':closed,'shared_service_unchanged':True,'unix':time.time()})


def main():
    deadline=time.monotonic()+43200
    while not(ROOT/'teacher-frozen.json').exists():
        log=(ROOT/'teacher.log').read_text()if(ROOT/'teacher.log').exists()else''
        if'Traceback (most recent call last)'in log:raise RuntimeError('Teacher failed; inspect teacher.log')
        if time.monotonic()>deadline:raise RuntimeError('Teacher deadline exceeded')
        time.sleep(15)
    close_tunnel()
    if not(ROOT/'prepared.json').exists():run('bu_prepare.py')
    remote=read(STATE)['directory'];prefix='from pathlib import Path\nimport json\nr=Path('+repr(remote)+')/".build/mk61-agent-20261106/spec-phase-adapter-v1"\n'
    launched=remote_python(prefix+"print((r/'launch.json').exists())").strip()=='True'
    if not launched:run('bu_remote.py','deploy');run('bu_remote.py','start')
    query=prefix+'''def read(n):return json.loads((r/n).read_text())if(r/n).exists()else None
out={'status':read('status.json'),'best':read('best.json'),'selection':read('preselected.json'),'training':read('training.json'),'complete':read('controller-complete.json'),'failure':read('controller-failure.json'),'development':{},'closed':{}}
for p in [r/'parent-development.json',*sorted(r.glob('development-*.json'))]:
 if p.exists():
  v=json.loads(p.read_text());out['development'][p.stem]={k:v[k]['summary']for k in ['primary','own','wrong','retention']if k in v}
for p in sorted(r.glob('closed-*.json')):
 v=json.loads(p.read_text());out['closed'][p.stem]={k:v[k]['summary']for k in ['primary','own','wrong']}
print(json.dumps(out))
'''
    last=None
    while True:
        try:v=json.loads(remote_python(query))
        except(subprocess.CalledProcessError,json.JSONDecodeError)as e:
            print({'SSH_or_snapshot_retry':type(e).__name__},flush=True);time.sleep(15);continue
        write(ROOT/'live-summary.json',v);key=json.dumps(v['status'],sort_keys=True)
        if key!=last:
            print({'status':v['status'],'development_complete':list(v['development']),'closed_complete':list(v['closed']),
                   'best_step':v['best']['step']if v['best']else None},flush=True);last=key
            state=read(HERE/'work-state.json');entry=state.get('latest_phase_spec_training',{})
            entry.update(phase=(v['status']or{}).get('phase','remote_starting'),actor_weights_frozen=True)
            if v['training']:entry['observed_completed_steps']=v['training']['optimizer_updates']
            elif(v['status']or{}).get('phase')=='training':entry['observed_completed_steps']=v['status']['step']
            state.update(phase='spec_phase_adapter_'+entry['phase'],latest_phase_spec_training=entry);write(HERE/'work-state.json',state)
        if v['failure']:raise RuntimeError(v['failure'])
        if v['complete']:break
        if time.monotonic()>deadline:raise RuntimeError('Course deadline exceeded')
        time.sleep(20)
    run('bu_remote.py','postflight');run('bu_remote.py','fetch')
    run('bu_native.py');run('bu_finish.py')
    write(ROOT/'pipeline-complete.json',{'complete':True,'optimizer_updates':1500,'unix':time.time()});print('ALL_PHASE_SPEC_WORK_COMPLETE',flush=True)


if __name__=='__main__':
    try:main()
    except BaseException as e:write(ROOT/'pipeline-failure.json',{'error':repr(e),'unix':time.time()});raise
