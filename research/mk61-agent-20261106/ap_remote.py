"""Authorized transport of the new frozen course and isolated two-GPU experiment."""
import argparse
import json
import shlex
import subprocess
import tarfile
from remote import SSH,STATE,HERE,REPO,BASE


def main():
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['deploy','start','status','fetch']);a=ap.parse_args()
    remote=json.loads(STATE.read_text())['directory'];local=BASE/'step-debug-v1';local.mkdir(exist_ok=True)
    if a.action=='deploy':
        files=list(HERE.glob('*.py'))+list(HERE.glob('*.cpp'))+list(HERE.glob('*.hpp'))
        frozen=local/'data-frozen.json'
        if frozen.exists():
            metadata=json.loads(frozen.read_text());files+=[local/n for n in metadata['files']]+[frozen]
            files+=[p for p in(local/'core-source').rglob('*')if p.is_file()]
        archive=local/'deploy.tar.gz'
        with tarfile.open(archive,'w:gz')as stream:
            for p in files:stream.add(p,arcname=str(p.relative_to(REPO)),recursive=False)
        source='import tarfile,sys;tarfile.open(fileobj=sys.stdin.buffer,mode="r|gz").extractall('+repr(remote)+',filter="data")'
        with archive.open('rb')as stream:subprocess.run([*SSH,'python3 -c '+shlex.quote(source)],stdin=stream,check=True)
        print(json.dumps({'files':len(files),'bytes':archive.stat().st_size,'frozen_course_included':frozen.exists()}));return
    prefix='from pathlib import Path\nimport json,sys,subprocess,os\nr=Path('+repr(remote)+')\nd=r/".build/mk61-agent-20261106/step-debug-v1"\nd.mkdir(exist_ok=True)\n'
    if a.action=='start':
        source=prefix+'''assert(d/'data-frozen.json').exists(),'Deploy frozen diagnosis data first'
marker=d/'start-launch.json'
if marker.exists():
 item=json.loads(marker.read_text());p=Path('/proc')/str(item['pid'])
 if p.exists()and b'ap_round.py'in(p/'cmdline').read_bytes():raise RuntimeError('Own controller already running')
with(d/'controller.log').open('a')as log:
 child=subprocess.Popen(['python3','-u','research/mk61-agent-20261106/ap_round.py'],cwd=r,
  env={**os.environ,'PYTHONPATH':str(r/'research/mk61-agent-20261106')},stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
item={'pid':child.pid};marker.write_text(json.dumps(item));print(json.dumps(item))
'''
    elif a.action=='status':
        source=prefix+"""for name in ['status.json','full/status.json','short/status.json','full/best.json','short/best.json']:
 p=d/name
 if p.exists():print(name,p.read_text()[-2200:])
for name in ['prepare.log','full-train.log','short-train.log','full-audit.log','short-audit.log','controller.log']:
 p=d/name
 if p.exists():print(name,p.read_text()[-700:])
"""
    else:
        source=prefix+'''import tarfile
t=tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz')
for p in sorted(d.rglob('*')):
 if not p.is_file()or '__pycache__'in p.parts:continue
 parts=p.relative_to(d).parts
 if p.suffix=='.pt'or p.name=='last.safetensors':continue
 t.add(p,arcname=str(p.relative_to(d)),recursive=False)
t.close()
'''
        child=subprocess.Popen([*SSH,'python3 -c '+shlex.quote(source)],stdout=subprocess.PIPE);target=local/'server-results';target.mkdir(exist_ok=True)
        with tarfile.open(fileobj=child.stdout,mode='r|gz')as stream:stream.extractall(target,filter='data')
        if child.wait():raise RuntimeError('Fetch failed')
        print(target);return
    result=subprocess.run([*SSH,'python3 -'],input=source,text=True,capture_output=True);print(result.stdout)
    if result.returncode:raise RuntimeError(result.stderr[-3000:])


if __name__=='__main__':main()
