"""Operate only full-isa-v1 through the user's authorized three-jump route."""
import argparse
import json
import shlex
import subprocess
import tarfile

from remote import SSH,STATE,HERE,REPO,BASE


def main():
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['deploy','data','start','status','fetch']);a=ap.parse_args()
    remote=json.loads(STATE.read_text())['directory'];local=BASE/'full-isa-v1'
    if a.action=='deploy':
        files=list(HERE.glob('*.py'))+list(HERE.glob('*.cpp'))
        names=['catalog.json','coverage.json','curriculum.json','output-token-ids.json','data-frozen.json','run-policy-frozen.json','policy.json',
          'train.jsonl','validation.jsonl','audit.jsonl','closed-natural.jsonl','historical-fragments.jsonl','observed-user-reproductions.jsonl']
        files += [local/name for name in names if(local/name).exists()]
        files += [p for p in(local/'core-source').rglob('*')if p.is_file()]
        archive=local/'deploy.tar.gz'
        with tarfile.open(archive,'w:gz')as stream:
            for path in files:stream.add(path,arcname=str(path.relative_to(REPO)),recursive=False)
        source='import tarfile,sys;tarfile.open(fileobj=sys.stdin.buffer,mode="r|gz").extractall('+repr(remote)+',filter="data")'
        with archive.open('rb')as stream:subprocess.run([*SSH,'python3 -c '+shlex.quote(source)],stdin=stream,check=True)
        print(json.dumps({'files':len(files),'bytes':archive.stat().st_size}));return
    prefix='from pathlib import Path\nimport json,sys,subprocess,os\nr=Path('+repr(remote)+')\nd=r/".build/mk61-agent-20261106/full-isa-v1"\n'
    if a.action in ['data','start']:
        source=prefix+f'''marker=d/{(a.action+'-launch.json')!r}
if marker.exists():
 item=json.loads(marker.read_text());p=Path('/proc')/str(item['pid'])
 if p.exists()and b'full_isa_round.py'in(p/'cmdline').read_bytes()and(p/'cwd').resolve()==r:raise RuntimeError('Own full ISA controller active')
with(d/{(a.action+'-controller.log')!r}).open('a')as log:
 child=subprocess.Popen([sys.executable,'-u','research/mk61-agent-20261106/full_isa_round.py',{a.action!r}],cwd=r,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
item={{'pid':child.pid,'script':'full_isa_round.py','action':{a.action!r}}};marker.write_text(json.dumps(item)+'\\n');print(json.dumps(item))
'''
    elif a.action=='status':
        source=prefix+'''for f in [d/'status.json',d/'teacher/status.json',d/'full/status.json',d/'protected/status.json']:
 if f.exists():
  x=json.loads(f.read_text());print(str(f.relative_to(d)),json.dumps({k:v for k,v in x.items()if k not in ['counts','files','errors']}))
for name in ['data-controller.log','start-controller.log','prepare-run.log','full.log','protected.log']:
 p=d/name
 if p.exists():print(name,p.read_text()[-700:])
'''
    else:
        source=prefix+'''import tarfile
t=tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz')
for p in sorted(d.rglob('*')):
 if not p.is_file()or '__pycache__'in p.parts:continue
 parts=p.relative_to(d).parts
 if parts[0]=='teacher-runtime-cache':continue
 if parts[0]!='export'and any(x in parts for x in ['best','last','optimizer']):continue
 t.add(p,arcname=str(p.relative_to(d)),recursive=False)
t.close()
'''
        child=subprocess.Popen([*SSH,'python3 -c '+shlex.quote(source)],stdout=subprocess.PIPE)
        target=local/'server-results';target.mkdir(exist_ok=True)
        with tarfile.open(fileobj=child.stdout,mode='r|gz')as stream:stream.extractall(target,filter='data')
        if child.wait():raise RuntimeError('Fetch failed')
        print(target);return
    result=subprocess.run([*SSH,'python3 -'],input=source,text=True,capture_output=True);print(result.stdout)
    if result.returncode:raise RuntimeError(result.stderr[-2200:])


if __name__=='__main__':main()
