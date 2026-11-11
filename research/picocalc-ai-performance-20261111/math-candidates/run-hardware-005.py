"""HOST-only by default; one revised private APP after a fresh exact handoff."""
from pathlib import Path
import argparse, errno, fcntl, json, os, re, runpy, signal, stat, time, traceback

ROOT = Path('/Users/bolk/Projects/MK61S_MINI')
BASE = Path(__file__).resolve().parent
helpers = runpy.run_path(str(ROOT / '.build/mk61ai/math-choice-20261111/run-benchmark.py'), run_name='matrix_helpers')
tests = runpy.run_path(str(ROOT / 'tests/prepare_mk61_ai_math_candidates.py'), run_name='matrix_decoder')
ai, sha, field = helpers['ai'], helpers['sha'], helpers['field']
UID, BUILD, CRC = 'E6657CD423721C35', '7C38C634', '8A17554E'
APPDIR = '/Apps/MATHCAND-20261111-005'
APP = APPDIR + '/MATHCAND.APP'
PACKAGE = BASE / 'HARDWARE-PACKAGE-005.json'
LEASE = ROOT / '.build/m0-libc-batch-20261107-v1/ROOT-PICO-LEASE-001.json'

class TracedSerial(ai.Serial):
    trace_path = None
    def pump(self, seconds=.01):
        start = len(self.data)
        try:
            return super().pump(seconds)
        finally:
            if self.trace_path and len(self.data) > start:
                with self.trace_path.open('ab') as stream:
                    stream.write(self.data[start:])

ai.Serial = TracedSerial

def validate():
    package = json.loads(PACKAGE.read_text())
    for path, digest in package['pins'].items():
        assert sha(path) == digest, path
    meta = json.loads((BASE / 'package.json').read_text())
    for name, digest in meta['source_pins'].items():
        assert sha(ROOT / name) == digest, name
    for name, digest in meta['generated'].items():
        assert sha(BASE / name) == digest, name
    assert sha(meta['resident_elf']) == meta['resident_elf_sha256']
    arm = json.loads((BASE / 'arm-results.json').read_text())
    assert arm['status'] == 'ARM_ROM_PASS' and arm['bound_includes_FP32_rounding']
    assert arm['app_sha256'] == sha(BASE / 'app/MATHCAND.APP')
    assert arm['two_core_dispatch_executed'] and arm['worker_refusal_fails_without_join']
    cfg = json.loads((BASE / 'cfg-results.json').read_text())
    assert cfg['status'] == 'LINKED_CFG_AND_NEGATIVE_ARM_PASS'
    assert cfg['app_sha256'] == arm['app_sha256']
    assert cfg['positive']['timed_two_core_submit_and_join']
    assert cfg['negative']['matches_hardware_LR_and_r4']
    return package

def check(s, awake=True):
    for token in ('BUILD=' + BUILD, 'EXPECTED=' + CRC, 'ACTUAL=' + CRC,
                  'FIRMWARE_CRC=valid', 'CRASH=AVAILABLE', 'BOOT_WATCHDOG=0', 'MATH_TEST=OK failures=0', 'KBD=OK',
                  'PSRAM=OK BYTES=8388608', 'SD=OK', 'USB_DISK=0', 'SYS_HZ=125000000'):
        assert token in s, token
    if awake:
        assert field(s, 'SLEEP') == '0'

def counters(s):
    result = {key: field(s, key) for key in ('SETTINGS_WRITES', 'SETTINGS_ERASES',
              'RTC_SET', 'BOOTS', 'I2C_TIMEOUTS', 'IO_I2C_RESETS', 'I2C_ABORTS', 'IO_ERRORS')}
    match = re.search(r'KBD=(?:OK|WAIT) errors=(\d+)', s)
    assert match
    result['keyboard_errors'] = match[1]
    return result

STABLE = ('BOOTS', 'SETTINGS_WRITES', 'SETTINGS_ERASES', 'RTC_SET', 'I2C_ABORTS', 'IO_ERRORS')
TELEMETRY = ('I2C_TIMEOUTS', 'IO_I2C_RESETS', 'keyboard_errors')

def admit_counters(expected, observed):
    assert set(expected) == set(STABLE), 'GO must pin all protected counters'
    assert {k: observed[k] for k in STABLE} == expected, ('Protected counters differ', observed, expected)
    assert all(re.fullmatch(r'[0-9]+', observed[k]) for k in TELEMETRY)
    return dict(observed) # Capture ambient values once, never reset or recapture.

def unchanged(initial, current):
    assert current == initial, ('Counter delta during own window', initial, current)

def closed(s):
    return all(token in s for token in ('UI=CALCULATOR', 'SERVICE=CLOSED', 'RUNTIME=NONE'))

def finished(s):
    return 'PATH=[' + APP + ']' in s and 'RUNTIME=NONE' in s and 'RESULT=[APP finished' in s

def returned(s):
    return 'PATH=[' + APP + ']' in s and 'RUNTIME=NONE' in s and 'SERVICE=VIEWER' in s

def connect(end):
    while time.monotonic() < end:
        try:
            return helpers['connect'](end - time.monotonic())
        except (ValueError, AssertionError, FileNotFoundError):
            time.sleep(.2)
        except OSError as error:
            if error.errno not in (errno.ENOENT, errno.ENXIO, errno.ENODEV, errno.EIO):
                raise
            time.sleep(.2)
    raise TimeoutError('UID-bound CDC did not return')

def retrieve_owned(p, out):
    command = 'ls "' + APPDIR + '"'
    names = [row.split(b'\t')[-1] for row in ai.listing_rows(p.command(command), command)]
    (out / 'owned-files.json').write_text(json.dumps([name.decode('ascii', 'replace') for name in names]) + '\n')
    for name in ('SETUP.BIN', 'MATHTEST.BIN'):
        if name.encode() in names:
            (out / name).write_bytes(ai.download(p, APPDIR + '/' + name))

def execute(attempt, handoff):
    package = validate()
    go = json.loads(handoff.read_text())
    assert go['uid'] == UID and go['coordinator_thread'] == ai.COORDINATOR
    assert go['handoff_received'] is True and go['package_sha256'] == sha(PACKAGE)
    expected = {key: str(value) for key, value in go['expected_counters'].items()}
    assert expected['BOOTS'] == package['expected_boots'], 'Boot changed since retained crash review'
    assert all(expected[k] == '0' for k in ('SETTINGS_WRITES', 'SETTINGS_ERASES', 'RTC_SET', 'I2C_ABORTS', 'IO_ERRORS')), 'Protected state changed'
    assert all(re.fullmatch(r'[0-9]+', v) for v in expected.values()), 'Invalid explicit GO counters'
    assert go['preexisting_crash'] == 'AVAILABLE', 'Preserve prior SDK panic evidence'
    assert set(expected) == set(STABLE)
    seconds = min(150, go['finish_before_utc_epoch'] - time.time() - 10)
    assert seconds >= 100, 'Fresh window must include upload, one test and cleanup'
    out = BASE / ('hardware-%03d' % attempt)
    out.mkdir(exist_ok=False)
    (out / 'handoff.json').write_bytes(handoff.read_bytes())
    report = dict(status='HOLD', Flash_writes=0, M3_writes=0, crash_clears=0, preexisting_crash='AVAILABLE', test_runs=0, owned_directory=APPDIR)
    lease = p = None
    owned = []
    end = time.monotonic() + seconds
    try:
        lease = os.open(LEASE, os.O_RDONLY | os.O_NOFOLLOW)
        info = os.fstat(lease)
        assert info.st_ino == 289244874 and info.st_nlink == 1 and stat.S_ISREG(info.st_mode)
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        TracedSerial.trace_path = out / 'serial.bin'
        p = connect(min(end, time.monotonic() + 20))
        p.deadline = end
        time.sleep(.2)
        p.pump(.05)
        before = p.status()
        (out / 'before.txt').write_text(before)
        check(before, False)
        assert closed(before) and all(t in before for t in ('DIRTY=0', 'RUN=0', 'PHYSICAL_KEYS=0'))
        initial = admit_counters(expected, counters(before))
        report['counters_before'] = initial
        report['ambient_entry_telemetry'] = {k: initial[k] for k in TELEMETRY}
        if field(before, 'SLEEP') == '1':
            assert go.get('allow_wake_calculator') is True
            p.send(b'\x1e\x91')
            time.sleep(.3)
            check(p.status())
        time.sleep(.2)
        unchanged(initial, counters(p.status()))
        p.commands()
        ai.identity(p)
        ai.create_owned(p, APPDIR, owned, out)
        report['upload'] = ai.upload(p, APP, (BASE / 'app/MATHCAND.APP').read_bytes(), out / 'upload-fault.bin')
        report['fixtures_upload'] = ai.upload(p, APPDIR + '/MATHCASE.BIN', (BASE / 'MATHCASE.BIN').read_bytes(), out / 'upload-fault.bin')
        print('Starting one corrected two-core matrix APP at270MHz', flush=True)
        p.data.clear()
        p.send(('run "' + APP + '"\r').encode())
        report['test_runs'] = 1
        last, reconnects = time.monotonic(), 0
        while time.monotonic() < end:
            try:
                p.pump(.05)
                if ai.PROMPT.search(bytes(p.data)):
                    break
                if time.monotonic() - last > 5:
                    p.close()
                    p = connect(end)
                    s = p.status()
                    (out / ('poll-%02d.txt' % reconnects)).write_text(s)
                    last, reconnects = time.monotonic(), reconnects + 1
                    assert counters(s)['BOOTS'] == initial['BOOTS'], 'Reboot; no replay'
                    if field(s, 'SYS_HZ') == '125000000' and (closed(s) or returned(s)):
                        break
                    assert 'PATH=[' + APP + ']' in s, 'Unexpected foreground'
            except OSError:
                p.close()
                p = connect(end)
                last, reconnects = time.monotonic(), reconnects + 1
        else:
            raise TimeoutError('Finite matrix APP did not finish')
        after = p.status()
        (out / 'after-app.txt').write_text(after)
        unchanged(initial, counters(after))
        check(after)
        assert finished(after), 'Owned APP did not finish successfully'
        ai.leave_app(p)
        p.commands()
        retrieve_owned(p, out)
        result = tests['decode'](out / 'MATHTEST.BIN')
        (out / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
        p.command('rm -r "' + APPDIR + '"', 20)
        owned.clear()
        report['owned_directory_removed'] = True
        command = 'ls "/Apps"'
        assert not any(row.split(b'\t')[-1].rstrip(b'/').lower() == APPDIR.rsplit('/', 1)[1].encode().lower()
                       for row in ai.listing_rows(p.command(command), command))
        p.send(b'\x1e\x1b')
        time.sleep(.25)
        final = p.status()
        (out / 'final-status.txt').write_text(final)
        check(final)
        assert closed(final)
        unchanged(initial, counters(final))
        report.update(status='PASS', build=BUILD, crc=CRC, restored_hz=125000000,
                      counters_after=counters(final), CDC_reconnects=reconnects,
                      result='results.json', matrix_cases=len(result['matrix_tiles']), cores=result['cores'])
    except BaseException as error:
        report['error'] = type(error).__name__ + ':' + str(error)
        (out / 'error-trace.txt').write_text(traceback.format_exc())
        if p is not None and p.fd >= 0 and owned:
            try:
                s = p.status()
                (out / 'failure-status.txt').write_text(s)
                if field(s, 'SYS_HZ') == '125000000' and 'BUILD=' + BUILD in s and (closed(s) or returned(s)):
                    ai.leave_app(p)
                    p.commands()
                    retrieve_owned(p, out)
                    p.command('rm -r "' + APPDIR + '"', 20)
                    report['owned_directory_removed'] = True
                    p.send(b'\x1e\x1b')
                    time.sleep(.25)
                    (out / 'failed-final-status.txt').write_text(p.status())
            except BaseException as cleanup_error:
                report['cleanup_error'] = repr(cleanup_error)
    finally:
        if p:
            p.close()
        if lease is not None:
            os.close(lease)
        TracedSerial.trace_path = None
        report['CDC_closed'] = p is None or p.fd == -1
        report['lease_closed'] = True
        (out / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2), flush=True)
    if report['status'] != 'PASS':
        raise SystemExit(1)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-after-handoff', type=Path)
    parser.add_argument('--attempt', type=int, choices=range(5, 10), default=5)
    args = parser.parse_args()
    validate()
    if args.execute_after_handoff:
        def expired(*unused):
            raise TimeoutError('Finite180second matrix APP controller')
        signal.signal(signal.SIGALRM, expired)
        signal.alarm(180)
        try:
            execute(args.attempt, args.execute_after_handoff)
        finally:
            signal.alarm(0)
    else:
        print('HOST pins and numerical qualification PASS; no physical I/O.')
