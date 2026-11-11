"""Wait for all four A/B panels, then verify native streams and finish the report."""
import json
import subprocess
import sys
import time
from bz_common import ROOT,HERE,REPO,read,write
from remote import SSH,STATE


def main():
    prefix='from pathlib import Path\nimport json\nd=Path('+repr(read(STATE)['directory'])+')/".build/mk61-agent-20261106/spec-compact-prompt-v1"\n'
    query=prefix+'''def get(n):return json.loads((d/n).read_text())if(d/n).exists()else None
out={'status':get('status.json'),'selection':get('preselected.json'),'complete':get('controller-complete.json'),'failure':get('controller-failure.json'),'panels':{}}
for split in ['development','closed']:
 for mode in ['gold','own']:
  name=split+'-'+mode+'.json'
  if(d/name).exists():out['panels'][split+'_'+mode]=get(name)['own']['summary']
print(json.dumps(out))
'''
    last=None;deadline=time.monotonic()+21600
    while True:
        if time.monotonic()>deadline:raise RuntimeError('Compact comparison monitoring deadline')
        try:
            result=subprocess.run([*SSH,'python3 -'],input=query,text=True,capture_output=True,timeout=40)
            if result.returncode:raise RuntimeError(result.stderr[-500:])
            value=json.loads(result.stdout)
        except(RuntimeError,subprocess.TimeoutExpired,json.JSONDecodeError)as error:
            print({'snapshot_retry':type(error).__name__},flush=True);time.sleep(15);continue
        write(ROOT/'live-summary.json',value)
        if value!=last:
            print(value,flush=True);last=value
            path=HERE/'work-state.json';state=read(path);entry=state.get('latest_compact_prompt_diagnostic',{})
            entry.update(phase=(value['status']or{}).get('phase','running'),observed_panels=list(value['panels']))
            state.update(latest_compact_prompt_diagnostic=entry);write(path,state)
        if value['failure']:raise RuntimeError(value['failure'])
        if value['complete']:break
        time.sleep(20)
    for name,args in [('bz_remote.py',['postflight']),('bz_remote.py',['fetch']),('bz_native.py',[]),('bz_finish.py',[])]:
        print({'starting':name,'args':args},flush=True)
        subprocess.run([sys.executable,'-u',str(HERE/name),*args],cwd=REPO,check=True)
    write(ROOT/'pipeline-complete.json',{'complete':True,'optimizer_updates':0,'unix':time.time()})
    print('ALL_COMPACT_PROMPT_WORK_COMPLETE',flush=True)


if __name__=='__main__':
    try:main()
    except BaseException as error:write(ROOT/'pipeline-failure.json',{'error':repr(error),'unix':time.time()});raise
