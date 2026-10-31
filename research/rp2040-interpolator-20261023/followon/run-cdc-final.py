#!/usr/bin/env python3
"""One coordinator-granted INTERP run on the existing A748 Pico, without reset."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from datetime import datetime

sys.dont_write_bytecode = True
ROOT = Path('/Users/bolk/Projects/MK61S_MINI')
PACKET = ROOT / '.build/rp2040-interpolator-20261023/combined-v3-v1'
PACKET_SHA = '1a71e2fc0b5f86512945aba7b4b078071c961a551a6658f2da536aea0b427afc'
OUT = ROOT / '.build/rp2040-interpolator-20261023/hardware-INTERP002-cdc-final'
HANDOFF = ROOT / '.build/picocalc-device-handoff.json'
READY = ROOT / '.build/rp2040-interpolator-20261023/followon/cdc-output-final/READY.json'
PORT = '/dev/cu.usbmodem11301'
UID = 'E6657CD423721C35'
DIRECTORY = '/INTRP02'
OWNER = 'interp-INTERP002-cdc-final'


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def canonical(command, reply):
    require(reply.startswith(command + '\r\n') and reply.endswith('\r\nmk61> '),
            'Uncorrelated command response: ' + command)
    return reply[len(command) + 2:-len('\r\nmk61> ')]


def correlated_reply(command, reply, first_status):
    """Separate source-defined complete notices before one exact command echo."""
    require(isinstance(first_status, str) and 'TERMINAL=COMMAND' in first_status,
            'No admitted command-mode status')
    indicators = re.findall(r'(?m)^KBD=[^\r\n]* X=\[([^\]\r\n]+)\] IP=', first_status)
    require(len(indicators) == 1, 'No unique initial indicator for asynchronous notice')
    allowed = {'PICOCALC PANEL INITIALIZED KBD=OK\r\n', 'X=[' + indicators[0] + ']\r\n'}
    prefix = []
    rest = reply
    while not rest.startswith(command + '\r\n'):
        end = rest.find('\r\n')
        require(end >= 0, 'Missing exact command echo')
        notice = rest[:end + 2]
        require(notice in allowed and notice not in prefix and len(prefix) < 2,
                'Unknown or duplicate asynchronous prefix')
        prefix.append(notice)
        rest = rest[end + 2:]
    require(rest.endswith('\r\nmk61> ') and rest.count('\r\nmk61> ') == 1,
            'Missing or ambiguous final prompt')
    require(len(re.findall(r'(?m)^' + re.escape(command) + r'\r$', rest)) == 1,
            'Duplicate command echo')
    require('\x00' not in rest, 'Binary command response')
    return rest, ''.join(prefix)


def settings(status):
    result = {}
    for prefix in ('UI_FONT_FAMILY=', 'UI='):
        rows = [line for line in status.splitlines() if line.startswith(prefix)]
        require(len(rows) == 1, 'Missing settings line: ' + prefix)
        result[prefix] = rows[0]
    for key in ('SETTINGS_WRITES', 'SETTINGS_ERASES', 'SETTINGS_SEQUENCE', 'RTC_SET', 'RTC_PPM'):
        values = re.findall(r'\b' + key + r'=(-?\d+)\b', status)
        require(len(values) == 1, 'Missing settings value: ' + key)
        result[key] = int(values[0])
    return result


def main():
    require(sys.flags.optimize == 0, 'Assertions must be enabled for accepted CRC routines')
    require(len(sys.argv)==4 and sys.argv[1]=='--run', 'Require --run PARENT_SHA READY_SHA')
    PARENT_SHA=sys.argv[2]
    require(len(PARENT_SHA)==64 and len(sys.argv[3])==64, 'Exact handoff and packet SHA required')
    require(sha(READY.read_bytes())==sys.argv[3], 'Follow-on packet changed')
    ready=json.loads(READY.read_text())
    for path, row in ready['files'].items():
        data=Path(path).read_bytes()
        require(len(data)==row['bytes'] and sha(data)==row['sha256'], 'Changed follow-on file: '+path)
    binding = load(PACKET / 'source/bind.py', '_interp_live_binding')
    bound = binding.BoundSet(PACKET, PACKET_SHA)
    bound.apps=ready['apps']
    bound.decoder=load(ROOT/'research/rp2040-interpolator-20261023/followon/decode.py','_interp_followon_decoder')
    cdc_result=load(ROOT/'research/rp2040-interpolator-20261023/followon/cdc-result.py','_interp_followon_cdc_result')
    run_admission=load(ROOT/'research/rp2040-interpolator-20261023/followon/run-admission.py','_interp_followon_run_admission')
    a = bound.accepted
    parent = HANDOFF.read_bytes()
    require(sha(parent) == PARENT_SHA, 'Coordinator handoff changed before claim')
    old = json.loads(parent)
    require('CLOSED' in old['state'] and old['uid']==UID and old['build']=='A7483AE6' and
            not old['serial_port_open'] and old['operator_process_exited'], 'Previous operator is not closed')
    OUT.mkdir(exist_ok=False)
    (OUT / 'parent-handoff.byteexact.json').write_bytes(parent)
    state = dict(status='STARTING', scope='INTERP002_4_APP_CDC_RESULTS_CURRENT_A748_NO_RESET',
                 pid=os.getpid(), physical_measurement=False, completed=[], owned={},
                 directory_created=False, serial_closed=False, failures=[],
                 coordinator_thread='01a164b7-9caa-7011-90d1-807e9630921c',
                 operator_thread='01a1683e-5253-7023-b8a7-3b66a190582e',
                 coordinator_grant='Separate exact CDC-output sole-owner GO required in this chat',
                 packet_sha256=sys.argv[3], transport_reference_packet=PACKET_SHA, reset=False, flash=False, bootsel=False,
                 preservation_scope='Existing calculator/program/stack/CWD/alarm/settings compared byte-for-byte; RTC trajectory. Only new /INTRP02 objects written. No generic full-state claim.')

    def save():
        a.core.atomic_json(OUT / 'receipt.json', state)

    def evidence(name, data):
        a.core.atomic_bytes(OUT / name, data)

    def phase(label):
        state['stage'] = label
        save()
        print(label, flush=True)

    save()
    claim = dict(old, owner=OWNER, operator_thread=state['operator_thread'], state='INTERP002_GRANTED', scope=state['scope'],
                 enabled=True, hardware_window_granted=True, active_operator_pid=os.getpid(),
                 operator_process_exited=False, serial_port_open=False,
                 parent_handoff_sha256=PARENT_SHA, evidence=str(OUT))
    a.core.atomic_json(HANDOFF, claim)
    evidence('granted-handoff.json', HANDOFF.read_bytes())
    p = w = None
    before = initial_settings = root_before = clock_before = None
    boots = None
    command_count = 0

    class Port(bound.port_type):
        def __init__(self):
            self.wire_stream = (OUT / 'wire.bin').open('xb')
            self.tx_stream = (OUT / 'tx.jsonl').open('x')
            self.saved_rx = 0
            self.first_status = None
            try:
                super().__init__(PORT, keyboard_layout=0)
                self.native_display = True
            except BaseException:
                self.wire_stream.close()
                self.tx_stream.close()
                raise

        def record_tx(self, kind, data):
            self.tx_stream.write(json.dumps(dict(kind=kind, hex=data.hex(), wall=time.time())) + '\n')
            self.tx_stream.flush()

        def pump(self, duration=.05):
            try:
                return super().pump(duration)
            finally:
                raw = bytes(getattr(self, 'interp_received', b''))
                self.wire_stream.write(raw[self.saved_rx:])
                self.saved_rx = len(raw)
                self.wire_stream.flush()

        def write_line(self, command):
            nonlocal command_count
            command_count += 1
            self.last_command_text_start = len(self.text)
            self.record_tx('command', command.encode('cp1251') + b'\r')
            return super().write_line(command)

        def command(self, command, timeout=30):
            start = len(self.text)
            try:
                reply = super().command(command, timeout)
                deadline = time.monotonic() + 2
                while not reply.endswith('\r\nmk61> '):
                    require(time.monotonic() < deadline, 'Incomplete command prompt')
                    self.pump(.02)
                    reply = bytes(self.text[self.last_command_text_start:]).decode('cp1251', 'strict')
                correlated, prefix = correlated_reply(command, reply, self.first_status)
                evidence('command-%06d-prefix.bin' % command_count, prefix.encode('cp1251'))
                evidence('command-%06d-correlated.bin' % command_count, correlated.encode('cp1251'))
                canonical(command, correlated)
                return correlated
            finally:
                evidence('command-%06d.bin' % command_count, bytes(self.text[getattr(self, 'last_command_text_start', start):]))

        def status(self, timeout=8):
            self.record_tx('status', b'\x05')
            result = super().status(timeout)
            if self.first_status is None:
                self.first_status = result
            return result

        def close(self):
            try:
                super().close()
            finally:
                if hasattr(self, 'wire_stream') and not self.wire_stream.closed:
                    self.wire_stream.flush()
                    os.fsync(self.wire_stream.fileno())
                    self.wire_stream.close()
                if hasattr(self, 'tx_stream') and not self.tx_stream.closed:
                    self.tx_stream.close()

    def status(label, service='CLOSED'):
        s = w.status()
        evidence(label + '.txt', s.encode())
        a.frames.assert_observed_status_faults(w.raw)
        a.core.assert_health(s, 'A7483AE6', 'C0A51996', 754344)
        require('RUNTIME=NONE' in s and 'M61_ACTIVE=0' in s and 'DIRTY=0' in s,
                'Foreground runtime, VM, or dirty state changed at ' + label)
        require(re.search(r'\bUSB_SCREEN=OFF(?=\s|$)', s) is not None and 'UI=CALCULATOR SELECT=0 VIEW=0' in s,
                'Foreground USB screen or UI changed at ' + label)
        if initial_settings is not None:
            require(settings(s) == initial_settings, 'Foreground settings changed at ' + label)
        require('RUN=0 BUSY=0' in s and 'SERVICE=' + service in s and 'USB_DISK=0' in s,
                'Unexpected foreground at ' + label)
        if boots is not None:
            require(a.core.field(s, 'BOOTS') == boots, 'Unexpected reboot')
        return s

    logical = ('reg', 'stk', 'dump', 'hout', 'pwd', 'alarm')

    def capture(label):
        result = {cmd: w.command(cmd, 60) for cmd in logical}
        a.core.atomic_json(OUT / (label + '.json'), result)
        return result

    def clock_sample():
        start = time.time()
        reply = w.command('date')
        return dict(rtc=canonical('date', reply), wall_before=start, wall_after=time.time())

    def control(value, purpose):
        require(w.command_ready, 'No control key into unreturned APP')
        p.record_tx(purpose, value)
        require(os.write(p.fd, value) == len(value), 'Short control write')

    def leave_viewer(label):
        s = status(label + '-viewer', 'VIEWER')
        require('RUNTIME=NONE' in s, 'APP runtime still active')
        control(b'\x1e', 'viewer-raw-mode')
        require('TERMINAL=RAW' in status(label + '-viewer-raw', 'VIEWER'), 'Expected RAW')
        control(b'\x1b', 'viewer-to-browser')
        require('TERMINAL=RAW' in status(label + '-browser', 'BROWSER'), 'Expected RAW')
        control(b'\x1b', 'browser-to-calculator')
        require('TERMINAL=RAW' in status(label + '-closed'), 'Expected RAW')
        start = len(p.text)
        control(b'\x1f', 'command-mode')
        p.wait_text(b'mk61> ', start, timeout=8)
        require('TERMINAL=COMMAND' in status(label + '-commands'), 'Command mode not acknowledged')

    def leave_error(label):
        expected = status(label + '-error', 'MESSAGE')
        require('RESULT=[APP returned an error]' in expected and 'TERMINAL=COMMAND' in expected and
                'RUNTIME=NONE' in expected and 'M61_ACTIVE=0' in expected and 'DIRTY=0' in expected,
                'Not the known returned error dialog')
        control(b'\x1e', 'error-raw-mode')
        require('TERMINAL=RAW' in status(label + '-error-raw', 'MESSAGE'), 'Expected RAW')
        control(b'\x1b', 'error-to-browser')
        require('TERMINAL=RAW' in status(label + '-error-browser', 'BROWSER'), 'Expected RAW')
        control(b'\x1b', 'error-browser-to-calculator')
        require('TERMINAL=RAW' in status(label + '-error-closed'), 'Expected RAW')
        start = len(p.text)
        control(b'\x1f', 'error-command-mode')
        p.wait_text(b'mk61> ', start, timeout=8)
        require('TERMINAL=COMMAND' in status(label + '-error-commands'), 'Expected COMMAND')

    def create_file(name, data):
        path = DIRECTORY + '/' + name
        require(not any(e['path'].casefold() == path.casefold() for e in w.listing(DIRECTORY)), 'Existing target')
        state['owned'][path] = dict(bytes=len(data), sha256=sha(data), canonical=None)
        save()
        w.upload(path, data)
        entries = [e for e in w.listing(DIRECTORY) if e['path'].casefold() == path.casefold()]
        require(len(entries) == 1 and entries[0]['kind'] == 'file', 'Missing canonical upload')
        actual = entries[0]['path']
        require(w.read(actual) == data, 'APP upload differs')
        state['owned'][path]['canonical'] = actual
        save()
        return actual

    def remove_known(key):
        row = state['owned'][key]
        require(row['canonical'] is not None, 'Incomplete upload retained')
        data = w.read(row['canonical'])
        require(len(data) == row['bytes'] and sha(data) == row['sha256'], 'Changed owned bytes retained')
        w.remove(row['canonical'])
        del state['owned'][key]
        save()

    try:
        phase('USB_ADMISSION')
        usb = subprocess.run(['/usr/sbin/ioreg', '-a', '-l', '-r', '-c', 'IOUSBHostDevice'],
                             capture_output=True, check=True, timeout=15).stdout
        evidence('usb-before.plist', usb)
        usb_tool = load(ROOT / '.build/picocalc-fresh-sd-verifier-20261023/sd-only-v2/transport.py', '_interp_usb_admission')
        usb_tool.usb_admission(usb, UID, 18022400, PORT)
        holders = subprocess.run(['/usr/sbin/lsof', '-nP', '-t', '--', PORT], capture_output=True, timeout=10)
        evidence('lsof-before.txt', holders.stdout + holders.stderr)
        require(holders.returncode == 1 and not holders.stdout, 'Port already held')
        phase('CAPTURE_CURRENT')
        p = Port()
        w = bound.adapter.Wire(a, lambda: p).open()
        claim.update(state='INTERP002_ACTIVE', serial_port_open=True)
        a.core.atomic_json(HANDOFF, claim)
        first = status('initial')
        boots = a.core.field(first, 'BOOTS')
        a.core.assert_idle(first, 'A7483AE6')
        require('TERMINAL=COMMAND' in first, 'Require existing command mode')
        identity = w.command('identity')
        evidence('identity.txt', identity.encode())
        require('UID=' + UID in identity, 'Wrong UID')
        evidence('crash.txt', w.command('crash show').encode())
        before = capture('calculator-before')
        initial_settings = settings(first)
        clock_before = clock_sample()
        require(all(' OFF ONCE ' in line for line in canonical('alarm', before['alarm']).splitlines()),
                'Active alarms require separate handling')
        root_before = w.listing('/')
        a.core.atomic_json(OUT / 'root-before.json', root_before)
        require(not any(e['path'].rstrip(' .').casefold() == DIRECTORY.casefold() for e in root_before),
                'Owned namespace collision')
        w.mkdir(DIRECTORY)
        state['directory_created'] = True
        save()
        for variant, app in bound.apps.items():
            phase('UPLOAD_' + variant.upper())
            data = Path(app['path']).read_bytes()
            require(sha(data) == app['sha256'], 'Frozen APP changed')
            target = create_file(app['name'] + '.APP', data)
            status(variant + '-before')
            phase('MEASURE_' + variant.upper())
            start = len(w.raw)
            w.run_app(target)
            exchange = w.raw[start:]
            evidence(variant + '-run.bin', exchange)
            require(isinstance(w.app_start,int) and start <= w.app_start <= len(w.raw), 'Missing fresh APP boundary')
            exchange = w.raw[w.app_start:]
            evidence(variant + '-fresh-run.bin', exchange)
            code = run_admission.validate(exchange, target, data, first, correlated_reply, canonical, (0,), framed=True)
            state['observed_app_flow_result'] = code
            save()
            result = cdc_result.parse(exchange, variant)
            evidence(variant + '-RESULT.bin', result)
            decoded = bound.decoder.decode(result, variant=variant, physical=True)
            a.core.atomic_json(OUT / (variant + '-decoded.json'), decoded)
            state['completed'].append(variant)
            state['physical_measurement'] = True
            save()
            print('RESULT ' + variant + ': ' + str(decoded['rows']) + ' rows PASS', flush=True)
            leave_viewer(variant)
            current = capture(variant + '-calculator-after')
            require(current == before, 'Calculator changed after ' + variant)
            require(settings(status(variant + '-verified')) == initial_settings, 'Settings changed')
        state['measurement_complete'] = len(state['completed']) == 4
    except BaseException as error:
        state['failures'].append(dict(stage=state.get('stage'), error=repr(error)))
        print('FAIL ' + repr(error), flush=True)
    finally:
        if w is not None:
            def finish(label, operation):
                try:
                    operation()
                    state[label] = True
                except BaseException as error:
                    state['failures'].append(dict(stage=label, error=repr(error)))
                save()

            if not w.command_ready:
                finish('passive_return_recovery', lambda: w.recover_command_channel(5))
            if w.command_ready:
                def foreground_recovery():
                    observed = w.status()
                    evidence('finally-foreground.txt', observed.encode())
                    a.frames.assert_observed_status_faults(w.raw)
                    a.core.assert_health(observed, 'A7483AE6', 'C0A51996', 754344)
                    require(boots is not None and a.core.field(observed, 'BOOTS') == boots,
                            'Unadmitted foreground or reboot')
                    require(re.search(r'\bUSB_SCREEN=OFF(?=\s|$)', observed) is not None and 'UI=CALCULATOR SELECT=0 VIEW=0' in observed,
                            'Unexpected USB screen or UI in finally')
                    require(initial_settings is not None and settings(observed) == initial_settings,
                            'Unexpected settings in finally')
                    require('RUN=0 BUSY=0' in observed and 'RUNTIME=NONE' in observed and
                            'M61_ACTIVE=0' in observed and 'DIRTY=0' in observed and 'USB_DISK=0' in observed,
                            'Foreground is not idle')
                    if 'SERVICE=MESSAGE ' in observed:
                        leave_error('finally')
                    elif 'SERVICE=VIEWER ' in observed:
                        leave_viewer('finally')
                    else:
                        require('SERVICE=CLOSED ' in observed and 'TERMINAL=COMMAND' in observed,
                                'Unexpected final foreground; do not send keys')
                finish('foreground_recovered', foreground_recovery)
            if w.command_ready and state.get('foreground_recovered'):
                def cleanup():
                    if not state['directory_created']:
                        return
                    entries = w.listing(DIRECTORY)
                    known = {v['canonical'] for v in state['owned'].values() if v['canonical']}
                    require(all(e['kind'] == 'file' and e['path'] in known for e in entries), 'Unknown owned-directory object')
                    for key in list(state['owned']):
                        remove_known(key)
                    require(not w.listing(DIRECTORY), 'Owned directory not empty')
                    answer = w.command('rmdir "' + DIRECTORY + '"')
                    require('ERROR' not in answer, 'rmdir failed')
                    state['directory_created'] = False
                    require(w.listing('/') == root_before, 'Root tree differs after cleanup')

                finish('owned_cleanup', cleanup)

                def final_compare():
                    final = status('final')
                    require(before is not None and capture('calculator-final') == before, 'Final calculator differs')
                    require(settings(final) == initial_settings, 'Final settings differ')
                    after = clock_sample()
                    state['final_RTC']=after['rtc']
                    state['final_settings']=settings(final)
                    state['final_IP']=a.core.field(final,'IP')
                    elapsed = (datetime.fromisoformat(after['rtc']) - datetime.fromisoformat(clock_before['rtc'])).total_seconds()
                    interval = [after['wall_before'] - clock_before['wall_after'] - 2,
                                after['wall_after'] - clock_before['wall_before'] + 2]
                    a.core.atomic_json(OUT / 'rtc-comparison.json', dict(before=clock_before, after=after,
                        elapsed_seconds=elapsed, allowed_seconds=interval))
                    require(interval[0] <= elapsed <= interval[1], 'RTC trajectory differs')

                finish('current_data_preserved', final_compare)
            finish('serial_closed', w.close)
            evidence('decoded-transcript.bin', w.raw)
        elif p is not None:
            p.close()
        state['serial_closed'] = p is None or (p.fd == -1 and p.lock_fd == -1)
        state['status'] = 'PASS_CLOSED' if state.get('measurement_complete') and not state['failures'] and state['serial_closed'] else 'FAIL_CLOSED' if state['serial_closed'] else 'FAIL_PORT_OPEN'
        save()
        current_handoff = json.loads(HANDOFF.read_bytes())
        require(current_handoff.get('owner') == OWNER, 'Unexpected handoff owner; do not overwrite')
        current_handoff.update(state='INTERP002_' + state['status'], enabled=False, hardware_window_granted=False,
            serial_port_open=not state['serial_closed'], own_FD_closed=state['serial_closed'],
            own_advisory_lock_released=state['serial_closed'], operator_process_exited=False,
            next_requested_owner='Memset M0+', receipt=str(OUT / 'receipt.json'),
            measurement_completed=state.get('measurement_complete', False), completed=state['completed'],
            current_RTC=state.get('final_RTC'), current_settings=state.get('final_settings'), current_IP=state.get('final_IP'))
        a.core.atomic_json(HANDOFF, current_handoff)
        evidence('closed-handoff-before-parent-exit.json', HANDOFF.read_bytes())
    print(json.dumps(dict(status=state['status'], completed=state['completed'], failures=state['failures'])), flush=True)
    return 0 if state['status'] == 'PASS_CLOSED' else 1


if __name__ == '__main__':
    def interrupted(signum, frame):
        raise KeyboardInterrupt('signal ' + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    raise SystemExit(main())
