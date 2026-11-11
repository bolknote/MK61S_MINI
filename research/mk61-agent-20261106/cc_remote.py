"""Deploy and operate only the SPEC retention recovery, preserving the user's Qwen."""
import argparse
import json
import shlex
import subprocess
import tarfile
from cc_common import ROOT,HERE,REPO,read
from remote import SSH,STATE


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['probe','deploy','start','status','fetch','postflight','preflight']);a=p.parse_args()
    remote=read(STATE)['directory'];prefix='from pathlib import Path\nimport json,sys,os,time,subprocess\nr=Path('+repr(remote)+')\nd=r/".build/mk61-agent-20261106/spec-action-choice-v1"\n'
    if a.action=='deploy':
        f=read(ROOT/'frozen.json');files=[HERE/n for n in f['sources']]+[ROOT/n for n in f['files']]+[ROOT/'frozen.json',ROOT/'prepared.json']
        archive=ROOT/'deploy.tar.gz'
        with tarfile.open(archive,'w:gz')as t:
            for path in files:t.add(path,arcname=str(path.relative_to(REPO)),recursive=False)
        source='import sys,tarfile;tarfile.open(fileobj=sys.stdin.buffer,mode="r|gz").extractall('+repr(remote)+',filter="data")'
        with archive.open('rb')as stream:subprocess.run([*SSH,'python3 -c '+shlex.quote(source)],stdin=stream,check=True)
        print(json.dumps({'files':len(files),'archive_bytes':archive.stat().st_size}));return
    if a.action=='probe':
        source=prefix+'''print(subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,memory.free,utilization.gpu','--format=csv,noheader'],text=True))
print(subprocess.check_output(['sudo','-n','docker','ps','--format','{{.Names}} {{.Status}} {{.Ports}}'],text=True))
print('Qwen_health',subprocess.check_output(['curl','-s','-o','/dev/null','-w','%{http_code}','--max-time','10','http://127.0.0.1:8000/health'],text=True))
'''
    elif a.action=='preflight':
        source=prefix+'''sys.path.insert(0,str(r/'research/mk61-agent-20261106'))
from cc_common import check_frozen
check_frozen();policy=json.loads((d/'policy.json').read_text());os.environ['MK61_AGENT_GPU']=str(policy['host_gpu'])
from run_experiment import run,SCRIPT
run('spec-action-choice-v1/GPU-preflight.log',SCRIPT+'cc_gpu_preflight.py',timeout=900)
print((d/'GPU-preflight.json').read_text())
'''
    elif a.action=='start':
        source=prefix+'''sys.path.insert(0,str(r/'research/mk61-agent-20261106'))
from cc_common import check_frozen
check_frozen();assert not(d/'launch.json').exists();policy=json.loads((d/'policy.json').read_text());proof=json.loads((d/'GPU-preflight.json').read_text());assert proof['complete']and proof['optimizer_updates']==0
free=subprocess.check_output(['nvidia-smi','--query-gpu=memory.free','--format=csv,noheader,nounits','-i',str(policy['host_gpu'])],text=True)
assert int(free.strip())>=policy['minimum_free_MiB'],'Insufficient room alongside Qwen'
with(d/'controller.log').open('w')as log:
 child=subprocess.Popen(['python3','-u','research/mk61-agent-20261106/cc_round.py'],cwd=r,env={**os.environ,'MK61_AGENT_GPU':str(policy['host_gpu'])},stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
v={'pid':child.pid,'unix':time.time(),'host_gpu':policy['host_gpu'],'Qwen_service_modified':False};(d/'launch.json').write_text(json.dumps(v));print(json.dumps(v))
'''
    elif a.action=='status':
        source=prefix+'''for n in ['status.json','best.json','preselected.json','controller-complete.json','controller-failure.json']:
 p=d/n
 if p.exists():print(n,p.read_text()[-2400:])
for n in ['controller.log','worker.log']:
 p=d/n
 if p.exists():print(n,p.read_text()[-1600:])
'''
    elif a.action=='postflight':
        source=prefix+'''assert json.loads((d/'controller-complete.json').read_text())['all_own_workers_joined']
jobs=subprocess.check_output(['sudo','-n','docker','ps','--no-trunc','--format','{{.Names}} {{.Command}}'],text=True)
owned=[line for line in jobs.splitlines()if'cc_jobs.py'in line];assert not owned
health=subprocess.check_output(['curl','-s','-o','/dev/null','-w','%{http_code}','--max-time','10','http://127.0.0.1:8000/health'],text=True);assert health=='200'
v={'Qwen_health':health,'complete':True,'all_own_workers_joined':True,'live_remote_recheck_completed':True,'own_containers':owned,'other_services_unchanged':True,
 'GPU':subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,memory.free,utilization.gpu','--format=csv,noheader'],text=True),'unix':time.time()}
(d/'postflight.json').write_text(json.dumps(v,indent=2)+chr(10));print(json.dumps(v))
'''
    else:
        source=prefix+'''import tarfile
assert json.loads((d/'controller-complete.json').read_text())['complete']
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz')as t:
 for p in sorted(d.rglob('*')):
  if not p.is_file()or'__pycache__'in p.parts or p.suffix=='.gz'or p.name=='controller.lock':continue
  if p.is_relative_to(d/'profiles')or p.is_relative_to(d/'export/parent/hf')or p.is_relative_to(d/'export/working/hf'):continue
  if p.suffix=='.safetensors'and'hf'not in p.parts and p.name not in ['best.safetensors','last.safetensors']:continue
  t.add(p,arcname=str(p.relative_to(d)),recursive=False)
'''
        child=subprocess.Popen([*SSH,'python3 -c '+shlex.quote(source)],stdout=subprocess.PIPE);target=ROOT/'server-results';target.mkdir(exist_ok=True)
        with tarfile.open(fileobj=child.stdout,mode='r|gz')as t:t.extractall(target,filter='data')
        assert child.wait()==0;print(target);return
    result=subprocess.run([*SSH,'python3 -'],input=source,text=True,capture_output=True,timeout=900 if a.action=='preflight'else 60);print(result.stdout)
    if result.returncode:raise RuntimeError(result.stderr[-3000:])


if __name__=='__main__':main()
