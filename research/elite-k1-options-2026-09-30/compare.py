"""Replay calculator input; compare actual frames and canonical game data."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
VARIANT=sys.argv[1]
BASE=json.loads((HERE/'baseline.json').read_text())
INFO=json.loads((HERE/VARIANT/'map.json').read_text())

def canonical(s):
    t=json.loads(json.dumps(s))
    if VARIANT=='specialized':
        assert t['pages'][4][7] in (0,10006351,10006751),t
        t['pages'][4][7]=0
    if VARIANT=='gates':
        assert t['pages'][4][7:] in ([0,0],[1052,1052],[6351,6751]),t
        t['pages'][4][7:]=[0,0]
    if VARIANT=='packed-drones':
        p=t['pages'][4][0]
        assert 0<=p<19**5,(p,t)
        assert t['pages'][4][1:5]==[0]*4,t
        t['pages'][4][:5]=[(p//19**i)%19 for i in range(5)]
    return t

def mode(s,labels):
    v=s['regs'][9]
    if v<0:return 'battle'
    if v==0:return 'title'
    return next((k for k in ('new_game','port_input_entry','result_input_entry')
                 if v==labels[k]),str(v))

def replay(pair):
    i,session=pair
    env={**os.environ}
    env.pop('ELITE_TRACE',None)
    if VARIANT=='packed-drones':env['ELITE_PACKED_DRONES']='1'
    if VARIANT=='overlay':env['ELITE_CHECK_OVERLAY']='1'
    r=subprocess.run([str(HERE/'runner'),str(HERE/VARIANT)],
                     input='\n'.join(session['commands'])+'\n',
                     text=True,capture_output=True,check=True,timeout=120,env=env)
    states=[json.loads(line) for line in r.stdout.splitlines()]
    assert len(states)==len(session['states']),(i,r.stderr)
    stats=[]
    commands=[c for c in session['commands'] if not c.startswith('set ')]
    for j,(b,raw) in enumerate(zip(session['states'],states)):
        if VARIANT=='overlay':
            initial=(HERE/VARIANT/'initial.raw').read_bytes()
            port=initial[6*112:6*112+63].hex()
            battle=initial[15*112:15*112+63].hex()
            zero=bytes(63).hex()
            expected=[battle,port,zero] if mode(raw,INFO['labels'])=='battle' else [port,zero,battle]
            assert raw['overlay_heads']==expected,(i,j,raw)
        n=canonical(raw)
        differences=[]
        for k in ('pages','frame','frame_changes','auto_display','segmented','running','error','input_frame_stable','x'):
            if b[k]!=n[k]:differences.append((k,b[k],n[k]))
        if mode(b,BASE['labels'])!=mode(n,INFO['labels']):differences.append(('mode',b['regs'][9],n['regs'][9]))
        if mode(n,INFO['labels'])=='battle' and b['regs'][5:9]!=n['regs'][5:9]:
            differences.append(('battle caches',b['regs'][5:9],n['regs'][5:9]))
        stats.append(dict(session=i,state=j,command=commands[j],before=b['steps'],after=n['steps'],
                          delta=n['steps']-b['steps'],differences=differences,
                          enemy=b['pages'][3][0],mode=mode(b,BASE['labels'])))
    return dict(commands=session['commands'],states=states),stats

with ThreadPoolExecutor(max_workers=4) as pool:
    results=list(pool.map(replay,enumerate(BASE['sessions'])))
rows=[t for _,s in results for t in s]
diff=[t for t in rows if t['differences']]
fast=[t for t in rows if t['delta']<0]
slow=[t for t in rows if t['delta']>0]
report=dict(variant=VARIANT,occupied_bytes=INFO['occupied_bytes'],bin_bytes=INFO['bin_bytes'],
            states=len(rows),before_steps=sum(t['before'] for t in rows),steps=sum(t['after'] for t in rows),
            faster=len(fast),unchanged=len(rows)-len(fast)-len(slow),slower=len(slow),
            max_regression=max((t['delta'] for t in slow),default=0),
            difference_count=len(diff),differences=diff[:5],fast=fast,slow=slow)
(HERE/(VARIANT+'.json')).write_text(json.dumps(dict(labels=INFO['labels'],sessions=[s for s,_ in results])))
(HERE/(VARIANT+'.comparison.json')).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('fast','slow')},ensure_ascii=False))
if diff:sys.exit(1)
