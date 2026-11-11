"""Transport only the isolated semantic experiment and its frozen sources."""
import argparse
import json
import shlex
import subprocess
import tarfile
from ay_common import ROOT,HERE,REPO,read
from remote import SSH,STATE


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['deploy','start','status','fetch']);a=p.parse_args()
    remote=read(STATE)['directory']
    if a.action=='deploy':
        frozen=read(ROOT/'frozen.json');paths=[HERE/n for n in frozen['sources']]
        paths+=[ROOT/n for n in frozen['files']]+[ROOT/'frozen.json',ROOT/'prepared.json']
        archive=ROOT/'deploy.tar.gz'
        with tarfile.open(archive,'w:gz')as stream:
            for path in paths:stream.add(path,arcname=str(path.relative_to(REPO)),recursive=False)
        source='import tarfile,sys;tarfile.open(fileobj=sys.stdin.buffer,mode="r|gz").extractall('+repr(remote)+',filter="data")'
        with archive.open('rb')as f:subprocess.run([*SSH,'python3 -c '+shlex.quote(source)],stdin=f,check=True)
        print(json.dumps({'files':len(paths),'archive_bytes':archive.stat().st_size}));return
    prefix='from pathlib import Path\nimport os,sys,json,subprocess\nr=Path('+repr(remote)+')\nd=r/".build/mk61-agent-20261106/semantic-spec-distill-v1"\n'
    if a.action=='start':
        source=prefix+'''sys.path.insert(0,str(r/'research/mk61-agent-20261106'))
from ay_common import check_frozen
check_frozen();assert(d/'prepared.json').exists()
marker=d/'launch.json'
if marker.exists():
 item=json.loads(marker.read_text());p=Path('/proc')/str(item['pid'])
 if p.exists()and b'ay_round.py'in(p/'cmdline').read_bytes():raise RuntimeError('Own controller already running')
with(d/'controller.log').open('a')as log:
 child=subprocess.Popen(['python3','-u','research/mk61-agent-20261106/ay_round.py'],cwd=r,
   stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
item={'pid':child.pid};marker.write_text(json.dumps(item));print(json.dumps(item))
'''
    elif a.action=='status':
        source=prefix+'''for name in ['status.json','hex/status.json','spec/status.json','hex/best.json','spec/best.json']:
 p=d/name
 if p.exists():print(name,p.read_text()[-1600:])
for name in ['controller.log','hex-train.log','spec-train.log','hex-audit.log','spec-audit.log']:
 p=d/name
 if p.exists():print(name,p.read_text()[-900:])
print(subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader']).decode())
'''
    else:
        source=prefix+'''import tarfile
t=tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz')
for p in sorted(d.rglob('*')):
 if not p.is_file()or'__pycache__'in p.parts or p.suffix in ['.gz','.pt']:continue
 if p.suffix=='.safetensors'and 'hf'not in p.parts:continue
 t.add(p,arcname=str(p.relative_to(d)),recursive=False)
t.close()
'''
        target=ROOT/'server-results';target.mkdir(exist_ok=True)
        child=subprocess.Popen([*SSH,'python3 -c '+shlex.quote(source)],stdout=subprocess.PIPE)
        with tarfile.open(fileobj=child.stdout,mode='r|gz')as stream:stream.extractall(target,filter='data')
        assert child.wait()==0;print(target);return
    result=subprocess.run([*SSH,'python3 -'],input=source,text=True,capture_output=True);print(result.stdout)
    if result.returncode:raise RuntimeError(result.stderr[-4000:])


if __name__=='__main__':main()
