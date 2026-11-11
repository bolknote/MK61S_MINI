"""Run only read-only model diagnosis in its own result folder on the two B200s."""
import argparse
import json
import shlex
import subprocess
import tarfile
from bn_common import ROOT,HERE,REPO,read
from remote import SSH,STATE


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['deploy','start','status','fetch']);a=p.parse_args();remote=read(STATE)['directory']
    prefix='from pathlib import Path\nimport sys,json,os,subprocess,time\nr=Path('+repr(remote)+')\nd=r/".build/mk61-agent-20261106/weight-diagnosis-v1"\n'
    if a.action=='deploy':
        f=read(ROOT/'frozen.json');paths=[HERE/n for n in f['sources']]+[ROOT/n for n in f['files']]+[ROOT/'frozen.json']
        archive=ROOT/'deploy.tar.gz'
        with tarfile.open(archive,'w:gz')as t:
            for path in paths:t.add(path,arcname=str(path.relative_to(REPO)),recursive=False)
        code='import sys,tarfile;tarfile.open(fileobj=sys.stdin.buffer,mode="r|gz").extractall('+repr(remote)+',filter="data")'
        with archive.open('rb')as stream:subprocess.run([*SSH,'python3 -c '+shlex.quote(code)],stdin=stream,check=True)
        print(json.dumps({'deployed_files':len(paths),'bytes':archive.stat().st_size}));return
    if a.action=='start':
        source=prefix+'''sys.path.insert(0,str(r/'research/mk61-agent-20261106'))
from bn_common import check
check();assert not(d/'launch.json').exists()
jobs={}
for gpu,name in [(0,'cross'),(1,'actions')]:
 body="from run_experiment import run,SCRIPT;run('weight-diagnosis-v1/"+name+".log',SCRIPT+'bn_"+name+".py',timeout=14400)"
 code="import sys;sys.path.insert(0,'research/mk61-agent-20261106');"+body
 with(d/(name+'-controller.log')).open('w')as log:
  child=subprocess.Popen(['python3','-u','-c',code],cwd=r,env={**os.environ,'MK61_AGENT_GPU':str(gpu)},stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 jobs[name]={'pid':child.pid,'gpu':gpu}
(d/'launch.json').write_text(json.dumps(jobs));print(json.dumps(jobs))
'''
    elif a.action=='status':
        source=prefix+'''for n in ['cross-complete.json','actions-complete.json','cross-controller.log','actions-controller.log','cross.log','actions.log']:
 p=d/n
 if p.exists():print(n,p.read_text()[-2400:])
'''
    else:
        source=prefix+'''import tarfile
t=tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz')
for p in sorted(d.rglob('*')):
 if p.is_file()and p.suffix in ['.json','.log']:t.add(p,arcname=str(p.relative_to(d)),recursive=False)
t.close()
'''
        target=ROOT/'server-results';target.mkdir(exist_ok=True);child=subprocess.Popen([*SSH,'python3 -c '+shlex.quote(source)],stdout=subprocess.PIPE)
        with tarfile.open(fileobj=child.stdout,mode='r|gz')as stream:stream.extractall(target,filter='data')
        assert child.wait()==0;print(target);return
    result=subprocess.run([*SSH,'python3 -'],input=source,text=True,capture_output=True,timeout=90)
    print(result.stdout)
    if result.returncode:raise RuntimeError(result.stderr[-3000:])


if __name__=='__main__':main()
