"""Wait through real training, sealed audits and native checks without relaunching SGD."""
import json
import subprocess
import sys
import time
from cb_common import ROOT,HERE,REPO,read,write
from remote import SSH,STATE


def main():
    prefix='from pathlib import Path\nimport json\nd=Path('+repr(read(STATE)['directory'])+')/".build/mk61-agent-20261106/spec-actor-paired-formats-v1"\n'
    query=prefix+'''def get(n):return json.loads((d/n).read_text())if(d/n).exists()else None
out={'status':get('status.json'),'best':get('best.json'),'selection':get('preselected.json'),'training':get('training.json'),'complete':get('controller-complete.json'),'failure':get('controller-failure.json'),'panels':{},'decisions':{}}
for path in [*sorted(d.glob('parent-*.json')),*sorted(d.glob('step-*-development-*.json')),*sorted(d.glob('step-*-retention-*.json')),*sorted(d.glob('closed-*.json'))]:
 value=json.loads(path.read_text())
 if'own'in value:out['panels'][path.stem]=value['own']['summary']
for path in sorted(d.glob('selection-*.json')):out['decisions'][path.stem]=json.loads(path.read_text())
print(json.dumps(out))
'''
    last=None;seen=set();choices=set();deadline=time.monotonic()+43200
    while True:
        if time.monotonic()>deadline:raise RuntimeError('Actor adaptation monitoring deadline')
        try:
            result=subprocess.run([*SSH,'python3 -'],input=query,text=True,capture_output=True,timeout=40)
            if result.returncode:raise RuntimeError(result.stderr[-500:])
            value=json.loads(result.stdout)
        except(RuntimeError,subprocess.TimeoutExpired,json.JSONDecodeError)as error:
            print({'snapshot_retry':type(error).__name__},flush=True);time.sleep(15);continue
        write(ROOT/'live-summary.json',value)
        if value['status']!=last:
            print({'status':value['status'],'best_step':(value['best']or{}).get('step'),'panels_complete':len(value['panels'])},flush=True);last=value['status']
            path=HERE/'work-state.json';state=read(path);entry=state.get('latest_paired_actor_training',{})
            entry.update(phase=(value['status']or{}).get('phase','running'),observed_completed_steps=(value['training']or{}).get('optimizer_updates',(value['status']or{}).get('step',0)))
            state['latest_paired_actor_training']=entry;write(path,state)
        for name,s in value['panels'].items():
            if name not in seen:
                print({'completed_panel':name,'summary':s},flush=True);seen.add(name)
        for name,d in value['decisions'].items():
            if name not in choices:print({'decision':name,**d},flush=True);choices.add(name)
        if value['failure']:raise RuntimeError(value['failure'])
        if value['complete']:break
        time.sleep(20)
    for name,args in [('cb_remote.py',['postflight']),('cb_remote.py',['fetch']),('cb_native.py',[]),('cb_finish.py',[])]:
        print({'starting':name,'args':args},flush=True)
        subprocess.run([sys.executable,'-u',str(HERE/name),*args],cwd=REPO,check=True)
    write(ROOT/'pipeline-complete.json',{'complete':True,'optimizer_updates':read(ROOT/'server-results/training.json')['optimizer_updates'],'unix':time.time()})
    print('ALL_PAIRED_ACTOR_TRAINING_WORK_COMPLETE',flush=True)


if __name__=='__main__':
    try:main()
    except BaseException as error:write(ROOT/'pipeline-failure.json',{'error':repr(error),'unix':time.time()});raise
