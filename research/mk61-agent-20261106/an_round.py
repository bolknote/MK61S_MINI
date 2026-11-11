"""Matched internal-adapter ablation on two B200s; exam after selection."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import json
import os
import shutil
import subprocess
import sys
import time
from an_common import ROOT, PARENT, ARMS, write, sha
from run_experiment import REPO, SCRIPT, run


def status(phase, **values): write(ROOT/'status.json', {'phase': phase, 'unix': time.time(), **values})


def worker(arm, action):
    with (ROOT/(arm+'-'+action+'-controller.log')).open('a') as log:
        p = subprocess.run([sys.executable, '-u', SCRIPT+'an_round.py', 'worker', arm, action], cwd=REPO,
            env={**os.environ, 'MK61_AGENT_GPU': '0' if arm == 'direct' else '1'}, stdout=log, stderr=subprocess.STDOUT)
    if p.returncode: raise RuntimeError((arm, action, p.returncode))


def parallel(action):
    with ThreadPoolExecutor(max_workers=2) as pool:
        for f in as_completed([pool.submit(worker, a, action) for a in ARMS]): f.result()


def main():
    if len(sys.argv) > 1:
        arm, action = sys.argv[2:4]
        run('hex-hypothesis-v2/'+arm+'-'+action+'.log', SCRIPT+'an_jobs.py', action, '--arm', arm, timeout=14400); return
    ROOT.mkdir(exist_ok=True); lock = (ROOT/'controller.lock').open('a+'); fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
    if (ROOT/'complete.json').exists(): return
    status('preflight'); run('hex-hypothesis-v2/prepare.log', SCRIPT+'an_jobs.py', 'prepare', timeout=14400)
    status('training_internal_goal_code_contrasts'); parallel('train')
    records = {a: json.loads((ROOT/a/'training.json').read_text()) for a in ARMS}
    assert records['direct']['same_draw_digest'] == records['planned']['same_draw_digest'] and records['direct']['counts'] == records['planned']['counts']
    assert records['direct']['starting_checkpoint_sha256'] == records['planned']['starting_checkpoint_sha256'], 'One actual starting checkpoint'
    choices = {a: json.loads((ROOT/a/'best.json').read_text()) for a in ARMS}
    research = {a: json.loads((ROOT/a/'research.json').read_text()) for a in ARMS}
    selected = max(ARMS, key=lambda a: choices[a]['key'])
    write(ROOT/'preselected.json', {'selected_arm': selected, 'choices': choices, 'research': research,
        'fresh_used_for_selection': False, 'strict_original_nonregression': True})
    status('sealed_fresh_baseline'); run('hex-hypothesis-v2/initial-fresh.log', SCRIPT+'an_jobs.py', 'baseline', timeout=14400)
    status('sealed_fresh_Q4_and_exports'); parallel('audit')
    shutil.copytree(PARENT/'export/compiler', ROOT/'export/compiler', dirs_exist_ok=True)
    shutil.copytree(ROOT/'export'/selected, ROOT/'export/selected-research', dirs_exist_ok=True)
    for manifest in ['data-frozen.json', 'prepared.json']:
        for n, d in json.loads((ROOT/manifest).read_text())['files'].items(): assert sha(ROOT/n) == d, n
    for n, d in json.loads((ROOT/'prepared.json').read_text())['source_hashes'].items(): assert sha(REPO/SCRIPT/n) == d, n
    write(ROOT/'complete.json', {'completed': True, 'optimizer_updates': sum(r['steps'] for r in records.values())}); status('complete')


if __name__ == '__main__':
    try: main()
    except BaseException as error:
        if len(sys.argv) == 1: status('failed', error=repr(error))
        raise
