"""Wait for all four development/closed routes and native verification."""
import json
import os
import signal
import subprocess
import time
from bw_common import ROOT,HERE,REPO,read,write
from remote import SSH,STATE

PYTHON=REPO/'.build/squeal-chat-20261105/venv/bin/python'


def run(name,*args):
    print({'starting':name,'unix':time.time()},flush=True)
    subprocess.run([str(PYTHON),'-u',str(HERE/name),*args],cwd=REPO,check=True)


def remote(src):
    p=subprocess.run([*SSH,'python3 -'],input=src,text=True,capture_output=True,timeout=40)
    if p.returncode:raise RuntimeError('SSH read failed: '+p.stderr[-500:])
    return p.stdout


def main():
    deadline=time.monotonic()+43200
    while not(ROOT/'teacher-frozen.json').exists():
        if'Traceback (most recent call last)'in(ROOT/'teacher.log').read_text():raise RuntimeError('Teacher preparation failed')
        if time.monotonic()>deadline:raise RuntimeError('Teacher deadline')
        time.sleep(10)
    if not(ROOT/'teacher-tunnel-closed.json').exists():
        tunnel=read(ROOT/'teacher-tunnel.json');p=subprocess.run(['ps','-p',str(tunnel['pid']),'-o','command='],capture_output=True,text=True)
        closed=False
        if p.returncode==0 and'127.0.0.1:18089:172.18.141.21:8000'in p.stdout and'ssh'in p.stdout:
            os.kill(tunnel['pid'],signal.SIGTERM);closed=True
        write(ROOT/'teacher-tunnel-closed.json',{'own_pid':tunnel['pid'],'closed':closed,'shared_service_unchanged':True})
    if not(ROOT/'prepared.json').exists():run('bw_prepare.py')
    prefix='from pathlib import Path\nimport json\nr=Path('+repr(read(STATE)['directory'])+')/".build/mk61-agent-20261106/spec-phase-routing-v1"\n'
    if remote(prefix+"print((r/'launch.json').exists())").strip()!='True':run('bw_remote.py','deploy');run('bw_remote.py','start')
    query=prefix+'''def read(n):return json.loads((r/n).read_text())if(r/n).exists()else None
out={'status':read('status.json'),'selection':read('preselected.json'),'complete':read('controller-complete.json'),'failure':read('controller-failure.json'),'development':{},'closed':{}}
for split in ['development','closed']:
 for p in sorted(r.glob(split+'-*.json')):
  v=json.loads(p.read_text());out[split][p.stem]={k:{'summary':v[k]['summary'],**({'replan':v[k]['replan']}if'replan'in v[k]else{})}for k in ['primary','own','wrong']}
print(json.dumps(out))
'''
    last=None
    while True:
        try:v=json.loads(remote(query))
        except(RuntimeError,subprocess.TimeoutExpired,json.JSONDecodeError)as e:
            print({'snapshot_retry':type(e).__name__},flush=True);time.sleep(10);continue
        write(ROOT/'live-summary.json',v);key=json.dumps(v['status'],sort_keys=True)
        if key!=last:
            print({'status':v['status'],'development_complete':list(v['development']),'closed_complete':list(v['closed'])},flush=True);last=key
            s=read(HERE/'work-state.json');entry=s.get('latest_phase_routing',{});entry.update(phase=(v['status']or{}).get('phase','remote_starting'))
            s.update(phase='spec_phase_routing_'+entry['phase'],latest_phase_routing=entry);write(HERE/'work-state.json',s)
        if v['failure']:raise RuntimeError(v['failure'])
        if v['complete']:break
        if time.monotonic()>deadline:raise RuntimeError('Routing evaluation deadline')
        time.sleep(20)
    run('bw_remote.py','postflight');run('bw_remote.py','fetch');run('bw_native.py');run('bw_finish.py')
    write(ROOT/'pipeline-complete.json',{'complete':True,'optimizer_updates':0,'unix':time.time()})
    print('ALL_PHASE_ROUTING_WORK_COMPLETE',flush=True)


if __name__=='__main__':
    try:main()
    except BaseException as e:write(ROOT/'pipeline-failure.json',{'error':repr(e),'unix':time.time()});raise
