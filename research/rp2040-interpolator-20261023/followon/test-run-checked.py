#!/usr/bin/env python3
"""Actual-envelope regression plus stop-before-next-key negative replays."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import re
from types import SimpleNamespace

ROOT = Path('/Users/bolk/Projects/MK61S_MINI')
HERE = Path(__file__).resolve().parent
BUILD = ROOT / '.build/rp2040-interpolator-20261023'
OUT = BUILD / 'followon/cdc-output-checked'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    runner = load(HERE / 'run-cdc-checked.py', '_cdc_v2_regression_runner')
    admission = load(HERE / 'run-admission.py', '_cdc_v2_admission')
    original = BUILD / 'hardware-INTERP002'
    first = (original / 'initial.txt').read_text()
    actual = (original / 'lookup-run.bin').read_bytes()
    old_app = (BUILD / 'followon/apps/lookup/FLOOK.APP').read_bytes()
    target = '/INTRP02/FLOOK.APP'
    call = lambda raw, app=old_app, framed=False: admission.validate(
        raw, target, app, first, runner.correlated_reply, runner.canonical, (0, 4), framed=framed)
    assert call(actual) == 4
    app = (BUILD / 'followon/cdc-output/apps/lookup/FLOOK.APP').read_bytes()
    synthetic = (BUILD / 'followon/cdc-output/protocol/lookup-exchange.bin').read_bytes()
    crc = int.from_bytes(app[52:56], 'little')
    memory = int.from_bytes(app[32:36], 'little')
    synthetic = synthetic.replace(b'open "FLOOK.APP"', b'open "/INTRP02/FLOOK.APP"')
    synthetic = synthetic.replace(b'APP_RESULT=0\r\n', f'APP_RESULT=0 CRC={crc:08X} MEMORY={memory}\r\n'.encode())
    assert call(synthetic, app, framed=True) == 0
    bad = [
        b'open "/INTRP02/FLOOK.APP"\r\nAPP_FLOW_RESULT=4\r\nERROR\r\nmk61> ',
        actual.replace(b'APP_RESULT=0', b'APP_RESULT=5'),
        actual.replace(b'CRC=E49681C1', b'CRC=00000000'),
        actual.replace(b'MEMORY=23268', b'MEMORY=1'),
        actual.replace(b'APP_FLOW_RESULT=4', b'APP_FLOW_RESULT=4\r\nAPP_FLOW_RESULT=4'),
        actual.replace(b'FLOOK.APP', b'OTHER.APP'),
        actual.replace(b'\r\nERROR', b''),
        actual.replace(b'\r\nmk61> ', b'\r\nmk61> \r\nmk61> '),
        actual.replace(b'APP_FLOW_RESULT=4', b'CRASH=HARDFAULT\r\nAPP_FLOW_RESULT=4'),
        b'UNRELATED\r\n' + actual,
        synthetic,
    ]
    for raw in bad:
        try:
            call(raw)
        except RuntimeError:
            pass
        else:
            raise AssertionError('Accepted an incomplete or contradictory APP envelope')

    binding = runner.load(runner.PACKET / 'source/bind.py', '_cdc_v2_test_binding')
    bound = binding.BoundSet(runner.PACKET, runner.PACKET_SHA)
    tree = ast.parse((HERE / 'run-cdc-checked.py').read_bytes())
    main_fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    methods = [next(n for n in main_fn.body if isinstance(n, ast.FunctionDef) and n.name == name)
               for name in ('status', 'leave_error')]
    factory = ast.parse('def make_chain(w,p,a,control,evidence,boots,initial_settings):\n return leave_error\n')
    factory.body[0].body[:0] = methods
    ast.fix_missing_locations(factory)
    namespace = dict(runner.__dict__)
    exec(compile(factory, '<exact-v2-status-and-error-chain>', 'exec'), namespace)
    baseline = (original / 'final.txt').read_text()

    def replay(stage=None, field=None):
        states = []
        for mode, service in [('COMMAND', 'MESSAGE'), ('RAW', 'MESSAGE'), ('RAW', 'BROWSER'), ('RAW', 'CLOSED'), ('COMMAND', 'CLOSED')]:
            s = baseline.replace('TERMINAL=COMMAND', 'TERMINAL=' + mode).replace('SERVICE=MESSAGE ', 'SERVICE=' + service + ' ')
            states.append(s)
        if stage is not None:
            old, new = field
            assert old in states[stage]
            states[stage] = states[stage].replace(old, new)
        sent = []

        class Wire:
            raw = b''

            def status(self):
                value = states.pop(0)
                self.raw += value.encode()
                return value

        class Port:
            text = bytearray()

            def wait_text(self, expected, start, timeout):
                assert expected in self.text[start:]

        p = Port()

        def control(value, label):
            sent.append(value)
            if value == b'\x1f':
                p.text.extend(b'\r\nmk61> ')

        chain = namespace['make_chain'](Wire(), p, bound.accepted, control, lambda *args: None, 3, runner.settings(baseline))
        error = None
        try:
            chain('test')
        except RuntimeError as caught:
            error = str(caught)
        if stage is None:
            assert error is None and sent == [b'\x1e', b'\x1b', b'\x1b', b'\x1f']
        else:
            assert error and len(sent) == stage, (stage, field, sent, error)
        return dict(stage=stage, field=None if field is None else field[0], control_bytes=len(sent), stopped=bool(error))

    normal = replay()
    drift = [replay(stage, field) for stage in range(1, 5)
             for field in [('RUNTIME=NONE', 'RUNTIME=APP'), ('M61_ACTIVE=0', 'M61_ACTIVE=1'), ('DIRTY=0', 'DIRTY=1'), ('USB_SCREEN=OFF', 'USB_SCREEN=ON'),
                           ('UI=CALCULATOR', 'UI=MENU')]]
    report = dict(status='PASS', physical_device_access=False,
                  actual_failed_envelope_sha256=hashlib.sha256(actual).hexdigest(),
                  actual_envelopes_accepted=1, synthetic_cdc_load_envelopes_accepted=1,
                  malformed_envelopes_rejected=len(bad), normal_control_chain=normal,
                  post_control_drift_cases=drift)
    (OUT / 'admission-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
