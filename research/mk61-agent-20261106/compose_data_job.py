"""Launch only our optional next-phase data builders in the SSH scratch repo."""
import argparse
import json
import subprocess

from remote import SSH,STATE


def main():
    p=argparse.ArgumentParser();p.add_argument('kind',choices=['augmentation','balanced','morphology']);p.add_argument('--phase',type=int,choices=[2,3,4],required=True);a=p.parse_args()
    remote=json.loads(STATE.read_text())['directory'];script={'augmentation':'compose_augment.py','balanced':'compose_balanced.py','morphology':'compose_morphology.py'}[a.kind]
    if a.kind=='morphology'and a.phase!=4:raise ValueError('Full grammar builder is phase4 only')
    source='''from pathlib import Path
import json,sys,subprocess
r=Path('''+repr(remote)+''');d=r/'.build/mk61-agent-20261106/composition-v1'
'''+f'''marker=d/{(a.kind+str(a.phase)+'-launch.json')!r}
if marker.exists():
 item=json.loads(marker.read_text());proc=Path('/proc')/str(item['pid'])
 if proc.exists()and(proc/'cwd').resolve()==r and {script.encode()!r}in(proc/'cmdline').read_bytes():raise RuntimeError('Own data builder already running')
with(d/{(a.kind+str(a.phase)+'-controller.log')!r}).open('a')as log:
 child=subprocess.Popen([sys.executable,'-u','research/mk61-agent-20261106/{script}']+{([]if a.kind=='morphology'else['--phase',str(a.phase)])!r},cwd=r,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
marker.write_text(json.dumps({{'pid':child.pid,'script':{script!r},'phase':{a.phase}}})+'\\n');print(marker.read_text())
'''
    result=subprocess.run([*SSH,'python3 -'],input=source,text=True,capture_output=True)
    print(result.stdout)
    if result.returncode:raise RuntimeError(result.stderr[-1800:])


if __name__=='__main__':main()
