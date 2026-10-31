#!/usr/bin/env python3
"""Focused join tests; do not repeat the already qualified numerical matrix."""
import argparse
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.dont_write_bytecode = True
import bind as B


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--packet', type=Path)
    parser.add_argument('--manifest-sha')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    bound = B.BoundSet(args.packet, args.manifest_sha)
    adapter = bound.adapter
    original_selector = adapter.verified_apps
    constructor_calls = []

    def forbidden_selector():
        raise AssertionError('The old V2 APP selector was called')

    adapter.verified_apps = forbidden_selector
    good = (bound.accepted.library / 'review/status-fixtures/completion-fresh-status.txt').read_text()
    fixtures = {v: (bound.math / 'protocol' / v / 'synthetic-result.bin').read_bytes() for v in bound.apps}
    decoder_checks = []
    for variant in bound.apps:
        report = bound.admit(fixtures[variant], variant, 2, 4)
        assert report['status'] == 'PASS' and not report['hardware_verified']
        assert not any('net' in key for row in report['results'] for rr in row['rounds'] for key in rr)
        other = next(v for v in bound.apps if v != variant)
        old = (B.BUILD / 'packet-v2/protocol' / variant / 'synthetic-result.bin').read_bytes()
        for kind, raw in (('V2_schema', old), ('wrong_variant', fixtures[other])):
            try:
                bound.admit(raw, variant, 2, 4)
            except AssertionError:
                decoder_checks.append(dict(variant=variant, rejected=kind))
            else:
                raise AssertionError(('Cross-binding admitted', variant, kind))

    class Preservation:
        def __init__(self):
            self.calc = b'original hidden state: FAKE provider'
            self.env = dict(rtc_set=0)

        def capture_full(self, wire):
            return dict(data=self.calc, coverage=sorted(adapter.FULL_FIELDS), fresh=True, uid=adapter.UID, build=adapter.BUILD)

        def capture_environment(self, wire):
            return copy.deepcopy(self.env)

        def capture_all_sd(self, wire):
            return dict(fresh=True, complete=True, includes_hidden_and_large=True, uid=adapter.UID,
                        build=adapter.BUILD, files={name: adapter.sha(data) for name, data in wire.files.items()})

        def verify_all_sd(self, wire, before):
            assert {name: adapter.sha(data) for name, data in wire.files.items()} == before['files'] and not wire.created

        def restore_environment(self, wire, before):
            self.env = copy.deepcopy(before)

        def verify_environment(self, wire, before):
            assert self.env == before

        def restore_full(self, wire, before):
            self.calc = before['data']

        def verify_full(self, wire, before):
            assert self.calc == before['data']

    class FakeWire:
        """Only the reviewed Lifecycle and new mapping/admission are exercised."""
        def __init__(self, fault, preservation):
            self.fault = fault
            self.preservation = preservation
            self.files = {'/USER.bin': b'original user bytes'}
            self.created = False
            self.command_ready = True
            self.closed = False
            self.text = bytearray()
            self.opened_variants = []

        @property
        def raw(self):
            return bytes(self.text)

        @property
        def passive_raw(self):
            return b'FAKE hardware; no physical receive'

        def guard(self):
            assert self.command_ready, 'Attempted command before APP return'

        def open(self):
            return self

        def status(self):
            self.guard()
            self.text.extend(good.encode())
            return good

        def command(self, text, timeout=30):
            self.guard()
            assert text in ('identity', 'crash show')
            return 'UID=' + adapter.UID if text == 'identity' else 'CRASH=NONE'

        def listing(self, path):
            self.guard()
            entries = [dict(path=n, kind='file', bytes=len(data)) for n, data in self.files.items()
                       if str(Path(n).parent) == path]
            if path == '/' and self.created:
                entries.append(dict(path=adapter.DIRECTORY, kind='directory', bytes=None))
            return entries

        def mkdir(self, path):
            self.guard()
            assert path == adapter.DIRECTORY and not self.created
            self.created = True

        def upload(self, path, data):
            self.guard()
            if path.endswith('.APP'):
                path = path[:-4] + '.app'
            assert path not in self.files
            self.files[path] = data

        def read(self, path):
            self.guard()
            return self.files[path]

        def remove(self, path):
            self.guard()
            if path in self.files:
                del self.files[path]
            else:
                assert path == adapter.DIRECTORY and not any(n.startswith(path + '/') for n in self.files)
                self.created = False

        def run_app(self, path):
            self.guard()
            variant = next(v for v, app in bound.apps.items() if Path(path).stem == app['name'])
            assert self.files[path] == Path(bound.apps[variant]['path']).read_bytes()
            self.opened_variants.append(variant)
            self.preservation.calc = b'changed mock hidden state'
            self.preservation.env['rtc_set'] = 1
            self.command_ready = False
            if self.fault == 'no_return':
                raise TimeoutError('Mock bound V3 APP did not return')
            self.command_ready = True
            data = fixtures[variant]
            if self.fault == 'old_schema':
                data = (B.BUILD / 'packet-v2/protocol' / variant / 'synthetic-result.bin').read_bytes()
            elif self.fault == 'wrong_variant':
                data = fixtures[next(v for v in fixtures if v != variant)]
            self.files[adapter.DIRECTORY + '/RESULT.bin'] = data
            self.text.extend(b'APP_FLOW_RESULT=0\r\nmk61> ')

        def recover_command_channel(self):
            self.guard()

        def close(self):
            self.closed = True

    lifecycle_cases = []
    for fault in ('normal', 'old_schema', 'wrong_variant', 'no_return'):
        preservation = Preservation()
        wire = FakeWire(fault, preservation)
        life = adapter.Lifecycle(bound.accepted, wire, preservation, output / fault, bound.apps,
                                 lambda raw, variant: bound.admit(raw, variant, 2, 4))
        result = life.execute()
        assert wire.closed and result['serial_closed']
        assert wire.files['/USER.bin'] == b'original user bytes'
        if fault == 'normal':
            assert result['status'] == 'PASS' and result['completed'] == list(bound.apps)
            assert wire.opened_variants == list(bound.apps)
        else:
            assert result['status'] == 'HOLD' and result['primary_failure']
        if fault == 'no_return':
            assert result['manual_recovery_required'] and result['pending_restoration']
            assert not result.get('calculator_restored') and wire.created
        else:
            assert result['calculator_verified'] and result['environment_final_verified']
            assert preservation.calc == b'original hidden state: FAKE provider'
            assert preservation.env['rtc_set'] == 0 and not wire.created
        lifecycle_cases.append(dict(case=fault, status=result['status'], variants=wire.opened_variants,
                                    serial_closed=True, pending_restoration=result.get('pending_restoration', [])))
        print('PASS bound lifecycle', fault, flush=True)

    cli_cases = []
    screen = sys.modules['hil_portable_apps'].ScreenPort
    def forbidden_constructor(*args, **kwargs):
        constructor_calls.append(True)
        raise AssertionError('Hardware constructor called')
    for name, values in (('null', {}), ('labels_only', {key: 'label is not an implementation' for key in B.PROVIDERS})):
        path = output / (name + '.json')
        path.write_text(json.dumps(values))
        argv = ['bind.py', '--hardware', '--bindings', str(path)]
        if args.packet:
            argv += ['--packet', str(args.packet), '--manifest-sha', args.manifest_sha]
        stream = io.StringIO()
        with patch.object(sys, 'argv', argv), patch.object(screen, '__init__', forbidden_constructor), contextlib.redirect_stdout(stream):
            try:
                B.main()
            except SystemExit as error:
                assert error.code == 2
            else:
                raise AssertionError('Hardware CLI did not remain HELD')
        reply = json.loads(stream.getvalue())
        assert not reply['port_constructed'] and not reply['hardware_enabled'] and not constructor_calls
        cli_cases.append(dict(case=name, status=reply['status'], exit_code=2, hardware_constructors=0))
    assert adapter.PACKET_SHA == B.V2_SHA
    adapter.verified_apps = original_selector
    rejection_checks = []
    for name, operation in (
        ('wrong_manifest_pin', lambda: B.verified_manifest(bound.math, 'packet-manifest.json', '0' * 64)),
        ('wrong_receipt_pin', lambda: B.verified_review(bound.math_review_root, '0' * 64, B.MATH_SHA, 'bad')),
        ('receipt_for_wrong_candidate', lambda: B.verified_review(bound.math_review_root, B.MATH_REVIEW_SHA, B.ADAPTER_SHA,
                                                                'TECHNICAL_GO_FOCUSED_OFFLINE_INTERP_V3_DELTA')),
    ):
        try:
            operation()
        except RuntimeError:
            rejection_checks.append(name)
        else:
            raise AssertionError('Invalid binding admitted: ' + name)
    report = dict(status='PASS_FOCUSED_OFFLINE_BINDING', hardware_verified=False, hardware_constructor_calls=0,
                  math_manifest_sha256=B.MATH_SHA, adapter_manifest_sha256=B.ADAPTER_SHA,
                  mathematical_matrix_repeated=False, adapter_legacy_selector_called=False,
                  decoder_negative_cases=decoder_checks, lifecycle_cases=lifecycle_cases,
                  cli_hold_cases=cli_cases, pin_rejection_cases=rejection_checks,
                  source_sha256={name: B.sha(Path(__file__).parent / name) for name in ('bind.py', 'test_binding.py', 'bindings.template.json')},
                  scope='Actual reviewed Lifecycle + explicit new V3 descriptors/decoder. Hardware/wire/provider doubles only test the join; previous ARM/transport reviews are referenced unchanged, not reclassified as physical results.')
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(status=report['status'], decoder_negatives=len(decoder_checks), lifecycle_cases=4,
                         cli_hold_cases=2, pin_rejections=3, hardware_verified=False), indent=2))


if __name__ == '__main__':
    main()
