"""Deploy/operate only the isolated semantic-3m-v1 study over authorized SSH."""
import argparse
import json
import shlex
import subprocess
import tarfile

from remote import SSH,STATE,HERE,REPO,BASE


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['deploy','data','start','status','fetch']);a=p.parse_args()
    remote=json.loads(STATE.read_text())['directory'];local=BASE/'semantic-3m-v1';local.mkdir(exist_ok=True)
    if a.action=='deploy':
        files=list(HERE.glob('*.py'))+[x for x in local.iterdir()if x.name in ['audit.jsonl','audit-frozen.json','policy.json']]
        archive=local/'deploy.tar.gz'
        with tarfile.open(archive,'w:gz')as stream:
            for f in files:stream.add(f,arcname=str(f.relative_to(REPO)),recursive=False)
        source='import sys,tarfile;tarfile.open(fileobj=sys.stdin.buffer,mode="r|gz").extractall('+repr(remote)+',filter="data")'
        with archive.open('rb')as stream:subprocess.run([*SSH,'python3 -c '+shlex.quote(source)],stdin=stream,check=True)
        print(json.dumps({'deployed_files':len(files),'bytes':archive.stat().st_size}));return
    prefix='from pathlib import Path\nimport json,sys,subprocess,os\nr=Path('+repr(remote)+')\nd=r/".build/mk61-agent-20261106/semantic-3m-v1"\n'
    if a.action in ['data','start']:
        source=prefix+f'''marker=d/{(a.action+'-launch.json')!r}
if marker.exists():
 value=json.loads(marker.read_text());proc=Path('/proc')/str(value['pid'])
 if proc.exists()and b'semantic_round.py'in(proc/'cmdline').read_bytes()and(proc/'cwd').resolve()==r:raise RuntimeError('Own controller already active')
with(d/{(a.action+'-controller.log')!r}).open('a')as stream:
 child=subprocess.Popen([sys.executable,'-u','research/mk61-agent-20261106/semantic_round.py',{a.action!r}],cwd=r,stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
value={{'pid':child.pid,'script':'semantic_round.py','phase':{a.action!r}}};marker.write_text(json.dumps(value)+'\\n');print(json.dumps(value))
'''
    elif a.action=='status':
        source=prefix+'''for f in [d/'status.json',d/'teacher/status.json',*sorted(d.glob('*/status.json'))]:
 if f.exists():
  value=json.loads(f.read_text());print(str(f.relative_to(d)),json.dumps({k:v for k,v in value.items()if k not in ['counts','files','errors']}))
for f in [d/'data-controller.log',d/'start-controller.log',d/'direct.log',d/'auxiliary.log']:
 if f.exists():print(f.name,f.read_text()[-1200:])
'''
    else:
        source=prefix+'''import tarfile
t=tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz')
for f in sorted(d.rglob('*')):
 if not f.is_file()or '__pycache__'in f.parts:continue
 parts=f.relative_to(d).parts
 if parts[0]in ['teacher-runtime-cache']:continue
 if parts[0]!='export'and any(x in parts for x in ['best','last','optimizer']):continue
 t.add(f,arcname=str(f.relative_to(d)),recursive=False)
t.close()
'''
        child=subprocess.Popen([*SSH,'python3 -c '+shlex.quote(source)],stdout=subprocess.PIPE);target=local/'server-results';target.mkdir(exist_ok=True)
        with tarfile.open(fileobj=child.stdout,mode='r|gz')as stream:stream.extractall(target,filter='data')
        if child.wait():raise RuntimeError('Fetch failed')
        print(target);return
    compile(source,'semantic-control','exec');value=subprocess.run([*SSH,'python3 -'],input=source,text=True,capture_output=True)
    print(value.stdout)
    if value.returncode:raise RuntimeError(value.stderr[-2400:])


if __name__=='__main__':main()
