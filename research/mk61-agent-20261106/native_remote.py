"""Operate only the new native-mixed-v1 directory inside the existing SSH sandbox."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import tarfile

from remote import SSH,STATE,BASE,HERE,REPO


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['deploy','data','teacher','activate','prepare','probe','start','finish','status','fetch','fetch-review'])
    p.add_argument('--scripts-only',action='store_true');a=p.parse_args()
    remote=json.loads(STATE.read_text())['directory'];local=BASE/'native-mixed-v1';local.mkdir(exist_ok=True)
    prefix='from pathlib import Path\nimport os,sys,json,subprocess,time\nr=Path('+repr(remote)+')\nd=r/".build/mk61-agent-20261106/native-mixed-v1"\nd.mkdir(exist_ok=True)\n'
    if a.action=='deploy':
        files=list(HERE.glob('*.py'))
        files += [p for p in local.glob('*')if p.is_file()and p.suffix in ['.json','.jsonl']]
        if not a.scripts_only:files += [p for p in(local/'initial').rglob('*')if p.is_file()]
        archive=local/'deploy.tar.gz'
        with tarfile.open(archive,'w:gz')as t:
            for file in dict.fromkeys(files):t.add(file,arcname=str(file.relative_to(REPO)),recursive=False)
        code='import sys,tarfile;tarfile.open(fileobj=sys.stdin.buffer,mode="r|gz").extractall('+repr(remote)+',filter="data")'
        with archive.open('rb')as stream:r=subprocess.run([*SSH,'python3 -c '+shlex.quote(code)],stdin=stream,capture_output=True)
        if r.returncode:raise RuntimeError('Deployment SSH exit '+str(r.returncode)+': '+r.stderr.decode()[-1500:])
        print(json.dumps({'files':len(files),'bytes':archive.stat().st_size}));return
    if a.action in ['data','teacher','activate','prepare','probe','start','finish']:
        script={'data':'native_data_controller.py','teacher':'native_teacher.py','activate':'native_activate_controller.py','prepare':'native_prepare_controller.py','probe':'native_probe_controller.py','start':'native_round.py','finish':'native_finish_controller.py'}[a.action]
        source=prefix+f'''p=d/{(a.action+'-launch.json')!r}
env=os.environ.copy()
if {a.action in ['probe','finish']!r}:env['MK61_AGENT_GPU']='1'
if p.exists():
 pid=json.loads(p.read_text())['pid'];proc=Path('/proc')/str(pid)
 if proc.exists()and {script.encode()!r}in(proc/'cmdline').read_bytes()and(proc/'cwd').resolve()==r:raise RuntimeError('Own job already running')
with(d/{(a.action+'-controller.log')!r}).open('a')as log:
 child=subprocess.Popen([sys.executable,'-u','research/mk61-agent-20261106/{script}'],cwd=r,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
p.write_text(json.dumps({{'pid':child.pid,'script':{script!r}}})+'\\n');print(p.read_text())
'''
    elif a.action=='status':
        source=prefix+'''for p in [d/'status.json',d/'language/status.json',d/'teacher/status.json']:
 if p.exists():print(str(p.relative_to(d)),p.read_text()[-1200:])
for p in sorted(d.glob('*/status.json')):
 if p.parent.name not in ['language','teacher']and'symmetric-warmup'not in p.parent.name:print(str(p.relative_to(d)),p.read_text()[-1200:])
for p in [d/'data-controller.log',d/'teacher-controller.log',d/'start-controller.log']:
 if p.name=='data-controller.log'and(d/'language/manifest.json').exists():continue
 if p.name=='teacher-controller.log'and(d/'teacher/manifest.json').exists():continue
 if p.exists():print(p.name,p.read_text()[-900:])
'''
    else:
        source=prefix+'review_only='+repr(a.action=='fetch-review')+'\n'+'''import tarfile
t=tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz')
for p in sorted(d.rglob('*')):
 if review_only and any(x in p.relative_to(d).parts for x in ['initial','initial-active','warm-common-2000','warmup-source','q4-language-symmetric-warmup','mixed-language-symmetric-warmup','best','last','best-short','before-context']):continue
 if p.is_file()and not any(x in p.parts for x in ['sources','pydeps','__pycache__'])and p.suffix not in ['.u16','.parquet','.part']:t.add(p,arcname=str(p.relative_to(d)),recursive=False)
t.close()
'''
        process=subprocess.Popen([*SSH,'python3 -c '+shlex.quote(source)],stdout=subprocess.PIPE)
        target=local/'server-results';target.mkdir(exist_ok=True)
        with tarfile.open(fileobj=process.stdout,mode='r|gz')as t:t.extractall(target,filter='data')
        if process.wait():raise RuntimeError('Fetch failed')
        print(target);return
    compile(source,'remote-control','exec')
    result=subprocess.run([*SSH,'python3 -'],input=source,text=True,capture_output=True)
    print(result.stdout)
    if result.returncode:raise RuntimeError(result.stderr[-2000:])


if __name__=='__main__':main()
