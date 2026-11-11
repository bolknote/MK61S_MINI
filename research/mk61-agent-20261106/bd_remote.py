"""Deploy and follow only the isolated, zero-update factorial diagnostic."""
import argparse
import json
import shlex
import subprocess
import tarfile
from bd_common import ROOT,HERE,REPO,read
from remote import SSH,STATE


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['probe','deploy','start','status','fetch']);a=p.parse_args()
    remote=read(STATE)['directory'];prefix='from pathlib import Path\nimport json,sys,subprocess,time,os\nr=Path('+repr(remote)+')\nd=r/".build/mk61-agent-20261106/spec-factorial-diagnostic-v1"\n'
    if a.action=='probe':
        source=prefix+'''print(subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader'],text=True))
print(subprocess.check_output(['sudo','-n','docker','ps','--format','{{.ID}} {{.Command}}'],text=True))
'''
    elif a.action=='deploy':
        f=read(ROOT/'frozen.json');paths=[HERE/n for n in f['sources']]+[ROOT/n for n in f['files']]+[ROOT/'frozen.json',ROOT/'prepared.json']
        archive=ROOT/'deploy.tar.gz'
        with tarfile.open(archive,'w:gz')as stream:
            for path in paths:stream.add(path,arcname=str(path.relative_to(REPO)),recursive=False)
        command='import tarfile,sys;tarfile.open(fileobj=sys.stdin.buffer,mode="r|gz").extractall('+repr(remote)+',filter="data")'
        with archive.open('rb')as stream:subprocess.run([*SSH,'python3 -c '+shlex.quote(command)],stdin=stream,check=True)
        print(json.dumps({'deployed':len(paths),'bytes':archive.stat().st_size}));return
    elif a.action=='start':
        source=prefix+'''sys.path.insert(0,str(r/'research/mk61-agent-20261106'))
from bd_common import check_frozen
check_frozen();assert not(d/'complete.json').exists();assert not(d/'launch.json').exists()
script="import sys;sys.path.insert(0,'research/mk61-agent-20261106');from run_experiment import run;run('spec-factorial-diagnostic-v1/worker.log','research/mk61-agent-20261106/bd_run.py',timeout=10800)"
with(d/'controller.log').open('w')as log:
 p=subprocess.Popen(['python3','-u','-c',script],cwd=r,env={**os.environ,'MK61_AGENT_GPU':'0'},stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
value={'pid':p.pid,'optimizer_updates':0,'unix':time.time()};(d/'launch.json').write_text(json.dumps(value));print(json.dumps(value))
'''
    elif a.action=='status':
        source=prefix+'''for n in ['status.json','complete.json']:
 p=d/n
 if p.exists():print(n,p.read_text()[-7000:])
for n in ['controller.log','worker.log']:
 p=d/n
 if p.exists():print(n,p.read_text()[-600:])
'''
    else:
        source=prefix+'''import tarfile
t=tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz')
for p in sorted(d.rglob('*')):
 if not p.is_file()or '__pycache__'in p.parts or p.suffix in ['.gz','.safetensors']or'export'in p.relative_to(d).parts:continue
 t.add(p,arcname=str(p.relative_to(d)),recursive=False)
t.close()
'''
        target=ROOT/'server-results';target.mkdir(exist_ok=True)
        child=subprocess.Popen([*SSH,'python3 -c '+shlex.quote(source)],stdout=subprocess.PIPE)
        with tarfile.open(fileobj=child.stdout,mode='r|gz')as stream:stream.extractall(target,filter='data')
        assert child.wait()==0;print(target);return
    result=subprocess.run([*SSH,'python3 -'],input=source,text=True,capture_output=True,timeout=90)
    print(result.stdout)
    if result.returncode:raise RuntimeError(result.stderr[-3000:])


if __name__=='__main__':main()
