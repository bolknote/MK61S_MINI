"""HOST by default. Execute once only after the coordinator hands over PicoCalc.

The user authorizes a higher PSRAM read rate at270 MHz
measurement after handoff. No reference execution, M3 work or stress sweep.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import signal
import struct
import sys
import time

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / 'controller'))
import hil_mk61_ai_perf as perf

ai, finish = perf.ai, perf.finish
_original_readiness = ai.readiness
def cumulative_key_readiness(status, build, crc):
    found = re.search(r'\bPHYSICAL_KEYS=(\d+)', status)
    assert found
    result = _original_readiness(re.sub(r'\bPHYSICAL_KEYS=\d+', 'PHYSICAL_KEYS=0', status), build, crc)
    result.pop('physical_keys', None)
    result['physical_key_events_since_boot'] = int(found[1])
    return result
ai.readiness = cumulative_key_readiness


def validate():
    plan = json.loads((BASE / 'RUN270-v3.json').read_text())
    for item in plan['pins'].values():
        path = Path(item['path'])
        if path.stat().st_size != item['bytes'] or ai.sha(path) != item['sha256']:
            raise ValueError('HOST payload changed: ' + str(path))
    manifest = json.loads(Path(plan['payloads']['firmware_manifest']['path']).read_text())
    assert manifest['ai_fast_clock'] and manifest['ai_psram_late_read']
    assert manifest['build_id'].upper() == plan['new_build']
    assert manifest['firmware_integrity']['crc32'].upper() == plan['new_crc']
    assert manifest['uf2_sha256'] == plan['payloads']['uf2']['sha256']
    # Spectrum reserves [0x101c0000,0x101e0000) for ROMCACHE.
    # Check every actual UF2 write, not only the nominal binary length.
    limit=0x1c0000
    assert manifest['flash_bytes'] == Path(plan['payloads']['bin']['path']).stat().st_size <= limit
    uf2=Path(plan['payloads']['uf2']['path']).read_bytes()
    assert uf2 and len(uf2)%512==0
    for i in range(len(uf2)//512):
        block=uf2[i*512:(i+1)*512];header=struct.unpack_from('<8I',block)
        assert header[:3]==(0x0a324655,0x9e5d5157,0x2000)
        assert header[3]==0x10000000+i*256 and header[4:7]==(256,i,len(uf2)//512)
        assert header[7]==0xe48bff56 and struct.unpack_from('<I',block,508)[0]==0x0ab16f30
        assert header[3]+header[4]<=0x10000000+limit,'UF2 overlaps ROMCACHE'
    assert plan['config'] == dict(kernel=2, arithmetic=1, cores=2, freeze=1,
        filter=0, mhz=270, prefill=2, decode=2, repeat=0, stress_ms=5000,
        control=2, constrained=0, prefetch=1)
    assert plan['reference_seconds_per_token'] == 0.606
    return plan


def restore_known_good(plan, output, report):
    recovery = dict(plan, old_build=plan['new_build'], old_crc=plan['new_crc'],
        payloads=dict(plan['payloads'], uf2=plan['payloads']['return_uf2']))
    dest=output/'return-known-good';dest.mkdir(exist_ok=False)
    finish.flash_once(recovery,dest)
    p=ai.Serial(time.monotonic()+30)
    try:
        report['final']=ai.readiness(p.status(),'5D0A3631','B836FE58')
        report['returned_known_good']=True
    finally:p.close()


def execute(plan, handoff):
    evidence = json.loads(handoff.read_text())
    assert evidence['coordinator_thread'] == ai.COORDINATOR
    assert evidence['uid'] == ai.UID and evidence['handoff_received'] is True
    assert evidence['message'].strip()
    assert evidence['package_sha256'] == ai.sha(BASE / "PACKAGE-v3.json")
    assert time.time() < evidence["finish_before_utc_epoch"]
    assert evidence.get('romcache_verified') is True, 'ROMCACHE not verified in handoff'
    output = BASE / 'hardware270-v3'
    output.mkdir(exist_ok=False)
    (output / 'handoff.json').write_bytes(handoff.read_bytes())
    report = dict(status='HOLD', physical_io=False, control_rerun=False,
        reference_seconds_per_token=0.606, save_or_restore=False,
        cores=2, requested_hz=270000000)
    port = None
    result = {}
    owned = []
    appfolder = '/Apps/MK61AI/' + plan['app_nonce']
    connection = [None]
    lease = None
    try:
        lease = os.open(plan['root_lease_path'], os.O_RDONLY | os.O_NOFOLLOW)
        info = os.fstat(lease)
        assert stat.S_ISREG(info.st_mode) and info.st_nlink == 1
        assert info.st_ino == plan['root_lease_inode']
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        ai.usb_identity()
        port = ai.Serial(time.monotonic() + 30)
        report['physical_io'] = True
        finish.drain(port, maximum=3, quiet=.25)
        status = port.status()
        (output/'preflight-before.txt').write_text(status)
        old_build = re.search(r'(?<![A-Z_])BUILD=([0-9A-F]{8})\b', status)
        old_crc = re.search(r'\bEXPECTED=([0-9A-F]{8})\s+ACTUAL=\1\b', status)
        assert old_build and old_crc
        assert evidence.get('expected_build') == old_build[1] and evidence.get('expected_crc') == old_crc[1], 'device changed since coordinator handoff'
        plan.update(old_build=old_build[1], old_crc=old_crc[1])
        if 'RUNTIME=NONE' not in status or 'SERVICE=CLOSED' not in status or 'UI=CALCULATOR' not in status or re.search(r'\bSLEEP=1\b',status):
            assert evidence.get('allow_exit_finished_spectrum') is True
            assert plan['old_build']=='5D0A3631' and plan['old_crc']=='B836FE58'
            assert all(t in status for t in ('RUNTIME=APP','PATH=[/SpectrumStereo/SPECTRUM.APP]','RESULT=[APP finished; Enter / Esc: files]','DIRTY=0'))
            def field(raw,key):
                m=re.search(r'(?<![A-Z_])'+key+r'=([^\s]+)',raw);assert m,key
                return m[1]
            counters=('BOOTS','PHYSICAL_KEYS','POWER_BUTTONS','SETTINGS_WRITES','SETTINGS_ERASES','RTC_SET','SLEEP_ENTRIES')
            before={k:field(status,k) for k in counters}
            if field(status,'SLEEP')=='1':
                port.send(b'\x1e\x91')  # Existing system POWER event; one wake only.
                end=time.monotonic()+3
                while True:
                    port.pump(.05);status=port.status()
                    if field(status,'SLEEP')=='0' and field(status,'POWER_MODE')=='RUN':break
                    assert time.monotonic()<end,'Wake did not settle'
                assert int(field(status,'POWER_BUTTONS'))==int(before['POWER_BUTTONS'])+1
                (output/'preflight-awake.txt').write_text(status)
            for _ in range(8):
                if all(t in status for t in ('SERVICE=CLOSED','RUNTIME=NONE','UI=CALCULATOR')):break
                port.send(b'\x1e\x1b')
                end=time.monotonic()+.25
                while time.monotonic()<end:port.pump(.02)
                status=port.status()
            else:raise AssertionError('Finished Spectrum screen did not close')
            after={k:field(status,k) for k in counters}
            assert all(before[k]==after[k] for k in ('BOOTS','PHYSICAL_KEYS','SETTINGS_WRITES','SETTINGS_ERASES','RTC_SET'))
            assert field(status,'SLEEP')=='0'
            report['finished_spectrum_closed']={'before':before,'after':after,'restarted':False,'files_changed':False}
            (output/'preflight-after.txt').write_text(status)
        report['entry'] = ai.readiness(status, plan['old_build'], plan['old_crc'])
        port.close(); port = None
        if plan['old_build'] != plan['new_build']:
            finish.flash_once(plan, output)
            report['firmware_flashed'] = True
        else:
            report['candidate_already_installed'] = True
        ai.wait_usb_identity(20)
        port = ai.Serial(time.monotonic() + 240)
        boot_deadline = time.monotonic() + 30
        while True:
            try:
                ai.readiness(port.status(), plan['new_build'], plan['new_crc'])
                break
            except ValueError:
                if time.monotonic() >= boot_deadline:
                    raise
                time.sleep(0.2)
        port.commands(); ai.identity(port)

        def listing(path):
            command = 'ls "' + path + '"'
            return ai.listing_rows(port.command(command), command)

        folder = '/AI/' + plan['nonce']
        appfolder = '/Apps/MK61AI/' + plan['app_nonce']
        owned = []
        if plan['nonce'].encode().lower() not in [r.split(b'\t')[-1].rstrip(b'/').lower() for r in listing('/AI')]:
            ai.create_owned(port, folder, owned, output)
        rows = listing(folder)
        model = plan['payloads']['model']
        present = any(row == f'f\t{model["bytes"]} B\tMODEL.MKA'.encode() for row in rows)
        if not present:
            assert not any(row.split(b'\t')[-1].upper() == b'MODEL.MKA' for row in rows)
            perf.install_alternate(port, plan, output)
        report['model_reused'] = present
        ai.create_owned(port, appfolder, owned, output)
        for leaf, payload in [('PERF.CFG', 'config'), ('PERF.REF', 'reference')]:
            ai.upload(port, folder + '/' + leaf, Path(plan['payloads'][payload]['path']).read_bytes(), output / 'upload-fault.bin')
        for leaf, payload in [('AIHASH.APP', 'hashprobe'), ('AIBENCH.APP', 'benchmark')]:
            ai.upload(port, appfolder + '/' + leaf, Path(plan['payloads'][payload]['path']).read_bytes(), output / 'upload-fault.bin')
        foreground = set()
        app = appfolder + '/AIHASH.APP'
        ai.mark_foreground(app, foreground, output)
        port.data.clear(); port.send(('run "' + app + '"\r').encode())
        reply = port.wait(lambda b: ai.PROMPT.search(b), 60)
        digest = re.search(rb'AI_MODEL_SHA bytes=(\d+) sha256=([0-9a-f]{64})', reply)
        assert digest and int(digest[1]) == model['bytes'] and digest[2].decode() == model['sha256']
        assert b'ERROR' not in reply
        report['model_sha256'] = digest[2].decode()
        ai.leave_app(port)
        app = appfolder + '/AIBENCH.APP'
        ai.mark_foreground(app, foreground, output)
        connection[0] = port
        port, report['transport'] = perf.run_perf(connection, plan, app, output)
        result = json.loads(ai.download(port, folder + '/PERF.JSON'))
        (output / 'stress-performance.json').write_text(json.dumps(result, indent=2) + '\n')
        load = re.search(r'AI_LOAD bytes=2093896 us=(\d+) ok=1', (output / 'progress.txt').read_text())
        assert load and result['model_load_us'] == int(load[1]), 'stale result'
        assert result['ok'] and result['device'] and not result['cancelled']
        assert result['config'] == plan['config'] and result['actual_hz'] == 270000000
        assert result['clocks_restored'] and result['restored_hz'] == 125000000
        assert result['reference_external'] and result['matching_tokens'] and result['matching_checksums']
        assert result['matching_kv'] is None and result['tile_rows'] == 28
        assert result['psram_read_divider256'] == plan['read_divider256']
        assert result['stress_iterations'] > 0 and result['control_probe_calls'] == 1
        assert result['stress_before_decode'] is True and result['stress_elapsed_ms'] >= 5000
        d=result['stress_diagnostic']
        assert d['reason']=='none' and d['busy_entered'] and d['busy_exited']
        assert d['write_status']==d['read_status']==1 and d['crc_match']
        assert not result['i2c_errors'] and not result['freeze_violations']
        assert result['freeze_count'] == result['thaw_count']
        assert not report['transport']['app_error']
        assert result['stress_only'] is True and result['results']==[]
        assert result['worker_jobs']>0
        report.update(diagnostic_only=True,decode_not_run=True,stress_diagnostic=d,
            stress_elapsed_ms=result['stress_elapsed_ms'],stress_iterations=result['stress_iterations'])
        assert result['sampled_heap_peak'] < result['heap_capacity'] and result['stack_high_water'] < 32768
        ai.leave_app(port)
        report['stress_final'] = ai.readiness(port.status(), plan['new_build'], plan['new_crc'])
        # Same immutable lease, same firmware and model. Decode is gated by
        # the assertions above; no candidate pass exists before stress PASS.
        (output / 'progress.txt').rename(output / 'stress-progress.txt')
        ai.upload(port, folder + '/PERF.CFG', Path(plan['payloads']['performance_config']['path']).read_bytes(), output / 'upload-fault.bin')
        port.command('rm "' + folder + '/PERF.JSON"', 20)
        perf_plan = dict(plan, config=plan['performance_config'])
        port.deadline = min(port.deadline, time.monotonic() + 180)
        connection[0] = port
        port, report['performance_transport'] = perf.run_perf(connection, perf_plan, app, output)
        result = json.loads(ai.download(port, folder + '/PERF.JSON'))
        (output / 'performance.json').write_text(json.dumps(result, indent=2) + '\n')
        load = re.search(r'AI_LOAD bytes=2093896 us=(\d+) ok=1', (output / 'progress.txt').read_text())
        assert load and result['model_load_us'] == int(load[1]), 'stale performance result'
        assert result['ok'] and result['device'] and not result['cancelled']
        assert result['config'] == plan['performance_config'] and result['actual_hz'] == 270000000
        assert result['reference_external'] and result['matching_tokens'] and result['matching_checksums']
        assert result['clocks_restored'] and result['restored_hz'] == 125000000
        assert result['matching_kv'] is None and result['tile_rows'] == 28
        assert result['psram_read_divider256'] == 346 and result['stress_iterations'] == 0
        assert not result['stress_only'] and not result['i2c_errors'] and not result['freeze_violations']
        assert result['freeze_count'] == result['thaw_count']
        assert not report['performance_transport']['app_error']
        rows=result['results'];assert len(rows)==2 and [r['pass'] for r in rows]==[1,2]
        for row in rows:
            assert row['prefill_tokens']==row['decode_tokens']==2
            assert row['rows']==75776 and row['worker_rows']==37888
            assert row['worker_jobs']==3279 and row['prefetches']>0
            assert not row['remote_jobs'] and not row['remote_rows'] and not row['remote_fallbacks']
        assert result['sampled_heap_peak'] < result['heap_capacity'] and result['stack_high_water'] < 32768
        report['decode_not_run']=False
        report['seconds_per_token']=[r['decode_us']/r['decode_tokens']/1e6 for r in rows]
        report['time_reduction_percent']=[100*(1-x/0.606) for x in report['seconds_per_token']]
        report['faster_than_reference']=all(x<0.606 for x in report['seconds_per_token'])
        report['archive_tokens_checksums_match']=True
        ai.leave_app(port)
        report['final'] = ai.readiness(port.status(), plan['new_build'], plan['new_crc'])
        port.command('rm -r "' + appfolder + '"', 20)
        port.send(b'\x1e')
        report.update(status='MEASUREMENT_PASS', apps_removed=True)
        if not report['faster_than_reference']:
            port.close();port=None
            restore_known_good(plan,output,report)

    except BaseException as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
        # A failed private stress never enters run(pass1). If the diagnostic
        # restored125MHz, close its error screen before relinquishing USB.
        if port is not None and result.get('clocks_restored') and result.get('restored_hz') == 125000000:
            try:
                ai.leave_app(port)
                report['final'] = ai.readiness(port.status(), plan['new_build'], plan['new_crc'])
                report['failed_test_closed_at_125MHz'] = True
                if appfolder in owned:
                    port.command('rm -r "' + appfolder + '"', 20)
                    report['apps_removed'] = True
                port.close();port=None
                restore_known_good(plan,output,report)
            except BaseException as cleanup_error:
                report['cleanup_error'] = type(cleanup_error).__name__ + ': ' + str(cleanup_error)

    finally:
        for item in [port, connection[0]]:
            if item is not None:
                item.close()
        if lease is not None:
            os.close(lease)
        report['cdc_closed'] = all(item is None or item.fd == -1 for item in [port, connection[0]])
        report['lease_closed'] = True
        (output / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2), flush=True)
    if report['status'] != 'MEASUREMENT_PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-after-handoff', type=Path)
    args = parser.parse_args()
    plan = validate()
    if args.execute_after_handoff:
        def timeout_handler(signum, frame):
            raise TimeoutError("bounded360second PSRAM qualification window expired")
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(360)
        try:execute(plan, args.execute_after_handoff)
        finally:signal.alarm(0)
    else:
        print(json.dumps(dict(status='HOST_READY', physical_io=False,
            new_build=plan['new_build'], config=plan['config'],
            reference_seconds_per_token=0.606, control_rerun=False), indent=2))
