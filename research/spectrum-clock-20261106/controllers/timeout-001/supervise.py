"""Launch a single reviewed phase; finite parent always reaps its child."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import clock_hil as c

def main():
    parser=argparse.ArgumentParser();parser.add_argument('phase',type=Path)
    parser.add_argument('--seconds',type=int,default=45)
    args=parser.parse_args();phase=args.phase.resolve();p=json.loads(phase.read_text())
    c.need(args.seconds in (45,180,390),'Unreviewed time cap')
    for path,value in p['pins'].items():c.need(c.sha(path)==value,'Changed phase input '+path)
    c.need(p['action'] in ('admit','flash','clock','step') and p['uid']==c.UID,'Wrong phase')
    c.need(args.seconds=={'admit':45,'flash':180,'clock':390,'step':180}[p['action']],'Phase time cap differs')
    grant=phase.with_suffix('.grant.json');out=phase.with_suffix('.result')
    for path in (grant,out):c.need(not path.exists(),'One-shot path already exists '+str(path))
    now=time.time();sources=c.pins();sources[str(Path(__file__).resolve())]=c.sha(__file__)
    grant.write_text(json.dumps(dict(authority='direct human user',user_quote='занимай устройство',
        uid=c.UID,phase_sha256=c.sha(phase),source_pins=sources,
        not_before=now-2,start_before=now+20,finish_before=now+args.seconds),indent=2)+'\n')
    started=time.monotonic();timed_out=False
    with phase.with_suffix('.supervisor.log').open('x') as log:
        child=subprocess.Popen([sys.executable,'-B',str(Path(c.__file__).resolve()),
            '--phase',str(phase),'--grant',str(grant),'--out',str(out)],stdout=log,stderr=subprocess.STDOUT)
        print('STARTED',child.pid,'phase',c.sha(phase),flush=True)
        try:code=child.wait(timeout=args.seconds+15)
        except subprocess.TimeoutExpired:
            timed_out=True;child.terminate()
            try:code=child.wait(timeout=5)
            except subprocess.TimeoutExpired:child.kill();code=child.wait(timeout=5)
    proof=dict(child_pid=child.pid,reaped=True,exit_code=code,timed_out=timed_out,
               elapsed_seconds=time.monotonic()-started)
    phase.with_suffix('.supervisor.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps(proof),flush=True)
    if (out/'receipt.json').exists():
        r=json.loads((out/'receipt.json').read_text())
        print(json.dumps({key:r.get(key) for key in ('status','error','lease')}),flush=True)
    sys.exit(code if code else int(timed_out))
if __name__=='__main__':main()
