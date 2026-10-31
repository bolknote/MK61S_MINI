#!/usr/bin/env python3
"""Run the immutable approved caller, recording its lease before any USB TX."""
import ast
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path('/Users/bolk/Projects/MK61S_MINI')
SCRIPT = ROOT / 'research/rp2040-interpolator-20261023/followon/run-cdc-final.py'
READY = ROOT / '.build/rp2040-interpolator-20261023/followon/cdc-output-final/READY.json'
HANDOFF = ROOT / '.build/picocalc-device-handoff.json'
OUT = ROOT / '.build/rp2040-interpolator-20261023/hardware-INTERP002-cdc-final'
ACTIVATION = ROOT / '.build/rp2040-interpolator-20261023/hardware-INTERP002-cdc-final-activation'
PARENT = '7b527e5199f4411ac38ce8569443b09b87795ea9205777694a62e80f771ad588'
PACKET = '146cccf64ccb9402bf9c516e2979622dc4cafb2e2553a89084e12f18b1440afc'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(name, value):
    with (ACTIVATION / name).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


assert sha(SCRIPT.read_bytes()) == '57c80334fc4e26e8a1af4e38088e9af85ee8420a361898549af3f0cbbfb32ed4'
assert sha(READY.read_bytes()) == PACKET
assert sha(HANDOFF.read_bytes()) == PARENT
for path, pin in json.loads(READY.read_bytes())['files'].items():
    data = Path(path).read_bytes()
    assert len(data) == pin['bytes'] and sha(data) == pin['sha256'], path
assert not OUT.exists()
ACTIVATION.mkdir(exist_ok=False)
argv = [str(SCRIPT), '--run', PARENT, PACKET]
save('argv.json', dict(runner_argv=argv, host_argv=sys.orig_argv, pid=os.getpid(), parent_pid=os.getppid(),
     wall=time.time(), launcher_sha256=sha(Path(__file__).read_bytes()),
     gate='Read-only Python line trace; disabled after recording and asserting the frozen caller lease, before USB admission/TX. Frozen program bytes unchanged.'))
tree = ast.parse(SCRIPT.read_bytes())
main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
gate_line = next(n.lineno for n in main.body if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == 'p' for t in n.targets))
gate_done = False


def trace(frame, event, arg):
    global gate_done
    if event == 'line' and frame.f_code.co_filename == str(SCRIPT) and frame.f_lineno == gate_line:
        raw = HANDOFF.read_bytes()
        assert raw == (OUT / 'granted-handoff.json').read_bytes()
        lease = json.loads(raw)
        assert lease['owner'] == 'interp-INTERP002-cdc-final'
        assert lease['state'] == 'INTERP002_GRANTED' and lease['active_operator_pid'] == os.getpid()
        assert lease['uid'] == 'E6657CD423721C35' and lease['build'] == 'A7483AE6'
        assert lease['scope'] == 'INTERP002_4_APP_CDC_RESULTS_CURRENT_A748_NO_RESET'
        assert lease['parent_handoff_sha256'] == PARENT
        assert lease['enabled'] and lease['hardware_window_granted']
        assert not lease['serial_port_open'] and not lease['operator_process_exited']
        assert not (OUT / 'tx.jsonl').exists() and not (OUT / 'wire.bin').exists()
        save('before-usb-tx.json', dict(status='PASS', new_lease_sha256=sha(raw), parent_sha256=PARENT,
             pid=os.getpid(), runner_argv=sys.argv, serial_constructed=False, USB_TX=False, wall=time.time()))
        gate_done = True
        sys.settrace(None)
        return None
    return trace


print('OPERATOR_PID=' + str(os.getpid()), flush=True)
sys.argv = argv
sys.settrace(trace)
try:
    runpy.run_path(str(SCRIPT), run_name='__main__')
except SystemExit as result:
    save('execution-exit.json', dict(exit_code=result.code, gate_passed=gate_done, pid=os.getpid(), wall=time.time()))
    raise
finally:
    sys.settrace(None)
