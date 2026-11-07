"""Operate composition-v1 only inside the existing user-authorized SSH directory."""
import argparse
import json
import shlex
import subprocess
import tarfile

from remote import SSH,STATE,HERE,REPO,BASE


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['deploy','teacher','start','extend','status','fetch']);a=p.parse_args()
    remote=json.loads(STATE.read_text())['directory'];local=BASE/'composition-v1';local.mkdir(exist_ok=True)
    prefix='from pathlib import Path\nimport os,sys,json,subprocess\nr=Path('+repr(remote)+')\nd=r/".build/mk61-agent-20261106/composition-v1"\nd.mkdir(exist_ok=True)\n'
    if a.action=='deploy':
        files=list(HERE.glob('*.py'))+[p for p in local.glob('*')if p.is_file()and p.suffix in ['.json','.jsonl']]
        path=local/'deploy.tar.gz'
        with tarfile.open(path,'w:gz')as archive:
            for f in files:archive.add(f,arcname=str(f.relative_to(REPO)),recursive=False)
        code='import sys,tarfile;tarfile.open(fileobj=sys.stdin.buffer,mode="r|gz").extractall('+repr(remote)+',filter="data")'
        with path.open('rb')as stream:result=subprocess.run([*SSH,'python3 -c '+shlex.quote(code)],stdin=stream,capture_output=True)
        if result.returncode:raise RuntimeError(result.stderr.decode()[-1800:])
        print(json.dumps({'files':len(files),'bytes':path.stat().st_size}));return
    if a.action in ['teacher','start','extend']:
        script={'teacher':'compose_teacher.py','start':'compose_round.py','extend':'compose_extension.py'}[a.action]
        source=prefix+f'''marker=d/{(a.action+'-launch.json')!r}
if marker.exists():
 item=json.loads(marker.read_text());proc=Path('/proc')/str(item['pid'])
 if proc.exists()and {script.encode()!r}in(proc/'cmdline').read_bytes()and(proc/'cwd').resolve()==r:raise RuntimeError('Own controller already running')
with(d/{(a.action+'-controller.log')!r}).open('a')as log:
 child=subprocess.Popen([sys.executable,'-u','research/mk61-agent-20261106/{script}'],cwd=r,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
marker.write_text(json.dumps({{'pid':child.pid,'script':{script!r}}})+'\\n');print(marker.read_text())
'''
    elif a.action=='status':
        source=prefix+'''for p in [d/'status.json',d/'teacher/status.json',*sorted(d.glob('*/status.json'))]:
 if p.exists():print(str(p.relative_to(d)),p.read_text()[-1600:])
for p in [d/'teacher-controller.log',d/'start-controller.log']:
 if p.exists():print(p.name,p.read_text()[-1200:])
'''
    else:
        source=prefix+'''import tarfile
t=tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz')
for p in sorted(d.rglob('*')):
 if not p.is_file()or '__pycache__'in p.parts:continue
 if any(x in p.relative_to(d).parts for x in ['best','last','optimizer']):continue
 t.add(p,arcname=str(p.relative_to(d)),recursive=False)
t.close()
'''
        process=subprocess.Popen([*SSH,'python3 -c '+shlex.quote(source)],stdout=subprocess.PIPE)
        target=local/'server-results';target.mkdir(exist_ok=True)
        with tarfile.open(fileobj=process.stdout,mode='r|gz')as t:t.extractall(target,filter='data')
        if process.wait():raise RuntimeError('Fetch failed')
        print(target);return
    compile(source,'compose-control','exec')
    result=subprocess.run([*SSH,'python3 -'],input=source,text=True,capture_output=True)
    print(result.stdout)
    if result.returncode:raise RuntimeError(result.stderr[-2000:])


if __name__=='__main__':main()
