"""Stage train-only mining, then deploy a frozen isolated SPEC experiment."""
import argparse
import json
import shlex
import subprocess
import tarfile
from bc_common import ROOT,HERE,REPO,read
from remote import SSH,STATE


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['stage','mine','fetch-mining','deploy','start','status','fetch','recovery']);a=p.parse_args()
    remote=read(STATE)['directory']
    if a.action in ['stage','deploy']:
        if a.action=='stage':
            paths=list(HERE.glob('bc_*.py'))+[ROOT/n for n in ['parent.safetensors','ast-frozen.json','teacher-frozen.json','train-clean.jsonl','development-clean.jsonl','closed-clean.jsonl','retired-goals.jsonl','replay-goals.jsonl']]
        else:
            f=read(ROOT/'frozen.json');paths=[HERE/n for n in f['sources']]+[ROOT/n for n in f['files']]+[ROOT/'frozen.json',ROOT/'prepared.json']
        archive=ROOT/(a.action+'.tar.gz')
        with tarfile.open(archive,'w:gz')as stream:
            for path in paths:stream.add(path,arcname=str(path.relative_to(REPO)),recursive=False)
        command='import tarfile,sys;tarfile.open(fileobj=sys.stdin.buffer,mode="r|gz").extractall('+repr(remote)+',filter="data")'
        with archive.open('rb')as f:subprocess.run([*SSH,'python3 -c '+shlex.quote(command)],stdin=f,check=True)
        print(json.dumps({'action':a.action,'files':len(paths),'bytes':archive.stat().st_size}));return
    prefix='from pathlib import Path\nimport os,sys,json,subprocess\nr=Path('+repr(remote)+')\nd=r/".build/mk61-agent-20261106/semantic-spec-selfcheck-v1"\n'
    if a.action=='recovery':
        source=prefix+'''from concurrent.futures import ThreadPoolExecutor
assert not(d/'preselected.json').exists()
assert all((d/n/'training.json').exists()for n in ['seed-a','seed-b'])
script="import sys;sys.path.insert(0,'research/mk61-agent-20261106');from run_experiment import run;run('semantic-spec-selfcheck-v1/NAME-recovery.log','research/mk61-agent-20261106/bc_recovery.py','--run','NAME',timeout=7200)"
def worker(item):
 gpu,name=item
 subprocess.run(['python3','-u','-c',script.replace('NAME',name)],cwd=r,env={**os.environ,'MK61_AGENT_GPU':str(gpu)},check=True)
with ThreadPoolExecutor(2)as e:list(e.map(worker,enumerate(['seed-a','seed-b'])))
print('Development-only strength checks complete')
'''
    elif a.action=='mine':
        source=prefix+'''from concurrent.futures import ThreadPoolExecutor
script="import sys;sys.path.insert(0,'research/mk61-agent-20261106');from run_experiment import run;run('semantic-spec-selfcheck-v1/mining-SHARD.log','research/mk61-agent-20261106/bc_mine.py','--shard','SHARD',timeout=7200)"
def worker(shard):
 if(d/f'mined-{shard}.json').exists():return
 subprocess.run(['python3','-u','-c',script.replace('SHARD',str(shard))],cwd=r,env={**os.environ,'MK61_AGENT_GPU':str(shard)},check=True)
with ThreadPoolExecutor(2)as e:list(e.map(worker,[0,1]))
print('Training-only mining complete')
'''
    elif a.action=='start':
        source=prefix+'''sys.path.insert(0,str(r/'research/mk61-agent-20261106'))
from bc_common import check_frozen
check_frozen();assert(d/'prepared.json').exists()
marker=d/'launch.json'
if marker.exists():
 item=json.loads(marker.read_text());p=Path('/proc')/str(item['pid'])
 if p.exists()and b'bc_round.py'in(p/'cmdline').read_bytes():raise RuntimeError('Own controller running')
with(d/'controller.log').open('a')as log:
 child=subprocess.Popen(['python3','-u','research/mk61-agent-20261106/bc_round.py'],cwd=r,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
item={'pid':child.pid};marker.write_text(json.dumps(item));print(json.dumps(item))
'''
    elif a.action=='status':
        source=prefix+'''for name in ['status.json','seed-a/status.json','seed-b/status.json','seed-a/best.json','seed-b/best.json','preselected.json']:
 p=d/name
 if p.exists():print(name,p.read_text()[-1800:])
for name in ['controller.log','seed-a-train.log','seed-b-train.log','mining-0.log','mining-1.log']:
 p=d/name
 if p.exists():print(name,p.read_text()[-700:])
print(subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader'],text=True))
'''
    else:
        source=prefix+'''import tarfile
t=tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz')
for p in sorted(d.rglob('*')):
 if not p.is_file()or'__pycache__'in p.parts or p.suffix in ['.gz','.pt']:continue
 if MINING_ONLY and not p.name.startswith('mined-'):continue
 if p.suffix=='.safetensors'and 'hf'not in p.parts:continue
 t.add(p,arcname=str(p.relative_to(d)),recursive=False)
t.close()
'''.replace('MINING_ONLY',repr(a.action=='fetch-mining'))
        target=ROOT if a.action=='fetch-mining'else ROOT/'server-results';target.mkdir(exist_ok=True)
        child=subprocess.Popen([*SSH,'python3 -c '+shlex.quote(source)],stdout=subprocess.PIPE)
        with tarfile.open(fileobj=child.stdout,mode='r|gz')as stream:stream.extractall(target,filter='data')
        assert child.wait()==0;print(target);return
    result=subprocess.run([*SSH,'python3 -'],input=source,text=True,capture_output=True);print(result.stdout)
    if result.returncode:raise RuntimeError(result.stderr[-4000:])


if __name__=='__main__':main()
