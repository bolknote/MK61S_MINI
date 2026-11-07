"""Operate only harness-ablation-v1 over the already authorized SSH route."""
import argparse
import json
import shlex
import subprocess
import tarfile

from remote import SSH,STATE,HERE,REPO,BASE


def main():
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['deploy','start','status','fetch']);a=ap.parse_args()
    remote=json.loads(STATE.read_text())['directory'];local=BASE/'harness-ablation-v1'
    if a.action=='deploy':
        files=list(HERE.glob('*.py'))+list(HERE.glob('*.cpp'))+list(HERE.glob('ha_*.hpp'))+list(local.glob('*.json'))+list(local.glob('*.jsonl'))
        files += [p for p in(local/'core-source').rglob('*')if p.is_file()]
        archive=local/'deploy.tar.gz'
        with tarfile.open(archive,'w:gz')as stream:
            for path in files:stream.add(path,arcname=str(path.relative_to(REPO)),recursive=False)
        source='import tarfile,sys;tarfile.open(fileobj=sys.stdin.buffer,mode="r|gz").extractall('+repr(remote)+',filter="data")'
        with archive.open('rb')as stream:subprocess.run([*SSH,'python3 -c '+shlex.quote(source)],stdin=stream,check=True)
        print(json.dumps({'files':len(files),'bytes':archive.stat().st_size}));return
    prefix='from pathlib import Path\nimport json,sys,subprocess,os\nr=Path('+repr(remote)+')\nd=r/".build/mk61-agent-20261106/harness-ablation-v1"\n'
    if a.action=='start':
        source=prefix+'''marker=d/'launch.json'
if marker.exists():
 item=json.loads(marker.read_text());p=Path('/proc')/str(item['pid'])
 if p.exists()and b'ha_round.py'in(p/'cmdline').read_bytes()and(p/'cwd').resolve()==r:raise RuntimeError('Own harness controller active')
with(d/'controller.log').open('a')as log:
 child=subprocess.Popen([sys.executable,'-u','research/mk61-agent-20261106/ha_round.py'],cwd=r,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
item={'pid':child.pid,'script':'ha_round.py'};marker.write_text(json.dumps(item)+'\\n');print(json.dumps(item))
'''
    elif a.action=='status':
        source=prefix+'''for p in [d/'status.json',d/'direct/status.json',d/'asm/status.json']:
 if p.exists():print(str(p.relative_to(d)),json.dumps({k:v for k,v in json.loads(p.read_text()).items()if k not in ['counts','sample_plan_digest']}))
for name in ['controller.log','prepare-run.log','direct-train.log','asm-train.log','direct-audit.log','asm-audit.log']:
 p=d/name
 if p.exists():print(name,p.read_text()[-1000:])
'''
    else:
        source=prefix+'''import tarfile
t=tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz')
for p in sorted(d.rglob('*')):
 if not p.is_file()or '__pycache__'in p.parts:continue
 parts=p.relative_to(d).parts
 if parts[0]!='export'and any(x in parts for x in ['best','last','optimizer']):continue
 t.add(p,arcname=str(p.relative_to(d)),recursive=False)
t.close()
'''
        child=subprocess.Popen([*SSH,'python3 -c '+shlex.quote(source)],stdout=subprocess.PIPE)
        target=local/'server-results';target.mkdir(exist_ok=True)
        with tarfile.open(fileobj=child.stdout,mode='r|gz')as stream:stream.extractall(target,filter='data')
        if child.wait():raise RuntimeError('Harness fetch failed')
        print(target);return
    result=subprocess.run([*SSH,'python3 -'],input=source,text=True,capture_output=True);print(result.stdout)
    if result.returncode:raise RuntimeError(result.stderr[-2600:])


if __name__=='__main__':main()
