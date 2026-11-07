"""Deploy, inspect and fetch the isolated capacity/curriculum experiment."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import tarfile

from remote import SSH,STATE,BASE,HERE,REPO


def rpc(script):
    r=subprocess.run([*SSH,'python3 -'],input=script,text=True,capture_output=True)
    if r.stdout:print(r.stdout)
    if r.returncode:raise RuntimeError(r.stderr[-2200:])


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['deploy','teacher','start','continue','finalize','status','fetch']);args=p.parse_args()
    remote=json.loads(STATE.read_text())['directory'];root=BASE/'capacity-v1'
    prefix='from pathlib import Path\nimport json,subprocess,sys,time,os\nr=Path('+repr(remote)+')\nd=r/".build/mk61-agent-20261106/capacity-v1"\n'
    if args.action=='deploy':
        files=list(HERE.glob('*.py'))
        files += [root/n for n in ['frozen.json','quantization-plan.json','method.json','initial-weight-budget.json','level1-validation-manual.jsonl','level1-fresh.jsonl','level2-validation-manual.jsonl','level2-fresh.jsonl']if(root/n).exists()]
        files += [p for p in(root/'grown-initial/hf').glob('*')if p.is_file()]
        files += [root/'grown-initial/growth.json']
        archive=root/'deploy.tar.gz'
        with tarfile.open(archive,'w:gz')as t:
            for f in files:t.add(f,arcname=str(f.relative_to(REPO)),recursive=False)
        command='import sys,tarfile;tarfile.open(fileobj=sys.stdin.buffer,mode="r|gz").extractall('+repr(remote)+',filter="data")'
        with archive.open('rb')as stream:
            result=subprocess.run([*SSH,'python3 -c '+shlex.quote(command)],stdin=stream,capture_output=True)
        if result.returncode:raise RuntimeError(result.stderr.decode()[-1600:])
        print(json.dumps({'files':len(files),'archive_bytes':archive.stat().st_size,'remote':remote}))
    elif args.action in ['teacher','start','continue','finalize']:
        teacher=args.action=='teacher';finalize=args.action=='finalize'
        marker='teacher-launch.json'if teacher else'finalize-launch.json'if finalize else'controller-launch.json'
        script='course_teacher.py'if teacher else'capacity_finalize.py'if finalize else'capacity_continue.py'if args.action=='continue'else'capacity_round.py'
        extra=['--root','.build/mk61-agent-20261106/capacity-v1/teacher-level1','--level','1','--workers','4']if teacher else['--wait']if finalize else[]
        logfile='teacher-controller.log'if teacher else'finalize-controller.log'if finalize else'controller.log'
        rpc(prefix+f'''d.mkdir(exist_ok=True)
p=d/{marker!r}
if p.exists():
 pid=json.loads(p.read_text())['pid'];proc=Path('/proc')/str(pid)
 if proc.exists()and {script.encode()!r}in(proc/'cmdline').read_bytes()and(proc/'cwd').resolve()==r:raise RuntimeError('This controller is already running')
with(d/{logfile!r}).open('a')as log:
 child=subprocess.Popen([sys.executable,'-u','research/mk61-agent-20261106/{script}',*{extra!r}],cwd=r,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
p.write_text(json.dumps({{'pid':child.pid}})+'\\n');print(json.dumps({{'pid':child.pid,'script':{script!r}}}))
''')
    elif args.action=='status':
        rpc(prefix+'''for p in [d/'status.json',d/'teacher-level1/status.json',d/'teacher-level1/teacher-manifest.json',d/'teacher-level2/status.json',d/'preselected.json']:
 if p.exists():
  value=json.loads(p.read_text())
  if p.name=='teacher-manifest.json':value={k:value[k]for k in ['level','partitions']}
  if p.name=='preselected.json':value={k:value[k]for k in ['level','models','selection']}
  print(str(p.relative_to(d)),json.dumps(value))
for p in sorted(d.glob('*/status.json')):
 if not p.parent.name.startswith('teacher'):print(str(p.relative_to(d)),p.read_text().strip())
for p in sorted((d/'results').glob('*validation.json'),key=lambda x:x.stat().st_mtime)[-4:]:
 value=json.loads(p.read_text());print(p.name,json.dumps(value['summary']))
for p in [d/'controller.log']:
 if p.exists():print(p.name,p.read_text()[-700:])
''')
    else:
        command=prefix+'''import tarfile
t=tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz')
for p in sorted(d.rglob('*')):
 if p.is_file()and '__pycache__'not in p.parts:t.add(p,arcname=str(p.relative_to(d)),recursive=False)
t.close()
'''
        target=root/'server-results';target.mkdir(exist_ok=True)
        process=subprocess.Popen([*SSH,'python3 -c '+shlex.quote(command)],stdout=subprocess.PIPE)
        with tarfile.open(fileobj=process.stdout,mode='r|gz')as t:t.extractall(target,filter='data')
        if process.wait():raise RuntimeError('Capacity result fetch failed')
        print(target)


if __name__=='__main__':main()
