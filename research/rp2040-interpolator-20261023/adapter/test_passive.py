#!/usr/bin/env python3
"""Actual accepted APP open/wait/frame/close with a receive-only pump and OS fakes."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch

import lifecycle as L

CAPS = bytes.fromhex('00054d5302120101021002c003400801010103012801010101010366ef00')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    accepted = L.Accepted()
    port_type = L.accepted_port_type(accepted)
    apps = L.verified_apps()
    fixture = accepted.library / 'review/status-fixtures/completion-fresh-status.txt'
    good = fixture.read_text()
    source_hashes = {name: L.sha(Path(__file__).parent.joinpath(name).read_bytes())
                     for name in ('lifecycle.py', 'test_passive.py')}
    records = []
    for case in ('late_caps_no_return', 'already_attached_no_return', 'late_caps_fresh_return'):
        # Dummy descriptors only. Constructors never discover/open hardware.
        port = port_type.__new__(port_type)
        port.path = '<offline>'
        port.fd = 101
        port.lock_fd = 102
        port.text = bytearray()
        port.attached = case == 'already_attached_no_return'
        port.packet = None
        port.frames = []
        port.sequence = 0
        port.next_ping = 0
        port.caps = port.pending = None
        port.pages = set()
        port.keyboard_layout = 1
        port.native_display = False
        original_close, original_read, original_write = L.os.close, L.os.read, L.os.write

        class OS:
            def __init__(self):
                self.clock = 0
                self.tx = []
                self.rx = []
                self.closed = []
                self.after_open = None
                self.timeouts = []

            def now(self):
                self.clock += .001
                return self.clock

            def select(self, read, write, error, timeout):
                return ([101] if read and self.rx else [], list(write), [])

            def read(self, fd, size):
                return self.rx.pop(0) if fd == 101 else original_read(fd, size)

            def write(self, fd, data):
                if fd != 101:
                    return original_write(fd, data)
                self.tx.append(bytes(data))
                if data.startswith(b'open '):
                    self.after_open = len(self.tx)
                    self.rx.extend((CAPS[:11], CAPS[11:]))
                    if case == 'late_caps_fresh_return':
                        self.rx.append(b'APP_FLOW_RESULT=0\r\nmk61> ')
                return len(data)

            def close(self, fd):
                if fd in (101, 102):
                    self.closed.append(fd)
                else:
                    original_close(fd)

        model = OS()
        actual_wait = port.wait_text

        def bounded_wait(expected, start, timeout):
            model.timeouts.append(timeout)
            return actual_wait(expected, start, timeout=1)

        port.wait_text = bounded_wait

        class SetupWire(L.Wire):
            """Preflight/files are modelled; APP open/wait/pump/close are actual."""
            def __init__(self):
                super().__init__(accepted, lambda: port)
                self.files = {}
                self.created = False
                self.commands = []
                self.commands_at_open = None

            def status(self):
                self.require_command_channel()
                port.text.extend(good.encode())
                return good

            def command(self, text, timeout=30):
                self.require_command_channel()
                self.commands.append(text)
                assert text in ('identity', 'crash show')
                return 'UID=' + L.UID if text == 'identity' else 'CRASH=NONE'

            def listing(self, path):
                self.require_command_channel()
                if path == '/':
                    return [dict(path=L.DIRECTORY, kind='directory', bytes=None)] if self.created else []
                assert path == L.DIRECTORY
                return [dict(path=name, kind='file', bytes=len(data)) for name, data in self.files.items()]

            def mkdir(self, path):
                self.require_command_channel()
                assert path == L.DIRECTORY and not self.created
                self.created = True

            def upload(self, path, data):
                self.require_command_channel()
                assert path not in self.files
                self.files[path] = data

            def read(self, path):
                self.require_command_channel()
                return self.files[path]

            def run_app(self, path):
                self.commands_at_open = len(self.commands)
                return super().run_app(path)

        class Preservation:
            def __init__(self):
                self.restores = []

            def capture_full(self, wire):
                return dict(coverage=sorted(L.FULL_FIELDS), fresh=True, uid=L.UID, build=L.BUILD, data=b'original complete mock snapshot')

            def capture_environment(self, wire):
                return dict(mock=True, rtc_set=0)

            def capture_all_sd(self, wire):
                return dict(fresh=True, complete=True, includes_hidden_and_large=True, uid=L.UID, build=L.BUILD)

            def restore_full(self, wire, before):
                self.restores.append('full')

            def restore_environment(self, wire, before):
                self.restores.append('environment')

        wire = SetupWire()
        preservation = Preservation()
        with patch('time.monotonic', model.now), patch('select.select', model.select), \
             patch('os.read', model.read), patch('os.write', model.write), patch('os.close', model.close), \
             patch('fcntl.ioctl', lambda *args: None), patch('fcntl.flock', lambda *args: None):
            if case == 'late_caps_fresh_return':
                wire.open()
                wire.run_app('/INTRP01/IALU.app')
                assert wire.command_ready
                wire.close()
                result = dict(status='RETURN_ACKNOWLEDGED_ONLY', command_channel_available=True,
                              manual_recovery_required=False, serial_closed=True)
            else:
                life = L.Lifecycle(accepted, wire, preservation, output / case, {'alu': apps['alu']},
                                   lambda *args: (_ for _ in ()).throw(AssertionError('Unexpected result admission')))
                result = life.execute()
                assert result['status'] == 'HOLD' and result['primary_failure']
                assert not result['command_channel_available'] and result['manual_recovery_required']
                assert result['pending_restoration'] and not preservation.restores
                assert result['serial_closed'] and not result.get('calculator_restored')
                assert len(wire.commands) == wire.commands_at_open
                assert (output / case / 'calculator-before.bin').read_bytes() == b'original complete mock snapshot'
                assert (output / case / 'passive-wire.bin').read_bytes() == CAPS
                assert wire.files and wire.created, 'Unreturned APP ownership was falsely reported as cleaned up'
                assert model.clock > .7, 'Did not cross the old keepalive threshold'
            assert port.attached and port.caps is not None, 'Actual valid CAPS decoder did not run'
            assert wire.passive_raw.startswith(CAPS)
            assert model.after_open is not None and not model.tx[model.after_open:]
            assert port.fd == port.lock_fd == -1 and model.closed == [101, 102]
        records.append(dict(case=case, status=result['status'], valid_CAPS_decoded=True,
                            command_channel_available=result['command_channel_available'],
                            manual_recovery_required=result['manual_recovery_required'],
                            post_open_tx=[], closed_descriptors=model.closed, passive_wait_requests=model.timeouts,
                            virtual_elapsed_seconds=model.clock))
        print('PASS', case, flush=True)
    report = dict(status='PASS_OFFLINE', hardware_accessed=False, hardware_constructor_called=False,
                  source_sha256=source_hashes, incoming_CAPS_hex=CAPS.hex(), cases=records,
                  transport_reference_sha256=L.REFERENCE_SHA,
                  scope='Actual accepted open/wait/frame decoder/serial close plus adapter receive-only pump and lifecycle finally. OS descriptors/clock and preflight/files/preservation are explicit fakes; no complete hardware provider is demonstrated.')
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(status=report['status'], cases=len(records), post_open_TX=0, hardware_accessed=False), indent=2))


if __name__ == '__main__':
    main()
