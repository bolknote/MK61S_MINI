"""HOST only: immutable scope, real probe reports, cleanup and no foreign UI keys."""
import copy
import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('audio_controller', HERE / 'run_audio_check.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
RECEIPT = HERE.parent / 'cosmic-display/PIPE-V2-2483-HIL-r1/receipt.json'
SUPERVISOR = RECEIPT.with_name('supervisor.json')
SOURCE = json.loads(RECEIPT.read_text())
STATUS = SOURCE['status_after']


def make_plan(directory):
    handoff = Path(directory) / 'HOST-only-handoff.json'
    handoff.write_text(json.dumps(dict(uid=c.b.UID, expected=c.EXPECTED, lease='released',
        source_receipt=str(RECEIPT), source_receipt_sha256=c.sha(RECEIPT),
        supervisor=str(SUPERVISOR), supervisor_sha256=c.sha(SUPERVISOR), native_binding=SOURCE['native_binding'])))
    app = HERE / 'build/SPAUDCHK.APP'
    return dict(readiness='fresh_handoff_verified', role='spectrum-audio-check', uid=c.b.UID,
        folder=c.FOLDER, indexes=[0], expected=c.EXPECTED, sequence=c.SEQUENCE,
        files={c.NAME: dict(local=str(app), sha256=c.sha(app))},
        handoff=dict(local=str(handoff), sha256=c.sha(handoff)),
        pins={str(path): c.sha(path) for path in (app, handoff, RECEIPT, SUPERVISOR)})


def report(master=10):
    amplitude = 16384 * master * 100 // 512000
    raw = f'SPAUD result=1 master={master} mute={int(master == 0)} calls=212500 pwm_en=1 pins=4/4 closed=1\n'
    for i in range(5):
        left = (128 - amplitude, 128 + amplitude) if i in (1, 3) else (128, 128)
        right = (128 - amplitude, 128 + amplitude) if i in (2, 3) else (128, 128)
        raw += f'SPPWM phase={i} count=1000 L={left[0]}/{left[1]} R={right[0]}/{right[1]}\n'
    return raw.encode()


class Checks(unittest.TestCase):
    def test_volume_zero_is_a_valid_muted_result_and_not_audibility(self):
        for master in range(11):
            result = c.parse_report(report(master))
            self.assertEqual(result['master'], master)
            self.assertEqual(result['muted'], master == 0)
            self.assertIn('requires human', result['output'])

    def test_missing_duplicate_wrong_pins_stopped_pwm_and_wrong_stereo_fail(self):
        raw = report()
        phase = re.search(rb'SPPWM phase=1[^\n]+\n', raw)[0]
        for bad in (b'', raw + raw, raw.replace(phase, b''), raw + phase,
                    raw.replace(b'pwm_en=1', b'pwm_en=0'), raw.replace(b'pins=4/4', b'pins=5/4'),
                    raw.replace(b'closed=1', b'closed=0'), raw.replace(b'calls=212500', b'calls=100000'),
                    raw.replace(b'L=96/160 R=128/128', b'L=128/128 R=96/160', 1),
                    raw.replace(b'count=1000', b'count=0', 1)):
            with self.assertRaises(c.Hold):
                c.parse_report(bad)

    def test_plan_rejects_draft_or_changed_scope_before_any_device_io(self):
        with tempfile.TemporaryDirectory() as directory:
            good = make_plan(directory)
            c.validate_plan(good)
            for key in ('readiness', 'expected', 'sequence', 'files', 'uid', 'pins'):
                bad = copy.deepcopy(good)
                if key == 'readiness':
                    bad[key] = 'draft_no_GO'
                elif key == 'expected':
                    bad[key]['build'] = '00000000'
                elif key == 'sequence':
                    bad[key]['volume'] = 50
                elif key == 'files':
                    bad[key]['SPECTRUM.APP'] = bad[key][c.NAME]
                elif key == 'uid':
                    bad[key] = '0000000000000000'
                else:
                    bad[key][bad['files'][c.NAME]['local']] = '0' * 64
                with patch.object(c.b.SpectrumGate, 'native', side_effect=AssertionError('No device I/O')):
                    with self.assertRaises(c.Hold):
                        c.validate_plan(bad)

    def test_cleanup_only_diagnostic_without_state_backup(self):
        commands = []
        class Port:
            def command(self, line):
                commands.append(line)
                return 'f\t16384\t48.rom\nf\t33471\tSPECTRUM.APP\n' if line.startswith('ls ') else 'OK'
        self.assertEqual(c.cleanup_file(Port(), {c.NAME}), [c.NAME])
        with self.assertRaises(c.Hold):
            c.cleanup_file(Port(), {'SPECTRUM.APP'})
        self.assertEqual(commands, [f'rm "{c.FOLDER}/{c.NAME}"', f'ls "{c.FOLDER}"'])

    def test_foreign_and_running_diagnostic_receive_no_escape(self):
        for path, running in (('/foreign.APP', False), (c.FOLDER + '/SPECTRUM.APP', False),
                              (c.FOLDER + '/' + c.NAME, True)):
            class Port:
                def status(self):
                    value = re.sub(r'(?m)^SERVICE=[^\r\n]*', 'SERVICE=VIEWER SOURCE=0 DIRTY=0 PATH=[' + path + '] RESULT=[APP finished; Enter]', STATUS)
                    return value.replace('RUNTIME=NONE', 'RUNTIME=APP') if running else value
                def send(self, value):
                    self.sent.append(value)
                def wire(self, value):
                    self.sent.append(value)
                def pump(self, seconds):
                    pass
            port = Port()
            port.sent = []
            with self.assertRaises(c.Hold):
                c.AudioPort.native_return(port, 0)
            self.assertEqual(port.sent, [])

    def test_full_controller_one_temp_and_no_ordinary_app_or_settings_write(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = make_plan(directory)
            files = {'48.rom': b'rom', 'SPECTRUM.APP': b'old', 'unrelated.trd': b'untouched'}
            commands, opens = [], []
            class Port:
                def __init__(self, gate):
                    self.gate = gate
                    self.binding = SOURCE['native_binding']
                    self.text = bytearray()
                def __enter__(self):
                    self.gate.final['native_binding'] = self.binding
                    return self
                def __exit__(self, *args):
                    self.gate.final.update(cdc_descriptor_closed=True, port_close_errors=[])
                def status(self):
                    return STATUS
                def commands(self):
                    pass
                def command(self, line):
                    commands.append(line)
                    if line == 'identity':
                        return 'UID=' + c.b.UID
                    if line == 'prof heap':
                        return 'HEAP_FREE=103488 HEAP_FREE_BLOCKS=2 HEAP_TOP=100000'
                    if line == 'fsput cancel':
                        return 'OK'
                    if line.startswith('ls '):
                        return ''.join('f\t10\t' + name + '\n' for name in files)
                    name = line.rsplit('/', 1)[-1][:-1]
                    if line.startswith('rm '):
                        files.pop(name)
                        return 'OK'
                    raise AssertionError('Unexpected command: ' + line)
                def open_app(self, name):
                    opens.append(name)
                    self.text.extend(report())
                def match(self, *args, **kwargs):
                    pass
                def native_return(self, physical):
                    return STATUS
            class Gate:
                def cleanup(self):
                    pass
                def noholders(self, binding):
                    self.holders_checked = True
            gate = Gate()
            gate.j, gate.final, gate.out = plan, {}, Path(directory)
            def write(port, path, data):
                name = path.rsplit('/', 1)[-1]
                self.assertEqual(name, c.NAME)
                files[name] = data
            with patch.object(c, 'AudioPort', Port), patch.object(c.b, 'write_file', side_effect=write):
                c.run(gate)
            self.assertEqual(opens, [c.NAME])
            self.assertEqual(files, {'48.rom': b'rom', 'SPECTRUM.APP': b'old', 'unrelated.trd': b'untouched'})
            self.assertEqual(gate.final['lease'], 'released')
            self.assertTrue(gate.holders_checked)
            self.assertFalse(gate.final['previous_state_backup'])
            self.assertFalse(gate.final['previous_state_restoration'])
            self.assertFalse(any(command.split()[0] in {'clock', 'reg', 'stk', 'hout', 'alarm', 'pwd', 'reset', 'dfu'} for command in commands))

    def test_report_failure_still_cleans_up_and_releases(self):
        gate = type('Gate', (), {'final': dict(cdc_descriptor_closed=True, port_close_errors=[],
                    native_binding={}, cleanup_native_verified=True), 'noholders': lambda self, binding: None})()
        with patch.object(c, 'run_port', side_effect=c.Hold('PWM mismatch')):
            with self.assertRaises(c.Hold):
                c.run(gate)
        self.assertEqual(gate.final['lease'], 'released')


if __name__ == '__main__':
    unittest.main()
