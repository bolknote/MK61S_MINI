"""Coordinate post-training semantic/action coupling on development only."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import json
import os
import subprocess
import sys
import time
from al_common import ROOT, ARMS, write
from run_experiment import REPO, SCRIPT, run


def worker(arm, action):
    with (ROOT/f'{arm}-coupling-{action}-controller.log').open('a') as log:
        p = subprocess.run([sys.executable, '-u', SCRIPT+'al_couple_round.py', 'worker', arm, action], cwd=REPO,
            env={**os.environ, 'MK61_AGENT_GPU': '0' if arm == 'late' else '1'}, stdout=log, stderr=subprocess.STDOUT)
    if p.returncode: raise RuntimeError((arm, action, p.returncode))


def parallel(action):
    with ThreadPoolExecutor(max_workers=2) as pool:
        for f in as_completed([pool.submit(worker, a, action) for a in ARMS]): f.result()


def main():
    if len(sys.argv) > 1:
        arm, action = sys.argv[2:4]; run(f'semantic-cross-v1/{arm}-coupling-{action}.log', SCRIPT+'al_couple.py', action, '--arm', arm, timeout=7200); return
    lock = (ROOT/'coupling.lock').open('a+'); fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
    if (ROOT/'coupling-complete.json').exists(): return
    while not (ROOT/'complete.json').exists():
        status = json.loads((ROOT/'status.json').read_text())
        if status['phase'] == 'failed': raise RuntimeError(status)
        time.sleep(10)
    write(ROOT/'coupling-status.json', {'phase': 'development', 'unix': time.time()}); parallel('control')
    choices = {a: json.loads((ROOT/a/'coupled.json').read_text()) for a in ARMS}; selected = max(ARMS, key=lambda a: choices[a]['key'])
    write(ROOT/'coupling-preselected.json', {'selected_arm': selected, 'choices': choices, 'fresh_used_for_selection': False, 'optimizer_updates': 0})
    write(ROOT/'coupling-status.json', {'phase': 'sealed_fresh', 'unix': time.time()}); parallel('audit')
    write(ROOT/'coupling-complete.json', {'completed': True, 'optimizer_updates': 0})
    write(ROOT/'coupling-status.json', {'phase': 'complete', 'unix': time.time()})


if __name__ == '__main__':
    try: main()
    except BaseException as error:
        if len(sys.argv) == 1: write(ROOT/'coupling-status.json', {'phase': 'failed', 'error': repr(error)})
        raise
