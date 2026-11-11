"""Operate this frozen comparison only, using the user's existing SSH route."""
import argparse
import json
import shlex
import subprocess
import tarfile
from br_common import ROOT,HERE,REPO,read
from remote import SSH,STATE


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['probe','deploy','start','status','fetch','postflight']);a=p.parse_args()
    remote=read(STATE)['directory']
    prefix='from pathlib import Path\nimport json,sys,os,time,subprocess\nr=Path('+repr(remote)+')\nd=r/".build/mk61-agent-20261106/capacity-clean-cycles-v1"\n'
    if a.action=='deploy':
        f=read(ROOT/'frozen.json');paths=[HERE/n for n in f['sources']]+[ROOT/n for n in f['files']]+[ROOT/'frozen.json',ROOT/'prepared.json']
        archive=ROOT/'deploy.tar.gz'
        with tarfile.open(archive,'w:gz')as stream:
            for path in paths:stream.add(path,arcname=str(path.relative_to(REPO)),recursive=False)
        command='import tarfile,sys;tarfile.open(fileobj=sys.stdin.buffer,mode="r|gz").extractall('+repr(remote)+',filter="data")'
        with archive.open('rb')as stream:subprocess.run([*SSH,'python3 -c '+shlex.quote(command)],stdin=stream,check=True)
        print(json.dumps({'deployed':len(paths),'bytes':archive.stat().st_size}));return
    if a.action=='probe':
        source=prefix+'''print(subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader'],text=True))
print(subprocess.check_output(['sudo','-n','docker','ps','--format','{{.ID}} {{.Command}}'],text=True))
'''
    elif a.action=='start':
        source=prefix+'''sys.path.insert(0,str(r/'research/mk61-agent-20261106'))
from br_common import check_frozen
check_frozen();assert(d/'prepared.json').exists();assert not(d/'launch.json').exists()
with(d/'controller.log').open('w')as log:
 child=subprocess.Popen(['python3','-u','research/mk61-agent-20261106/br_round.py'],cwd=r,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
v={'pid':child.pid,'unix':time.time()};(d/'launch.json').write_text(json.dumps(v));print(json.dumps(v))
'''
    elif a.action=='status':
        source=prefix+'''for n in ['status.json','small/status.json','large/status.json','small/best.json','large/best.json','preselected.json']:
 p=d/n
 if p.exists():print(n,p.read_text()[-2000:])
for n in ['controller.log','small-train.log','large-train.log','small-audit.log','large-audit.log']:
 p=d/n
 if p.exists():print(n,p.read_text()[-1300:])
'''
    elif a.action=='postflight':
        source=prefix+'''assert json.loads((d/'complete.json').read_text())['complete']
gpu=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader'],text=True)
jobs=subprocess.check_output(['sudo','-n','docker','ps','--format','{{.ID}} {{.Command}}'],text=True)
owned=[s for s in jobs.splitlines()if'br_jobs.py'in s]
receipt={'all_workers_joined':True,'live_remote_recheck_completed':True,'own_training_containers':owned,'GPU':gpu,'unix':time.time()}
assert not owned; (d/'postflight.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
'''
    else:
        source=prefix+'''import tarfile
t=tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz')
for p in sorted(d.rglob('*')):
 if not p.is_file()or'__pycache__'in p.parts or p.suffix in ['.gz','.pt']or p.name=='controller.lock':continue
 if p.suffix=='.safetensors'and'hf'not in p.parts and p.name not in ['best.safetensors','last.safetensors']:continue
 t.add(p,arcname=str(p.relative_to(d)),recursive=False)
t.close()
'''
        target=ROOT/'server-results';target.mkdir(exist_ok=True)
        child=subprocess.Popen([*SSH,'python3 -c '+shlex.quote(source)],stdout=subprocess.PIPE)
        with tarfile.open(fileobj=child.stdout,mode='r|gz')as stream:stream.extractall(target,filter='data')
        assert child.wait()==0;print(target);return
    r=subprocess.run([*SSH,'python3 -'],input=source,text=True,capture_output=True,timeout=90)
    print(r.stdout)
    if r.returncode:raise RuntimeError(r.stderr[-4000:])


if __name__=='__main__':main()
