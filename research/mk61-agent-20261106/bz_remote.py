"""Deploy, inspect and fetch only the gold diagnostic, leaving Qwen untouched."""
import argparse
import json
import shlex
import subprocess
import tarfile
from bz_common import ROOT,HERE,REPO,read
from remote import SSH,STATE


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['deploy','start','status','fetch','postflight']);args=parser.parse_args()
    remote=read(STATE)['directory'];prefix='from pathlib import Path\nimport json,sys,os,time,subprocess\nr=Path('+repr(remote)+')\nd=r/".build/mk61-agent-20261106/spec-compact-prompt-v1"\n'
    if args.action=='deploy':
        frozen=read(ROOT/'frozen.json');files=[HERE/n for n in frozen['sources']]+[ROOT/n for n in frozen['files']]+[ROOT/'frozen.json',ROOT/'prepared.json']
        archive=ROOT/'deploy.tar.gz'
        with tarfile.open(archive,'w:gz')as tar:
            for path in files:tar.add(path,arcname=str(path.relative_to(REPO)),recursive=False)
        command='import sys,tarfile;tarfile.open(fileobj=sys.stdin.buffer,mode="r|gz").extractall('+repr(remote)+',filter="data")'
        with archive.open('rb')as stream:subprocess.run([*SSH,'python3 -c '+shlex.quote(command)],stdin=stream,check=True)
        print(json.dumps({'files':len(files),'archive_bytes':archive.stat().st_size}));return
    if args.action=='start':
        source=prefix+'''sys.path.insert(0,str(r/'research/mk61-agent-20261106'))
from bz_common import check_frozen
check_frozen();assert not(d/'launch.json').exists();policy=json.loads((d/'policy.json').read_text())
free=subprocess.check_output(['nvidia-smi','--query-gpu=memory.free','--format=csv,noheader,nounits','-i',str(policy['host_gpu'])],text=True)
assert int(free.strip())>=policy['minimum_free_MiB']
with(d/'controller.log').open('w')as log:
 child=subprocess.Popen(['python3','-u','research/mk61-agent-20261106/bz_round.py'],cwd=r,env={**os.environ,'MK61_AGENT_GPU':str(policy['host_gpu'])},stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
value={'pid':child.pid,'unix':time.time(),'host_gpu':policy['host_gpu'],'Qwen_service_modified':False,'optimizer_updates':0};(d/'launch.json').write_text(json.dumps(value));print(json.dumps(value))
'''
    elif args.action=='status':
        source=prefix+'''result={}
for name in ['status.json','preselected.json','complete.json','controller-complete.json','controller-failure.json']:
 if(d/name).exists():result[name]=json.loads((d/name).read_text())
for split in ['development','closed']:
 for mode in ['gold','own']:
  if(d/(split+'-'+mode+'.json')).exists():
   value=json.loads((d/(split+'-'+mode+'.json')).read_text());result[split+'_'+mode]=value['own']['summary']
print(json.dumps(result))
for name in ['controller.log','worker.log']:
 if(d/name).exists():print(name,(d/name).read_text()[-1400:])
'''
    elif args.action=='postflight':
        source=prefix+'''assert json.loads((d/'controller-complete.json').read_text())['all_own_workers_joined']
jobs=subprocess.check_output(['sudo','-n','docker','ps','--no-trunc','--format','{{.Names}} {{.Command}}'],text=True)
owned=[line for line in jobs.splitlines()if'bz_jobs.py'in line];assert not owned
health=subprocess.check_output(['curl','-s','-o','/dev/null','-w','%{http_code}','--max-time','10','http://127.0.0.1:8000/health'],text=True);assert health=='200'
value={'complete':True,'all_own_workers_joined':True,'own_containers':owned,'Qwen_health':health,'other_services_unchanged':True,
 'GPU':subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,memory.free,utilization.gpu','--format=csv,noheader'],text=True),'unix':time.time()}
(d/'postflight.json').write_text(json.dumps(value,indent=2)+chr(10));print(json.dumps(value))
'''
    else:
        source=prefix+'''import tarfile
assert json.loads((d/'controller-complete.json').read_text())['complete']
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz')as tar:
 for path in sorted(d.rglob('*')):
  if not path.is_file()or'__pycache__'in path.parts or path.suffix=='.gz'or path.name=='controller.lock':continue
  tar.add(path,arcname=str(path.relative_to(d)),recursive=False)
'''
        child=subprocess.Popen([*SSH,'python3 -c '+shlex.quote(source)],stdout=subprocess.PIPE);target=ROOT/'server-results';target.mkdir(exist_ok=True)
        with tarfile.open(fileobj=child.stdout,mode='r|gz')as tar:tar.extractall(target,filter='data')
        assert child.wait()==0;print(target);return
    result=subprocess.run([*SSH,'python3 -'],input=source,text=True,capture_output=True,timeout=45);print(result.stdout)
    if result.returncode:raise RuntimeError(result.stderr[-3000:])


if __name__=='__main__':main()
