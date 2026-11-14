"""Host-only by default; one APP-only full-inference run after exact handoff.

The combined firmware is installed separately by the coordinator. This
controller never flashes firmware, uploads a model or touches M3/settings/RTC.
"""
import argparse
import errno
import fcntl
import json
import os
from pathlib import Path
import re
import runpy
import signal
import stat
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / '.build/mk61ai/packed-cpu-20261112'
PACKAGE = BASE / 'INFERENCE-PACKAGE.json'
PLAN = BASE / 'INFERENCE-PLAN.json'
LEASE = ROOT / '.build/m0-libc-batch-20261107-v1/ROOT-PICO-LEASE-001.json'
helpers = runpy.run_path(str(ROOT / '.build/mk61ai/math-choice-20261111/run-benchmark.py'), run_name='packed_cpu_helpers')
import hil_mk61_ai_perf as perf
ai, sha, field = perf.ai, helpers['sha'], helpers['field']
APPDIR = '/Apps/MK61AI/PACKEDCPU-20261112-001'
APP = APPDIR + '/AIBENCH.APP'
FOLDER = '/AI/HILV3-M3-9943AE8536E2'
STABLE = ('BOOTS', 'SETTINGS_WRITES', 'SETTINGS_ERASES', 'RTC_SET', 'I2C_ABORTS', 'IO_ERRORS')
CFG = dict(kernel=2, arithmetic=1, cores=2, freeze=1, filter=0, mhz=270,
           prefill=2, decode=2, repeat=2, stress_ms=5000, control=2, constrained=0, prefetch=1)


class TracedSerial(ai.Serial):
    trace = None

    def pump(self, seconds=.01):
        before = len(self.data)
        try:
            return super().pump(seconds)
        finally:
            if self.trace and len(self.data) > before:
                with self.trace.open('ab') as stream:
                    stream.write(self.data[before:])


ai.Serial = TracedSerial


def dynamic_uid():
    try:
        ai.PORT = helpers['binding']()['port']
    except (AssertionError, FileNotFoundError) as error:
        raise ValueError('UID not on CDC') from error


ai.usb_identity = dynamic_uid


def counters(s):
    result = {k: field(s, k) for k in STABLE + ('I2C_TIMEOUTS', 'IO_I2C_RESETS')}
    found = re.search(r'KBD=(?:OK|WAIT) errors=(\d+)', s)
    assert found, 'Keyboard counter missing'
    result['keyboard_errors'] = found[1]
    return result


def check(s, plan, awake=True):
    for token in ('BUILD=' + plan['new_build'], 'EXPECTED=' + plan['new_crc'],
                  'ACTUAL=' + plan['new_crc'], 'FIRMWARE_CRC=valid', 'BOOT_WATCHDOG=0',
                  'MATH_TEST=OK failures=0', 'KBD=OK', 'PSRAM=OK BYTES=8388608',
                  'SD=OK', 'USB_DISK=0', 'SYS_HZ=125000000'):
        assert token in s, token
    if awake:
        assert field(s, 'SLEEP') == '0'


def closed(s):
    return all(t in s for t in ('UI=CALCULATOR', 'SERVICE=CLOSED', 'RUNTIME=NONE'))


def connect(end):
    while time.monotonic() < end:
        try:
            p = helpers['connect'](end - time.monotonic())
            p.deadline = end
            return p
        except (ValueError, AssertionError, FileNotFoundError):
            time.sleep(.2)
        except OSError as error:
            if error.errno not in (errno.ENOENT, errno.ENXIO, errno.ENODEV, errno.EIO):
                raise
            time.sleep(.2)
    raise TimeoutError('UID-bound CDC deadline')


def validate():
    package = json.loads(PACKAGE.read_text())
    for name, digest in package['pins'].items():
        assert sha(name) == digest, name
    plan = json.loads(PLAN.read_text())
    assert plan['config'] == CFG and plan['cancel_at'] is None
    assert plan['expected_usb_reenumerations'] == 2
    assert plan['diagnostic_directory'] == FOLDER
    manifest = json.loads(Path(plan['payloads']['firmware_manifest']['path']).read_text())
    assert (manifest['build_id'].upper(), manifest['firmware_integrity']['crc32'].upper()) == (plan['new_build'], plan['new_crc'])
    assert manifest['ai_fast_clock'] and manifest['ai_fast_math'] and not manifest['ai_psram_late_read']
    assert manifest['foreground_memory_budget']['heap_capacity_bytes'] >= 108544
    arm = json.loads(Path(package['native_arm_report']).read_text())
    assert arm['status'] == 'NATIVE_ARM_ROM_PASS' and arm['integer_dot_checks'] == 6424
    assert arm['whole_and_split_checks'] == 48 and arm['numeric_error_checks'] == 8
    assert arm['format_error_checks'] == 8 and arm['failed_row_not_stored']
    assert arm['firmware_sha256'] == sha(plan['firmware_elf'])
    reference = json.loads((ROOT / '.build/mk61ai/lut8-hybrid-20261111/hardware-002/performance.json').read_text())
    assert reference['config'] == CFG
    assert plan['reference_seconds_per_token'] == [r['decode_us'] / r['decode_tokens'] / 1e6 for r in reference['results']]
    assert set(plan['accepted_model_sha256']) == {'67aae98d9ffbd332bbea6e9a7dde9ec003f8213b99d92c555b523c794256d01b'}
    return plan


def execute(go_path):
    plan = validate()
    go = json.loads(go_path.read_text())
    assert go['uid'] == ai.UID and go['coordinator_thread'] == ai.COORDINATOR
    assert go['handoff_received'] is True and go['package_sha256'] == sha(PACKAGE)
    expected = {k: str(v) for k, v in go['expected_counters'].items()}
    assert set(expected) == set(STABLE) and all(v.isdigit() for v in expected.values())
    assert go['preexisting_crash'] in ('AVAILABLE', 'NONE')
    seconds = min(230, go['finish_before_utc_epoch'] - time.time() - 10)
    assert seconds >= 120, 'Fresh window must include one run and cleanup'
    end = time.monotonic() + seconds
    out = BASE / 'inference-001'
    out.mkdir(exist_ok=False)
    (out / 'handoff.json').write_bytes(go_path.read_bytes())
    report = dict(status='HOLD', firmware_flashes=0, inference_runs=0, M3_writes=0,
                  model_writes=0, settings_writes=0, RTC_writes=0, baseline_rerun=False)
    lease = p = None
    connection = [None]
    owned, prior, touched = [], {}, set()
    initial = None

    def restore_private_files():
        for leaf in sorted(touched):
            path = FOLDER + '/' + leaf
            if leaf in prior:
                ai.upload(p, path, prior[leaf], out / 'restore-fault.bin')
                assert ai.download(p, path) == prior[leaf], 'Private file restore mismatch'
            else:
                reply = p.command('rm "' + path + '"')
                assert b'ERROR' not in reply and b'Error' not in reply
        report['prior_perf_restored'] = sorted(touched)
        touched.clear()

    try:
        lease = os.open(LEASE, os.O_RDONLY | os.O_NOFOLLOW)
        info = os.fstat(lease)
        assert info.st_ino == 289244874 and info.st_nlink == 1 and stat.S_ISREG(info.st_mode)
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        TracedSerial.trace = out / 'serial.bin'
        p = connect(min(end, time.monotonic() + 20))
        p.deadline = end
        perf.finish.drain(p, maximum=3, quiet=.25)
        before = p.status()
        (out / 'before.txt').write_text(before)
        check(before, plan, False)
        assert closed(before) and all(t in before for t in ('RUN=0', 'DIRTY=0', 'PHYSICAL_KEYS=0'))
        assert field(before, 'CRASH') == go['preexisting_crash']
        initial = counters(before)
        assert {k: initial[k] for k in STABLE} == expected
        report['counters_before'] = initial
        if field(before, 'SLEEP') == '1':
            assert go.get('allow_wake_calculator') is True
            p.send(b'\x1e\x91')
            time.sleep(.3)
            check(p.status(), plan)
        assert counters(p.status()) == initial
        p.commands()
        ai.identity(p)
        ai.create_owned(p, APPDIR, owned, out)
        command = 'ls "' + FOLDER + '"'
        listing = ai.listing_rows(p.command(command), command)
        assert b'f\t2093896 B\tMODEL.MKA' in listing, 'Pinned private model missing'
        names = {row.split(b'\t')[-1].upper() for row in listing}
        for leaf in ('PERF.CFG', 'PERF.REF', 'PERF.JSON'):
            if leaf.encode() in names:
                prior[leaf] = ai.download(p, FOLDER + '/' + leaf)
                (out / ('prior-' + leaf)).write_bytes(prior[leaf])
        for leaf, key in (('AIHASH.APP', 'hashprobe'), ('AIBENCH.APP', 'benchmark')):
            ai.upload(p, APPDIR + '/' + leaf, Path(plan['payloads'][key]['path']).read_bytes(), out / 'upload-fault.bin')
        for leaf, key in (('PERF.CFG', 'config'), ('PERF.REF', 'reference')):
            touched.add(leaf)
            ai.upload(p, FOLDER + '/' + leaf, Path(plan['payloads'][key]['path']).read_bytes(), out / 'upload-fault.bin')
        probe = APPDIR + '/AIHASH.APP'
        p.data.clear()
        p.send(('run "' + probe + '"\r').encode())
        reply = p.wait(lambda d: ai.PROMPT.search(d), 45)
        (out / 'model-sha.txt').write_bytes(reply)
        digest = re.search(rb'AI_MODEL_SHA bytes=2093896 sha256=([0-9a-f]{64})', reply)
        assert digest and digest[1].decode() in plan['accepted_model_sha256'] and b'ERROR' not in reply
        report['model_sha256'] = digest[1].decode()
        ai.leave_app(p)
        assert counters(p.status()) == initial
        print('Starting one full-inference APP at270MHz/two cores', flush=True)
        connection[0] = p
        report['inference_runs'] = 1
        touched.add('PERF.JSON')
        p, report['transport'] = perf.run_perf(connection, plan, APP, out)
        connection[0] = p
        raw = ai.download(p, FOLDER + '/PERF.JSON')
        (out / 'performance.json').write_bytes(raw)
        result = json.loads(raw)
        load = re.search(r'AI_LOAD bytes=2093896 us=(\d+) ok=1', (out / 'progress.txt').read_text())
        assert load and int(load[1]) == result['model_load_us'], 'Stale report'
        assert result['device'] and result['ok'] and not result['cancelled'] and not report['transport']['app_error']
        assert result['actual_hz'] == 270000000 and result['restored_hz'] == 125000000 and result['clocks_restored']
        assert result['config'] == CFG and result['reference_external']
        assert result['tile_rows'] == 28 and result['psram_read_divider256'] == 461
        assert result['matching_tokens'] and result['matching_checksums']
        assert result['stress_before_decode'] and result['stress_elapsed_ms'] >= 5000 and result['stress_iterations'] > 0
        stress = result['stress_diagnostic']
        assert stress['reason'] == 'none' and stress['crc_match'] and stress['busy_entered'] and stress['busy_exited']
        assert result['freeze_count'] == result['thaw_count'] and not result['freeze_violations'] and not result['i2c_errors']
        rows = result['results']
        assert len(rows) == 2 and [r['pass'] for r in rows] == [1, 2]
        for r in rows:
            assert r['prefill_tokens'] == r['decode_tokens'] == 2
            assert r['next'] == [0, 1295, 1295, 1295]
            assert r['checksums'] == ['5a7a309f', '23e0323c', '1629e247', 'e1e8d2bb']
            assert r['rows'] == 75776 and r['worker_rows'] == 37888 and r['worker_jobs'] == 3279
            assert r['prefetches'] == 2996 and not r['remote_jobs']
            assert (r['lut8_preparations'], r['lut8_reuses'], r['lut8_rows']) == (123, 120, 70656)
        assert result['sampled_heap_peak'] < result['heap_capacity'] and result['stack_high_water'] < 32768
        report['seconds_per_token'] = [r['decode_us'] / r['decode_tokens'] / 1e6 for r in rows]
        best = min(plan['reference_seconds_per_token'])
        report['reference_best_seconds_per_token'] = best
        report['faster_than_reference_best'] = all(v < best for v in report['seconds_per_token'])
        after = p.status()
        (out / 'after-app.txt').write_text(after)
        check(after, plan)
        assert counters(after) == initial and field(after, 'CRASH') == go['preexisting_crash']
        ai.leave_app(p)
        p.commands()
        restore_private_files()
        p.command('rm -r "' + APPDIR + '"', 20)
        owned.clear()
        command = 'ls "/Apps/MK61AI"'
        assert not any(row.split(b'\t')[-1].rstrip(b'/').lower() == APPDIR.rsplit('/', 1)[1].encode().lower()
                       for row in ai.listing_rows(p.command(command), command))
        report['own_directory_removed'] = True
        p.send(b'\x1e\x1b')
        time.sleep(.25)
        final = p.status()
        (out / 'final-status.txt').write_text(final)
        check(final, plan)
        assert closed(final) and counters(final) == initial
        report.update(status='MEASURED', counters_after=counters(final), restored_hz=125000000)
    except BaseException as error:
        if connection[0] is not None:
            p = connection[0]
        report['error'] = type(error).__name__ + ':' + str(error)
        (out / 'error-trace.txt').write_text(traceback.format_exc())
        if p is not None and p.fd >= 0:
            try:
                s = p.status()
                (out / 'failure-status.txt').write_text(s)
                check(s, plan)
                ai.cleanup_status(s, plan, {APP, APPDIR + '/AIHASH.APP'})
                assert 'RUNTIME=NONE' in s, 'Unexpected live APP; do not interfere'
                ai.leave_app(p)
                p.commands()
                restore_private_files()
                if owned:
                    p.command('rm -r "' + APPDIR + '"', 20)
                    owned.clear()
                    report['own_directory_removed'] = True
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
        TracedSerial.trace = None
        report['CDC_closed'] = p is None or p.fd == -1
        report['lease_closed'] = True
        (out / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2), flush=True)
    if report['status'] != 'MEASURED':
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-after-handoff', type=Path)
    args = parser.parse_args()
    validate()
    if args.execute_after_handoff:
        def expired(*unused):
            raise TimeoutError('Finite250second full-inference controller')
        signal.signal(signal.SIGALRM, expired)
        signal.alarm(250)
        try:
            execute(args.execute_after_handoff)
        finally:
            signal.alarm(0)
    else:
        print('HOST inference package PASS; no physical I/O.')
