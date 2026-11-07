"""Control and fetch only the isolated distillation round over the authorized SSH route."""
import argparse
import json
from pathlib import Path
import subprocess
import tarfile

from remote import SSH,STATE,BASE


def rpc(source):
    # Send source on stdin, not as an oversized command-line/mux packet.
    r=subprocess.run([*SSH,'python3 -'],input=source,text=True,capture_output=True)
    if r.stdout:print(r.stdout)
    if r.returncode:raise RuntimeError(r.stderr[-2000:])


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['launch','resume','status','fetch','hard-status','hard-fetch']);args=p.parse_args()
    remote=json.loads(STATE.read_text())['directory']
    prefix='from pathlib import Path\nimport json,os,signal,subprocess,sys,time\nroot=Path('+repr(remote)+')\nd=root/".build/mk61-agent-20261106/distill-v1"\n'
    if args.action=='hard-status':
        rpc(prefix+'''d=root/'.build/mk61-agent-20261106/distill-hard'
for name in ['status.json','data-manifest.json','preselected.json','controller.log']:
 p=d/name
 if p.exists():print(name,p.read_text()[-2200:])
for arm in ['dpo','text-only']:
 for name in ['status.json','training.json']:
  p=d/arm/name
  if p.exists():
   v=json.loads(p.read_text());v.pop('history',None);print(arm+'/'+name,json.dumps(v))
 for p in sorted((d/arm).glob('development-*.json'),key=lambda f:int(f.stem.split('-')[-1]))[-2:]:
  v=json.loads(p.read_text());n=v['by_kind']['natural_language'];print(arm,p.stem,n,'formal',v['passed']-n['passed'])
for name in ['prepare.log','dpo.log','text-only.log']:
 p=d/name
 if p.exists():print(name,p.read_text()[-900:])
''')
    elif args.action=='launch':
        rpc(prefix+'''d.mkdir(exist_ok=True)
def running(name,needle):
 p=d/name
 if not p.exists():return False
 pid=json.loads(p.read_text())['pid'];q=Path('/proc')/str(pid)
 return q.exists() and needle.encode() in (q/'cmdline').read_bytes() and (q/'cwd').resolve()==root
if running('controller-launch.json','distill_round.py'):raise RuntimeError('Round controller is already running')
if running('teacher-launch.json','teacher_data.py'):raise RuntimeError('Teacher is still running; do not duplicate')
for name in ['teacher-manifest.json','teacher-candidates.jsonl','teacher-verified.jsonl','teacher-rejected.jsonl']:
 p=d/name
 if p.exists():p.rename(p.with_name(p.name+'.schema-v1-'+str(int(time.time()))))
with (d/'teacher-controller-v2.log').open('w') as log:
 p=subprocess.Popen([sys.executable,'-u','research/mk61-agent-20261106/teacher_data.py','--workers','4'],cwd=root,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
(d/'teacher-launch.json').write_text(json.dumps({'pid':p.pid})+'\\n')
with (d/'controller.log').open('w') as log:
 c=subprocess.Popen([sys.executable,'-u','research/mk61-agent-20261106/distill_round.py'],cwd=root,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
(d/'controller-launch.json').write_text(json.dumps({'pid':c.pid})+'\\n')
print(json.dumps({'teacher_pid':p.pid,'round_controller_pid':c.pid,'remote':str(d)}))
''')
    elif args.action=='resume':
        rpc(prefix+'''active=d/'clean-controller-launch.json'
if active.exists():
 pid=json.loads(active.read_text())['pid'];proc=Path('/proc')/str(pid)
 if proc.exists()and b'distill_clean_round.py'in(proc/'cmdline').read_bytes()and(proc/'cwd').resolve()==root:raise RuntimeError('Clean controller already running; inspect status')
p=d/'controller-launch.json'
if p.exists():
 pid=json.loads(p.read_text())['pid'];proc=Path('/proc')/str(pid)
 if proc.exists() and b'distill_round.py' in(proc/'cmdline').read_bytes() and(proc/'cwd').resolve()==root:raise RuntimeError('Controller already running')
# A pre-training checker revision may leave a completed data snapshot with the
# old numerical validation inputs. Update only its validation component.
p=d/'data-manifest.json'
if p.exists():
 import hashlib
 natural=[json.loads(s)for s in(d/'validation-v2.jsonl').read_text().splitlines()]
 formal=[json.loads(s)for s in(root/'.build/mk61-agent-20261106/tasks/validation-extended-v2.jsonl').read_text().splitlines()]
 controls=[x for x in formal if x['kind']in['branch','loop','state']]
 selection=d/'selection.jsonl';selection.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\\n'for x in natural+formal[:8]+controls))
 manifest=json.loads(p.read_text());manifest['files']['selection.jsonl']=hashlib.sha256(selection.read_bytes()).hexdigest();manifest['validation_probes']='v2, corrected before gradients';p.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\\n')
with (d/'controller.log').open('a') as log:
 c=subprocess.Popen([sys.executable,'-u','research/mk61-agent-20261106/distill_round.py','--wait-existing-preparation'],cwd=root,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
(d/'controller-launch.json').write_text(json.dumps({'pid':c.pid})+'\\n')
print(json.dumps({'resumed_controller_pid':c.pid}))
''')
    elif args.action=='status':
        rpc(prefix+'''for name in ['status.json','generation-status.json','verification-status.json','teacher-manifest.json','data-manifest.json','own-error-manifest.json','preselected.json']:
 p=d/name
 if p.exists():print(name,p.read_text()[-2400:])
for arm in ['structured','direct','structured-clean','direct-clean']:
 for name in ['status.json','training.json']:
  p=d/arm/name
  if p.exists():
   v=json.loads(p.read_text());v.pop('history',None);print(arm+'/'+name,json.dumps(v))
for p in [d/'controller.log',d/'prepare.log',d/'clean-controller.log']:
 if p.exists():print(p.name,p.read_text()[-1000:])
for p in (root/'.build/mk61-agent-20261106/distill-broad').glob('*status.json'):
 print('broad/'+p.name,p.read_text()[-1200:])
''')
    else:
        import shlex
        for name in (['distill-hard']if args.action=='hard-fetch'else['distill-v1','distill-broad']):
            command=prefix+'d=root/".build/mk61-agent-20261106"/'+repr(name)+'\n'+'''import tarfile
t=tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz')
for f in sorted(d.rglob('*')):
 if f.is_file() and '__pycache__' not in f.parts:t.add(f,arcname=str(f.relative_to(d)),recursive=False)
t.close()
'''
            # Short command, no file payload; stdout is binary tar.
            process=subprocess.Popen([*SSH,'python3 -c '+shlex.quote(command)],stdout=subprocess.PIPE)
            target=BASE/name/'server-results';target.mkdir(exist_ok=True,parents=True)
            with tarfile.open(fileobj=process.stdout,mode='r|gz') as stream:stream.extractall(target,filter='data')
            if process.wait():raise RuntimeError('Distillation fetch failed')
            print(target)


if __name__=='__main__':main()
