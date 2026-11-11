"""Join all ablations and the preselected audit; print compact progress only."""
import json
import subprocess
import sys
import time
from ca_common import ROOT,HERE,REPO,read,write
from remote import SSH,STATE


def main():
    prefix='from pathlib import Path\nimport json\nd=Path('+repr(read(STATE)['directory'])+')/".build/mk61-agent-20261106/spec-prompt-parts-v1"\n'
    query=prefix+'''def get(n):return json.loads((d/n).read_text())if(d/n).exists()else None
out={'status':get('status.json'),'selection':get('preselected.json'),'complete':get('controller-complete.json'),'failure':get('controller-failure.json'),'panels':{}}
for path in [*sorted(d.glob('development-*.json')),*sorted(d.glob('closed-*.json'))]:
 out['panels'][path.stem]=json.loads(path.read_text())['own']['summary']
print(json.dumps(out))
'''
    last_status=None;seen=set();selection_seen=False;deadline=time.monotonic()+28800
    while True:
        if time.monotonic()>deadline:raise RuntimeError('Prompt parts monitoring deadline')
        try:
            result=subprocess.run([*SSH,'python3 -'],input=query,text=True,capture_output=True,timeout=40)
            if result.returncode:raise RuntimeError(result.stderr[-500:])
            value=json.loads(result.stdout)
        except(RuntimeError,subprocess.TimeoutExpired,json.JSONDecodeError)as error:
            print({'snapshot_retry':type(error).__name__},flush=True);time.sleep(15);continue
        write(ROOT/'live-summary.json',value)
        if value['status']!=last_status:
            print({'status':value['status'],'panels_complete':list(value['panels'])},flush=True);last_status=value['status']
            path=HERE/'work-state.json';state=read(path);entry=state.get('latest_prompt_parts_diagnostic',{})
            entry.update(phase=(value['status']or{}).get('phase','running'),observed_panels=list(value['panels']))
            state['latest_prompt_parts_diagnostic']=entry;write(path,state)
        for name,summary in value['panels'].items():
            if name not in seen:print({'completed_panel':name,'summary':summary},flush=True);seen.add(name)
        if value['selection'] and not selection_seen:
            print({'preselected':value['selection']},flush=True);selection_seen=True
        if value['failure']:raise RuntimeError(value['failure'])
        if value['complete']:break
        time.sleep(20)
    for name,args in [('ca_remote.py',['postflight']),('ca_remote.py',['fetch']),('ca_native.py',[]),('ca_finish.py',[])]:
        print({'starting':name,'args':args},flush=True)
        subprocess.run([sys.executable,'-u',str(HERE/name),*args],cwd=REPO,check=True)
    write(ROOT/'pipeline-complete.json',{'complete':True,'optimizer_updates':0,'unix':time.time()});print('ALL_PROMPT_PARTS_WORK_COMPLETE',flush=True)


if __name__=='__main__':
    try:main()
    except BaseException as error:write(ROOT/'pipeline-failure.json',{'error':repr(error),'unix':time.time()});raise
