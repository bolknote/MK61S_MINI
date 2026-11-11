"""Only the authorized repository and temporary AR jobs are controlled here."""
import argparse
import json
import shlex
import subprocess
import tarfile
from ar_common import ROOT, HERE, REPO, read
from remote import SSH, STATE


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['deploy','start-small','start-teacher','status','fetch']);a=p.parse_args()
    remote=read(STATE)['directory']
    if a.action=='deploy':
        frozen=read(ROOT/'frozen.json');paths=[HERE/n for n in frozen['sources']]
        paths += [ROOT/n for n in ['frozen.json','goals.json','policy.json','checks.json']]
        archive=ROOT/'deploy.tar.gz'
        with tarfile.open(archive,'w:gz')as t:
            for path in paths:t.add(path,arcname=str(path.relative_to(REPO)),recursive=False)
        source='import tarfile,sys;tarfile.open(fileobj=sys.stdin.buffer,mode="r|gz").extractall('+repr(remote)+',filter="data")'
        with archive.open('rb')as stream:subprocess.run([*SSH,'python3 -c '+shlex.quote(source)],stdin=stream,check=True)
        print(json.dumps({'files':len(paths),'bytes':archive.stat().st_size}));return
    prefix='from pathlib import Path\nimport json,sys,subprocess,os\nr=Path('+repr(remote)+')\nd=r/".build/mk61-agent-20261106/spec-diagnostic-v1"\n'
    if a.action.startswith('start-'):
        actor=a.action.split('-')[1]
        source=prefix+'''actor='''+repr(actor)+'''
out=d/actor;out.mkdir(exist_ok=True)
assert not(out/'results.json').exists(),'already complete'
sys.path.insert(0,str(r/'research/mk61-agent-20261106'))
from ar_common import check_frozen
check_frozen()
marker=out/'launch.json'
if marker.exists():
 old=json.loads(marker.read_text());p=Path('/proc')/str(old['pid'])
 if p.exists()and b'ar_run.py'in(p/'cmdline').read_bytes():raise RuntimeError('own worker already running')
if actor=='teacher':
 cmd=['python3','-u','research/mk61-agent-20261106/ar_run.py','teacher']
else:
 from run_experiment import IMAGE
 cmd=['sudo','-n','docker','run','--rm','--name','mk61-spec-small-ar','--gpus','device=0','--cpus=4','--memory=10g','--shm-size=512m','--user',f'{os.getuid()}:{os.getgid()}',
      '--env','HF_HUB_OFFLINE=1','--env','TRANSFORMERS_OFFLINE=1','--env','HF_HOME=/tmp/hf','--env','TOKENIZERS_PARALLELISM=false',
      '--volume',str(r)+':/work','--workdir','/work','--entrypoint','python3',IMAGE,'-u','research/mk61-agent-20261106/ar_run.py','small']
with(out/'worker.log').open('a')as log:
 child=subprocess.Popen(cmd,cwd=r,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
item={'pid':child.pid,'command':cmd};marker.write_text(json.dumps(item));print(json.dumps(item))
'''
    elif a.action=='status':
        source=prefix+'''for label in ['small','teacher']:
 out=d/label
 for n in ['status.json','worker.log']:
  p=out/n
  if p.exists():print(label,n,p.read_text()[-1500:])
print(subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader']).decode())
try:
 import urllib.request
 with urllib.request.urlopen('http://127.0.0.1:18080/health',timeout=3)as resp:print('teacher_health',resp.status)
except Exception as e:print('teacher_health',str(e))
log=subprocess.run(['sudo','-n','docker','logs','--tail','4','mk61-spec-teacher-ar'],capture_output=True,text=True)
print((log.stdout+log.stderr)[-1800:])
'''
    else:
        source=prefix+'''import tarfile
t=tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz')
for p in sorted(d.rglob('*')):
 if not p.is_file()or'__pycache__'in p.parts or p.suffix=='.gz':continue
 t.add(p,arcname=str(p.relative_to(d)),recursive=False)
t.close()
'''
        target=ROOT/'server-results';target.mkdir(exist_ok=True)
        child=subprocess.Popen([*SSH,'python3 -c '+shlex.quote(source)],stdout=subprocess.PIPE)
        with tarfile.open(fileobj=child.stdout,mode='r|gz')as t:t.extractall(target,filter='data')
        assert child.wait()==0;print(target);return
    result=subprocess.run([*SSH,'python3 -'],input=source,text=True,capture_output=True)
    print(result.stdout)
    if result.returncode:raise RuntimeError(result.stderr[-4000:])


if __name__=='__main__':main()
