"""Run one bounded post-selection GPU audit, then fetch only its completed files."""
import json
import shlex
import subprocess
import sys
import tarfile
from cb_common import ROOT,HERE,read,write,sha
from remote import SSH,STATE


def main():
    remote=read(STATE)['directory'];source='from pathlib import Path\nimport os,sys,json\nr=Path('+repr(remote)+')\nd=r/".build/mk61-agent-20261106/spec-actor-paired-formats-v1"\n'
    source+='''sys.path.insert(0,str(r/'research/mk61-agent-20261106'))
from cb_common import check_frozen,sha
check_frozen();plan=json.loads((d/'extra-protocol.json').read_text());assert sha(r/'research/mk61-agent-20261106/cb_extra.py')==plan['source_sha256']
assert json.loads((d/'controller-complete.json').read_text())['all_own_workers_joined']
os.environ['MK61_AGENT_GPU']=str(json.loads((d/'policy.json').read_text())['host_gpu'])
from run_experiment import run,SCRIPT
if not(d/'extra-complete.json').exists():run('spec-actor-paired-formats-v1/extra-worker.log',SCRIPT+'cb_extra.py',timeout=14400)
jobs=__import__('subprocess').check_output(['sudo','-n','docker','ps','--no-trunc','--format','{{.Names}} {{.Command}}'],text=True)
assert not [line for line in jobs.splitlines()if 'cb_extra.py'in line]
print((d/'extra-complete.json').read_text())
'''
    result=subprocess.run([*SSH,'python3 -'],input=source,text=True,capture_output=True,timeout=14500)
    if result.returncode:raise RuntimeError(f'SSH exit {result.returncode}: '+result.stderr[-2000:]+result.stdout[-1000:])
    print(result.stdout,flush=True)
    fetch='from pathlib import Path\nimport sys,json,tarfile\nd=Path('+repr(remote)+')/".build/mk61-agent-20261106/spec-actor-paired-formats-v1"\n'
    fetch+='''value=json.loads((d/'extra-complete.json').read_text());assert value['complete']
names=['extra-complete.json','extra-protocol.json','extra-protocol-receipt.json','extra-worker.log']
names += ['closed-'+role+'-'+form+'.json'for role,forms in value['additional_formats'].items()for form in forms]
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz')as tar:
 for name in names:
  if(d/name).exists():tar.add(d/name,arcname=name,recursive=False)
'''
    child=subprocess.Popen([*SSH,'python3 -c '+shlex.quote(fetch)],stdout=subprocess.PIPE)
    with tarfile.open(fileobj=child.stdout,mode='r|gz')as tar:tar.extractall(ROOT/'server-results',filter='data')
    assert child.wait()==0
    health=subprocess.run([sys.executable,str(HERE/'cb_remote.py'),'postflight'],text=True,capture_output=True,check=True)
    value=json.loads(health.stdout);value['supplementary_worker_joined']=True
    write(ROOT/'server-results/postflight.json',value)
    print(json.dumps(value),flush=True)


if __name__=='__main__':main()
