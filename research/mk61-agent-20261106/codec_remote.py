"""Deploy/inspect only codec-qat-v1 in the existing authorized server directory."""
import argparse
import json
import shlex
import subprocess
import tarfile

from remote import SSH,STATE,HERE,REPO,BASE


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['deploy','prepare','start','status','fetch','fetch-initial']);p.add_argument('--scripts-only',action='store_true');a=p.parse_args()
    remote=json.loads(STATE.read_text())['directory'];local=BASE/'codec-qat-v1';local.mkdir(exist_ok=True)
    prefix='from pathlib import Path\nimport json,sys,subprocess,os\nr=Path('+repr(remote)+')\nd=r/".build/mk61-agent-20261106/codec-qat-v1"\nd.mkdir(exist_ok=True)\n'
    if a.action=='deploy':
        files=list(HERE.glob('*.py'))
        if not a.scripts_only:
            files += [x for x in local.iterdir()if x.is_file()and x.suffix in ['.json','.jsonl']]
            for folder in ['tokenizer','freeze-history']:files += [x for x in(local/folder).rglob('*')if x.is_file()]
        archive=local/'deploy.tar.gz'
        with tarfile.open(archive,'w:gz')as t:
            for f in files:t.add(f,arcname=str(f.relative_to(REPO)),recursive=False)
        code='import sys,tarfile;tarfile.open(fileobj=sys.stdin.buffer,mode="r|gz").extractall('+repr(remote)+',filter="data")'
        with archive.open('rb')as stream:result=subprocess.run([*SSH,'python3 -c '+shlex.quote(code)],stdin=stream,capture_output=True)
        if result.returncode:raise RuntimeError(result.stderr.decode()[-1500:])
        print(json.dumps({'files':len(files),'bytes':archive.stat().st_size}));return
    if a.action in ['prepare','start']:
        source=prefix+f'''marker=d/{(a.action+'-launch.json')!r}
if marker.exists():
 item=json.loads(marker.read_text());proc=Path('/proc')/str(item['pid'])
 if proc.exists()and b'codec_round.py'in(proc/'cmdline').read_bytes()and(proc/'cwd').resolve()==r:raise RuntimeError('Own coordinator already running')
command=[sys.executable,'-u','research/mk61-agent-20261106/codec_round.py']+{['prepare']if a.action=='prepare'else[]!r}
with(d/{(a.action+'-controller.log')!r}).open('a')as log:
 child=subprocess.Popen(command,cwd=r,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
item={{'pid':child.pid,'script':'codec_round.py'}};marker.write_text(json.dumps(item)+'\\n');print(json.dumps(item))
'''
    elif a.action=='status':
        source=prefix+'''for f in [d/'status.json',*sorted(d.glob('*/status.json'))]:
 if f.exists():
  x=json.loads(f.read_text());print(str(f.relative_to(d)),json.dumps({k:v for k,v in x.items()if k!='counts'}))
for f in [d/'prepare-controller.log',d/'start-controller.log']:
 if f.exists():print(f.name,f.read_text()[-1800:])
'''
    else:
        source=prefix+('base=d/"initial"\n'if a.action=='fetch-initial'else'base=d\n')+'''import tarfile
t=tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz')
for f in sorted(base.rglob('*')):
 if not f.is_file()or '__pycache__'in f.parts:continue
 parts=f.relative_to(base).parts
 if parts[0]!='export'and any(x in parts for x in ['best','last','optimizer']):continue
 t.add(f,arcname=str(f.relative_to(base)),recursive=False)
t.close()
'''
        child=subprocess.Popen([*SSH,'python3 -c '+shlex.quote(source)],stdout=subprocess.PIPE);target=local/('initial-cache'if a.action=='fetch-initial'else'server-results');target.mkdir(exist_ok=True)
        with tarfile.open(fileobj=child.stdout,mode='r|gz')as t:t.extractall(target,filter='data')
        if child.wait():raise RuntimeError('Fetch failed')
        print(target);return
    compile(source,'codec-control','exec');result=subprocess.run([*SSH,'python3 -'],input=source,text=True,capture_output=True)
    print(result.stdout)
    if result.returncode:raise RuntimeError(result.stderr[-1800:])


if __name__=='__main__':main()
