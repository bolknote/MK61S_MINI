"""Attend the coordinator barrier; never stop active optimizer workers."""
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from compose_common import ROOT,ARMS
from run_experiment import REPO,SCRIPT


def main():
    lock=(ROOT/'extension.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if(ROOT/'coordinator-transfer.json').exists():return
    barrier=json.loads((ROOT/'coordinator-barrier.json').read_text());assert barrier['held']
    pid=barrier['pid'];proc=Path('/proc')/str(pid);started=time.monotonic()
    while not all((ROOT/f'{arm}-phase3/training.json').exists()for arm in ARMS):
        if time.monotonic()-started>10800:raise TimeoutError('Third phase did not finish')
        time.sleep(10)
    good=False
    for arm in ARMS:
        records=[]
        for phase in [1,2,3]:
            t=json.loads((ROOT/f'{arm}-phase{phase}/training.json').read_text())
            records.append(next(r for r in t['history']if r['step']==t['best_step']))
        if max(records,key=lambda r:r['key'])['good_quality_gate']:good=True
    assert(proc/'cwd').resolve()==REPO and b'compose_round.py'in(proc/'cmdline').read_bytes()
    if good:
        os.kill(pid,signal.SIGCONT);barrier.update(held=False,resolution='Validation target met; resume original final selection')
        (ROOT/'coordinator-barrier.json').write_text(json.dumps(barrier,indent=2)+'\n');return
    while not(ROOT/'morphology-phase4/manifest.json').exists():
        marker=json.loads((ROOT/'morphology4-launch.json').read_text());builder=Path('/proc')/str(marker['pid'])
        if not builder.exists():raise RuntimeError('Own grammar builder ended without manifest: '+(ROOT/'morphology4-controller.log').read_text()[-1500:])
        if time.monotonic()-started>10800:raise TimeoutError('Fourth-phase data did not complete')
        time.sleep(10)
    assert all(json.loads((ROOT/f'{arm}-phase3/status.json').read_text())['phase']=='complete'for arm in ARMS)
    assert(ROOT/'phase4-extra-train.jsonl').exists()and not(ROOT/'preselected.json').exists()
    # Both GPU courses have finished. Terminate only their held coordinator;
    # queued TERM is delivered on CONT before it can open the final audit.
    os.kill(pid,signal.SIGTERM);os.kill(pid,signal.SIGCONT)
    gate=(ROOT/'controller.lock').open('a+')
    for _ in range(60):
        try:fcntl.flock(gate,fcntl.LOCK_EX|fcntl.LOCK_NB);break
        except BlockingIOError:time.sleep(1)
    else:raise RuntimeError('Old own coordinator did not release its lock')
    fcntl.flock(gate,fcntl.LOCK_UN)
    with(ROOT/'start-controller.log').open('a')as log:
        child=subprocess.Popen([sys.executable,'-u',SCRIPT+'compose_round.py'],cwd=REPO,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    (ROOT/'start-launch.json').write_text(json.dumps({'pid':child.pid,'script':'compose_round.py','continuation':'phase4'})+'\n')
    record={'old_coordinator':pid,'new_coordinator':child.pid,'completed_optimizer_phases_before_transfer':3,
            'active_optimizer_workers_terminated':False,'fresh_remained_closed':True,'data':'phase4-extra-train.jsonl'}
    barrier.update(held=False,resolution='Completed third phase; transferred to bounded-grammar continuation')
    (ROOT/'coordinator-barrier.json').write_text(json.dumps(barrier,indent=2)+'\n')
    (ROOT/'coordinator-transfer.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record),flush=True)


if __name__=='__main__':main()
