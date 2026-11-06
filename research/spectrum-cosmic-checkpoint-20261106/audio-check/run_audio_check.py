"""One reviewed stereo/PWM diagnostic. Importing performs no device I/O."""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT / '.build/spectrum-hardware-tests/run-20261105'), str(HERE.parent / 'cosmic-display')]
import xip_named_run_v3 as b
import local_holders

need, Hold, sha = b.need, b.Hold, b.sha
FOLDER, NAME = b.FOLDER, 'SPAUDCHK.APP'
EXPECTED = {'build': '2483E8A7', 'crc': '22F8ED32', 'bytes': 1537040}
SEQUENCE = {'rate': 25000, 'volume': 100, 'pcm_amplitude': 16384,
            'silence_start_samples': 50000, 'left_samples': 50000,
            'right_samples': 50000, 'both_samples': 50000, 'silence_end_samples': 12500,
            'app_deadline_us': 12000000, 'marker_deadline_seconds': 20}


def source_pins():
    return {**b.source_pins(), str(Path(local_holders.__file__).resolve()): sha(local_holders.__file__),
            str(Path(__file__).resolve()): sha(__file__)}


def pinned(plan, item):
    need(sha(item['local']) == item['sha256'] == plan['pins'][item['local']], 'Changed pinned diagnostic input')


def validate_plan(plan):
    need(plan.get('readiness') == 'fresh_handoff_verified', 'No fresh supplier handoff')
    need(plan['role'] == 'spectrum-audio-check' and plan['uid'] == b.UID and plan['folder'] == FOLDER,
         'Changed device or namespace')
    need(plan['indexes'] == [0] and plan['expected'] == EXPECTED and plan['sequence'] == SEQUENCE,
         'Changed firmware or bounded audio sequence')
    need(set(plan['files']) == {NAME}, 'Changed writable file set')
    pinned(plan, plan['files'][NAME])
    need(0 < Path(plan['files'][NAME]['local']).stat().st_size < 4096, 'Unexpected diagnostic size')
    pinned(plan, plan['handoff'])
    handoff = json.loads(Path(plan['handoff']['local']).read_text())
    need(handoff['uid'] == b.UID and handoff['expected'] == EXPECTED and handoff['lease'] == 'released',
         'Wrong supplier identity or lease')
    for key in ('source_receipt', 'supervisor'):
        item = {'local': handoff[key], 'sha256': handoff[key + '_sha256']}
        pinned(plan, item)
    receipt = json.loads(Path(handoff['source_receipt']).read_text())
    need(receipt['status'] == 'PASS' and receipt['lease'] == 'released' and receipt['uid'] == b.UID
         and receipt['cleanup_native_verified'] and receipt['cdc_descriptor_closed']
         and not receipt['port_close_errors'] and receipt['native_binding'] == handoff['native_binding'],
         'Supplier cleanup not proved')
    need(receipt['cdc_sessions'] and all(row['closed'] and not row['errors'] for row in receipt['cdc_sessions']),
         'Supplier descriptor closure incomplete')
    last = receipt['holder_checks'][-1]
    need(not last['allow_self'] and {row['path'] for row in last['paths']} ==
         {handoff['native_binding'][key] for key in ('cu', 'tty')}
         and all(not row['pids'] for row in last['paths']), 'Supplier holder proof incomplete')
    supervisor = json.loads(Path(handoff['supervisor']).read_text())
    need(supervisor == {'child_pid': receipt['pid'], 'reaped': True, 'exit_code': 0, 'timed_out': False},
         'Supplier child not reaped successfully')
    b.guard_status(receipt['status_after'], EXPECTED, 0)


def parse_report(raw):
    rows = re.findall(rb'(?m)^SPAUD result=(\d+) master=(\d+) mute=(\d+) calls=(\d+) pwm_en=(\d+) pins=(\d+)/(\d+) closed=(\d+)\r?$', raw)
    need(len(rows) == 1, 'Missing or duplicate audio result')
    ok, master, mute, calls, enabled, left, right, closed = map(int, rows[0])
    need(ok == enabled == closed == 1 and left == right == 4 and 0 <= master <= 10 and mute == (master == 0)
         and 212500 <= calls <= 225000, 'Audio callback/PWM/lifecycle failure')
    rows = re.findall(rb'(?m)^SPPWM phase=(\d+) count=(\d+) L=(\d+)/(\d+) R=(\d+)/(\d+)\r?$', raw)
    need(len(rows) == 5, 'Missing or duplicate PWM phase')
    phases = []
    amplitude = 16384 * master * 100 // 512000
    for i, row in enumerate(rows):
        index, count, lo_l, hi_l, lo_r, hi_r = map(int, row)
        want_l = (128 - amplitude, 128 + amplitude) if i in (1, 3) else (128, 128)
        want_r = (128 - amplitude, 128 + amplitude) if i in (2, 3) else (128, 128)
        need(index == i and count > 0 and (lo_l, hi_l) == want_l and (lo_r, hi_r) == want_r,
             'PWM phase does not match requested stereo signal')
        phases.append(dict(index=i, count=count, left=[lo_l, hi_l], right=[lo_r, hi_r]))
    return dict(master=master, muted=bool(mute), callbacks=calls, phases=phases,
                output='PWM register extrema; speaker audibility requires human observation')


class AudioGate(b.SpectrumGate):
    def check(self):
        left = super().check()
        duration = b.elapsed(self.continuous_start, b.continuous())
        cap = min(135, self.cleanup_start + 45) if self.cleaning else 90
        need(duration < cap, 'Audio phase/cleanup cap exceeded')
        return min(left, cap - duration)

    def noholders(self, binding, allow_self=False):
        self.check()
        try:
            proof = local_holders.require_no_holders(binding, allow_self)
        except (local_holders.HolderError, OSError) as error:
            raise Hold(str(error)) from error
        self.final.setdefault('holder_checks', []).append(proof)
        self.check()


class AudioPort(b.SpectrumPort):
    def open_app(self, name):
        need(name == NAME, 'Foreign APP')
        self.pump(.02)
        self.send(('open "' + FOLDER + '/' + name + '"\r').encode())

    def native_return(self, physical):
        browser = False
        for _ in range(5):
            status = self.status()
            service, path, result = b.foreground(status)
            if service == 'CLOSED':
                b.guard_status(status, EXPECTED, physical)
                self.commands()
                return status
            if service == 'BROWSER' and browser:
                need(b.field(status, 'RUNTIME') == 'NONE', 'Unexpected browser runtime')
                self.wire(27)
                self.pump(.2)
                continue
            need(path == FOLDER + '/' + NAME, 'Foreign foreground; no escape sent')
            need(b.field(status, 'RUNTIME') == 'NONE' and service in ('VIEWER', 'BROWSER'),
                 'Diagnostic has not exited; no key abort or reset')
            if service == 'VIEWER':
                need(result.startswith('APP finished;'), 'Diagnostic did not finish normally')
            self.send(b'\x1e')
            self.wire(27)
            self.pump(.2)
            browser = True
        raise Hold('Native return exceeds finite cap')


def names(report):
    return {row.rstrip('\r').split('\t')[-1].rstrip('/') for row in report.splitlines() if re.match(r'^[df]\t', row)}


def cleanup_file(port, attempted):
    need(attempted <= {NAME}, 'Unowned cleanup target')
    if attempted:
        port.command(f'rm "{FOLDER}/{NAME}"')
    remaining = names(port.command(f'ls "{FOLDER}"'))
    need({'48.rom', 'SPECTRUM.APP'} <= remaining and not (attempted & remaining),
         'Owned namespace or cleanup not verified')
    return sorted(attempted)


def run_port(gate):
    validate_plan(gate.j)
    b.EXPECTED = EXPECTED
    attempted, changed, clean = set(), {}, False
    with AudioPort(gate) as port:
        physical = b.guard_status(port.status(), EXPECTED, 0)
        handoff = json.loads(Path(gate.j['handoff']['local']).read_text())
        need(port.binding == handoff['native_binding'], 'USB binding changed since supplier release')
        port.commands()
        need(b.field(port.command('identity'), 'UID') == b.UID, 'Wrong PicoCalc UID')
        try:
            gate.final['heap_start'] = port.command('prof heap')
            listing = names(port.command(f'ls "{FOLDER}"'))
            need({'48.rom', 'SPECTRUM.APP'} <= listing and NAME not in listing,
                 'Diagnostic filename occupied or namespace absent')
            need(int(b.field(gate.final['heap_start'], 'HEAP_TOP')) >= 8192,
                 'Insufficient free contiguous heap for diagnostic')
            item = gate.j['files'][NAME]
            attempted.add(NAME)
            b.write_file(port, FOLDER + '/' + NAME, Path(item['local']).read_bytes())
            changed[NAME] = item['sha256']
            start = len(port.text)
            port.open_app(NAME)
            port.match(rb'SPPWM phase=4 [^\r\n]+\r?\n', start, timeout=20)
            record = bytes(port.text[start:])
            (gate.out / 'audio-report.txt').write_bytes(record)
            gate.final['audio'] = parse_report(record)
            port.native_return(physical)
        except BaseException as error:
            gate.final['primary_error'] = repr(error)
            raise
        finally:
            try:
                gate.cleanup()
                port.native_return(physical)
                port.command('fsput cancel')
                gate.final['temporary_files_absent'] = cleanup_file(port, attempted)
                gate.final['heap_end'] = port.command('prof heap')
                status = port.status()
                b.guard_status(status, EXPECTED, physical)
                gate.final.update(status_after=status, previous_state_backup=False, previous_state_restoration=False)
                clean = True
            except BaseException as error:
                gate.final['cleanup_error'] = repr(error)
                raise
            finally:
                gate.final.update(changed_sd_files=changed, cleanup_native_verified=clean)


def run(gate):
    failure = None
    try:
        run_port(gate)
    except BaseException as error:
        failure = error
    try:
        need(gate.final.get('cdc_descriptor_closed') and not gate.final.get('port_close_errors'), 'CDC close unproved')
        gate.noholders(gate.final['native_binding'])
        need(gate.final.get('cleanup_native_verified'), 'Native/temporary cleanup unproved')
        gate.final['lease'] = 'released'
    except BaseException as error:
        gate.final['handoff_error'] = repr(error)
        if failure is None:
            failure = error
    if failure is not None:
        raise failure


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pins', action='store_true')
    for name in ('phase', 'grant', 'out'):
        parser.add_argument('--' + name, type=Path)
    args = parser.parse_args()
    if args.pins:
        print(json.dumps(source_pins(), indent=2))
        return
    need(args.phase and args.grant and args.out, 'Exact phase/grant/output required')
    validate_plan(json.loads(args.phase.read_text()))
    gate = AudioGate(args.phase, args.grant, args.out)
    gate.final['lease'] = 'closed_port_needs_attention'
    try:
        run(gate)
    except BaseException as error:
        gate.finish(False, repr(error))
        raise
    else:
        gate.finish(True)


if __name__ == '__main__':
    main()
