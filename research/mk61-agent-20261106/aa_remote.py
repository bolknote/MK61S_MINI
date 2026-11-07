"""Authorized isolated SSH transport; no changes to other experiments/services."""
import argparse
import json
import shlex
import subprocess
import tarfile
from remote import SSH, STATE, HERE, REPO, BASE


def main():
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['deploy','prepare','start','status','fetch']);a=ap.parse_args()
    remote=json.loads(STATE.read_text())['directory'];local=BASE/'action-alignment-v1';local.mkdir(exist_ok=True)
    if a.action=='deploy':
        files=list(HERE.glob('*.py'))+list(HERE.glob('*.cpp'))+list(HERE.glob('*.hpp'))
        archive=local/'deploy.tar.gz'
        with tarfile.open(archive,'w:gz')as stream:
            for p in files:stream.add(p,arcname=str(p.relative_to(REPO)),recursive=False)
        source='import tarfile,sys;tarfile.open(fileobj=sys.stdin.buffer,mode="r|gz").extractall('+repr(remote)+',filter="data")'
        with archive.open('rb')as stream:subprocess.run([*SSH,'python3 -c '+shlex.quote(source)],stdin=stream,check=True)
        print(json.dumps({'files':len(files),'bytes':archive.stat().st_size}));return
    prefix='from pathlib import Path\nimport json,sys,subprocess,os\nr=Path('+repr(remote)+')\nd=r/".build/mk61-agent-20261106/action-alignment-v1"\nd.mkdir(exist_ok=True)\n'
    if a.action in ['prepare','start']:
        script='aa_data.py'if a.action=='prepare'else'aa_round.py'
        if a.action=='prepare':
            command=["python3","-u","-c",'from run_experiment import run;run("action-alignment-v1/data.log","research/mk61-agent-20261106/aa_data.py",timeout=14400)']
        else:command=['python3','-u','research/mk61-agent-20261106/aa_round.py']
        source=prefix+f'''marker=d/{repr(a.action+'-launch.json')}
if marker.exists():
 item=json.loads(marker.read_text());p=Path('/proc')/str(item['pid'])
 if p.exists()and b'{script}'in(p/'cmdline').read_bytes()and(p/'cwd').resolve()==r:raise RuntimeError('Own action experiment already running')
with(d/{repr(a.action+'-controller.log')}).open('a')as log:
 child=subprocess.Popen({command!r},cwd=r,env={{**os.environ,'PYTHONPATH':str(r/'research/mk61-agent-20261106')}},stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
item={{'pid':child.pid,'script':{script!r}}};marker.write_text(json.dumps(item)+'\\n');print(json.dumps(item))
'''
    elif a.action=='status':
        source=prefix+'''for p in [d/'status.json',d/'warmup/status.json',d/'sft/status.json',d/'preference/status.json']:
 if p.exists():print(str(p.relative_to(d)),p.read_text()[-1800:])
for n in ['data.log','start-controller.log','warmup.log','sft-train.log','preference-train.log']:
 p=d/n
 if p.exists():print(n,p.read_text()[-900:])
'''
    else:
        source=prefix+'''import tarfile
t=tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz')
for p in sorted(d.rglob('*')):
 if not p.is_file()or '__pycache__'in p.parts:continue
 parts=p.relative_to(d).parts
 if p.suffix=='.pt':continue
 if parts[0]!='export'and any(x in parts for x in ['last','optimizer','checkpoint']):continue
 t.add(p,arcname=str(p.relative_to(d)),recursive=False)
t.close()
'''
        child=subprocess.Popen([*SSH,'python3 -c '+shlex.quote(source)],stdout=subprocess.PIPE)
        target=local/'server-results';target.mkdir(exist_ok=True)
        with tarfile.open(fileobj=child.stdout,mode='r|gz')as stream:stream.extractall(target,filter='data')
        if child.wait():raise RuntimeError('Action experiment fetch failed')
        print(target);return
    result=subprocess.run([*SSH,'python3 -'],input=source,text=True,capture_output=True);print(result.stdout)
    if result.returncode:raise RuntimeError(result.stderr[-2600:])


if __name__=='__main__':main()
