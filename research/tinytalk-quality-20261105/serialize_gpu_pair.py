#!/usr/bin/env python3
"""Temporarily serialize two owned training containers; always resume the saved in-memory run."""
import json
from pathlib import Path
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
PAUSED = '56e1ae849868'
ACTIVE = 'fb1c3486bc97'


def docker(*args):
    return subprocess.run(['sudo','-n','docker',*args], capture_output=True, text=True, check=True).stdout


def check(cid, label):
    value = json.loads(docker('inspect', cid))[0]
    assert any(m['Source'] == str(ROOT) and m['Destination'] == '/work' for m in value['Mounts'])
    args = value['Config']['Cmd']
    assert 'train.py' in args and args[args.index('--output') + 1] == label
    return value


def completed(label):
    path = ROOT / label / 'training.json'
    try:
        return 'seconds' in json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return False


def status(phase, **kw):
    value = {'phase':phase, 'unix':time.time(), **kw}
    path = ROOT / 'operations/schedule-state.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2))
    temporary.replace(path)
    print(json.dumps(value), flush=True)


def main():
    check(PAUSED, 'grounded40')
    check(ACTIVE, 'grounded65')
    deadline = time.monotonic() + 90
    while True:
        if completed('grounded40') or completed('grounded65'):
            status('no_scheduling_change_needed')
            return
        latest = None
        for line in reversed((ROOT / 'grounded40.log').read_text().splitlines()):
            try:
                latest = json.loads(line)
                break
            except ValueError:
                pass
        if latest and 'step' in latest and latest['step'] % 1000:
            break  # Between grading boundaries: no outstanding teacher call from this job.
        if time.monotonic() > deadline:
            status('could_not_find_safe_training_interval')
            return
        time.sleep(3)
    try:
        docker('pause', PAUSED)
        status('grounded65_running_first', paused_container=PAUSED, active_container=ACTIVE,
            preserved_step=latest['step'], automatic_resume='After grounded65 completion; at most 45 minutes')
        deadline = time.monotonic() + 2700
        while not completed('grounded65') and time.monotonic() < deadline:
            if not check(ACTIVE, 'grounded65')['State']['Running']:
                break
            time.sleep(5)
    finally:
        value = check(PAUSED, 'grounded40')
        if value['State']['Paused']:
            docker('unpause', PAUSED)
        status('grounded40_resumed', grounded65_completed=completed('grounded65'))


if __name__ == '__main__':
    def interrupt(signum, frame):
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    main()
