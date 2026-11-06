"""Sequential finite phases; stop on the first failure and never reuse a grant."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import clock_hil as c

SCHEDULE=[125,*range(130,251,10)]
def main():
    package=c.PACKAGE;started=time.monotonic();rows=[];error=None
    summary=package/'LADDER-001.json';c.need(not summary.exists(),'Ladder already used')
    previous=package/'RESET-PROBE-001.result/receipt.json'
    pins={str(path):c.sha(path) for path in c.HERE.glob('*.py')}
    proof=dict(status='RUNNING',uid=c.UID,pid=os.getpid(),source_pins=pins,
        schedule=SCHEDULE,full_cosmic_modes=[125,200,250],rows=rows)
    def save():summary.write_text(json.dumps(proof,indent=2)+'\n')
    save()
    try:
        for mhz in SCHEDULE:
            c.need(time.monotonic()-started<1000,'Ladder wall-time cap exceeded')
            for path,value in pins.items():c.need(c.sha(path)==value,'Controller changed during ladder')
            phase=package/f'LADDER-{mhz}-001.json'
            generator='make_clock_phase.py' if mhz in (125,200,250) else 'make_step_phase.py'
            subprocess.run([sys.executable,'-B',str(c.HERE/generator),str(mhz),str(previous),str(phase)],
                           check=True,timeout=10)
            seconds=390 if mhz in (125,200,250) else 180
            row=dict(mhz=mhz,phase=str(phase),status='RUNNING');rows.append(row);save()
            print('MODE',mhz,'START',flush=True)
            child=subprocess.Popen([sys.executable,'-B',str(c.HERE/'supervise.py'),str(phase),
                '--seconds',str(seconds)],start_new_session=True)
            timed_out=False
            try:code=child.wait(timeout=min(seconds+30,1080-(time.monotonic()-started)))
            except subprocess.TimeoutExpired:
                timed_out=True;os.killpg(child.pid,signal.SIGTERM)
                try:code=child.wait(timeout=5)
                except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);code=child.wait(timeout=5)
            row.update(supervisor_pid=child.pid,supervisor_reaped=True,exit_code=code,timed_out=timed_out)
            previous=phase.with_suffix('.result')/'receipt.json'
            if previous.exists():
                r=json.loads(previous.read_text());row.update(status=r['status'],receipt=str(previous),receipt_sha256=c.sha(previous),
                    lease=r.get('lease'),error=r.get('error'))
            else:row.update(status='HOLD',error='No phase receipt')
            save();c.need(code==0 and not timed_out and row['status']=='PASS' and row['lease']=='reserved_ports_closed',
                         f'First failure at{mhz}MHz: stop ladder')
            print('MODE',mhz,'PASS',flush=True)
        proof.update(status='PASS',native_binding=r['native_binding'],expected=r['expected'],
                     final_receipt=str(previous),lease='reserved_ports_closed')
    except BaseException as failure:
        error=failure;proof.update(status='HOLD',error=repr(failure))
    finally:proof['elapsed_seconds']=time.monotonic()-started;save()
    if error is not None:raise error
    print('LADDER PASS; final125MHz, CDC closed',flush=True)
if __name__=='__main__':main()
