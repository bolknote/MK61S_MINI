#!/usr/bin/env python3
"""Bounded source-defined exit from our returned APP error dialog."""
import ast
from datetime import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path('/Users/bolk/Projects/MK61S_MINI')
HERE = Path(__file__).resolve().parent
OUT = ROOT / '.build/rp2040-interpolator-20261023/hardware-INTERP002-recovery-2'
PRIOR = ROOT / '.build/rp2040-interpolator-20261023/hardware-INTERP002'
HANDOFF = ROOT / '.build/picocalc-device-handoff.json'
PARENT = '8c6bf5026df9a73c79b6bf473d6092c9dadb5680d047debf0cbd49162b40148a'
RUNNER_SHA = '55acc0ac97668b515b1a12f4819626c74cfa27d1cfb9cf62911d31114780f343'
READY_SHA = '25d9a8c071dbd2a9ba049acbe9bcdb99423ec6934a36864915c5ebdcf11de9d5'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def main():
    require(sys.argv[1:] == ['--run', PARENT], 'Exact recovery invocation required')
    source = (HERE / 'run-pico.py').read_bytes()
    require(sha(source) == RUNNER_SHA, 'Frozen runner changed')
    spec = importlib.util.spec_from_file_location('_interp002_recovery_runner', HERE / 'run-pico.py')
    runner = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = runner
    spec.loader.exec_module(runner)
    ready_bytes = runner.READY.read_bytes()
    require(sha(ready_bytes) == READY_SHA, 'Frozen READY changed')
    for path, row in json.loads(ready_bytes)['files'].items():
        data = Path(path).read_bytes()
        require(len(data) == row['bytes'] and sha(data) == row['sha256'], 'Frozen input changed: ' + path)
    binding = runner.load(runner.PACKET / 'source/bind.py', '_interp002_recovery_binding')
    bound = binding.BoundSet(runner.PACKET, runner.PACKET_SHA)
    a = bound.accepted
    parent = HANDOFF.read_bytes()
    require(sha(parent) == PARENT, 'Fault handoff changed')
    lease = json.loads(parent)
    require(lease['owner'] == 'interp-INTERP002' and lease['state'] == 'INTERP002_RECOVERY_FAIL_CLOSED'
            and lease['operator_process_exited'] and not lease['serial_port_open'], 'Fault owner not closed')
    OUT.mkdir(exist_ok=False)
    (OUT / 'parent-handoff.byteexact.json').write_bytes(parent)
    state = dict(status='STARTING', scope='INTERP002_ONLY_ERROR_FOREGROUND_RECOVERY', pid=os.getpid(),
                 reset=False, flash=False, app_executed=False, files_written=False, failures=[])

    def save():
        a.core.atomic_json(OUT / 'receipt.json', state)

    def evidence(name, data):
        a.core.atomic_bytes(OUT / name, data)

    # Reuse the exact reviewed Port class, including first-status/raw retention
    # and its narrow asynchronous-prefix parser; do not duplicate its transport.
    tree = ast.parse(source)
    original_main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    port_class = next(n for n in original_main.body if isinstance(n, ast.ClassDef) and n.name == 'Port')
    factory = ast.parse('def make_port(bound, OUT, evidence):\n command_count = 0\n return Port\n')
    factory.body[0].body.insert(1, port_class)
    ast.fix_missing_locations(factory)
    namespace = dict(runner.__dict__)
    exec(compile(factory, '<exact-reviewed-Port>', 'exec'), namespace)
    Port = namespace['make_port'](bound, OUT, evidence)
    p = w = None
    original_status = (PRIOR / 'initial.txt').read_text()
    before = json.loads((PRIOR / 'calculator-before.json').read_text())
    lease.update(state='INTERP002_RECOVERY_ACTIVE', scope=state['scope'], enabled=True,
                 hardware_window_granted=True, active_operator_pid=os.getpid(), operator_process_exited=False)
    a.core.atomic_json(HANDOFF, lease)
    save()
    try:
        usb = subprocess.check_output(['/usr/sbin/ioreg', '-a', '-l', '-r', '-c', 'IOUSBHostDevice'], timeout=15)
        evidence('usb-before.plist', usb)
        usb_tool = runner.load(ROOT / '.build/picocalc-fresh-sd-verifier-20261023/sd-only-v2/transport.py', '_interp002_recovery_usb')
        usb_tool.usb_admission(usb, runner.UID, 18022400, runner.PORT)
        holder = subprocess.run(['/usr/sbin/lsof', '-nP', '-t', '--', runner.PORT], capture_output=True, timeout=10)
        evidence('lsof-before.txt', holder.stdout + holder.stderr)
        require(holder.returncode == 1 and not holder.stdout and not holder.stderr, 'Port held')
        p = Port()
        w = bound.adapter.Wire(a, lambda: p).open()
        lease['serial_port_open'] = True
        a.core.atomic_json(HANDOFF, lease)

        def status(label, mode, service):
            s = w.status()
            evidence(label + '.txt', s.encode())
            a.frames.assert_observed_status_faults(w.raw)
            a.core.assert_health(s, 'A7483AE6', 'C0A51996', 754344)
            require(a.core.field(s, 'BOOTS') == 3 and 'RESET_REASON=00010001' in s, 'Unexpected reset')
            for fragment in ('TERMINAL=' + mode, 'SERVICE=' + service + ' ', 'RUNTIME=NONE',
                             'DIRTY=0', 'M61_ACTIVE=0', 'IP=00 RUN=0 BUSY=0', 'UI=CALCULATOR', 'USB_DISK=0'):
                require(fragment in s, 'Unexpected ' + fragment + ' at ' + label)
            require(runner.settings(s) == runner.settings(original_status), 'Settings changed at ' + label)
            print(label, flush=True)
            return s

        first = status('initial-message', 'COMMAND', 'MESSAGE')
        require('RESULT=[APP returned an error]' in first and 'PATH=[/INTRP02/FLOOK.APP]' in first,
                'Different dialog')

        def control(value, label):
            require(w.command_ready, 'No key into unreturned APP')
            p.record_tx(label, value)
            require(os.write(p.fd, value) == len(value), 'Short control write')

        control(b'\x1e', 'message-raw-mode')
        status('message-raw', 'RAW', 'MESSAGE')
        control(b'\x1b', 'message-to-browser')
        status('browser', 'RAW', 'BROWSER')
        control(b'\x1b', 'browser-to-calculator')
        status('closed', 'RAW', 'CLOSED')
        start = len(p.text)
        control(b'\x1f', 'calculator-command-mode')
        p.wait_text(b'mk61> ', start, timeout=8)
        final = status('commands', 'COMMAND', 'CLOSED')
        captured = {cmd: w.command(cmd, 60) for cmd in ('reg', 'stk', 'dump', 'hout', 'pwd', 'alarm')}
        a.core.atomic_json(OUT / 'calculator-final.json', captured)
        require(captured == before, 'Calculator data differs')
        date_before = time.time()
        rtc = runner.canonical('date', w.command('date'))
        date_after = time.time()
        rtc_fields = re.findall(r'\bRTC=([^\s]+)', original_status)
        require(len(rtc_fields) == 1, 'Missing unique saved RTC')
        first_rtc = rtc_fields[0]
        tx = [json.loads(line) for line in (PRIOR / 'tx.jsonl').read_text().splitlines()]
        # The saved first status was captured after this exact status request;
        # use the following command timestamp as its conservative upper bound.
        initial_tx = next(i for i, row in enumerate(tx) if row['kind'] == 'status')
        lower = tx[initial_tx]['wall']
        upper = tx[initial_tx + 1]['wall']
        elapsed = (datetime.fromisoformat(rtc) - datetime.fromisoformat(first_rtc)).total_seconds()
        interval = [date_before - upper - 2, date_after - lower + 2]
        a.core.atomic_json(OUT / 'rtc-comparison.json', dict(before=first_rtc, after=rtc,
                           elapsed_seconds=elapsed, allowed_seconds=interval))
        require(interval[0] <= elapsed <= interval[1], 'RTC trajectory differs')
        state.update(preservation_verified=True, final_RTC=rtc, final_settings=runner.settings(final), final_IP=0)
    except BaseException as error:
        state['failures'].append(repr(error))
        print('FAIL ' + repr(error), flush=True)
    finally:
        if w is not None:
            try:
                w.close()
            except BaseException as error:
                state['failures'].append('close: ' + repr(error))
            evidence('decoded-transcript.bin', w.raw)
        elif p is not None:
            p.close()
        state['serial_closed'] = p is None or (p.fd == -1 and p.lock_fd == -1)
        state['status'] = 'PASS_CLOSED' if state.get('preservation_verified') and not state['failures'] and state['serial_closed'] else 'FAIL_CLOSED'
        save()
        current = json.loads(HANDOFF.read_bytes())
        require(current['owner'] == 'interp-INTERP002', 'Owner changed; do not overwrite')
        current.update(state='INTERP002_RECOVERY_' + state['status'], enabled=False, hardware_window_granted=False,
                       serial_port_open=not state['serial_closed'], own_FD_closed=state['serial_closed'],
                       own_advisory_lock_released=state['serial_closed'], operator_process_exited=False,
                       recovery_receipt=str(OUT / 'receipt.json'), current_data_preservation_pending=not state.get('preservation_verified', False))
        if state.get('preservation_verified'):
            current.update(current_RTC=state['final_RTC'], current_settings=state['final_settings'], current_IP=0,
                           current_pre_post_preserved=True)
        a.core.atomic_json(HANDOFF, current)
        evidence('closed-handoff-before-parent-exit.json', HANDOFF.read_bytes())
    print(json.dumps(state), flush=True)
    return 0 if state['status'] == 'PASS_CLOSED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
