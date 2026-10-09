#!/usr/bin/env python3
"""Profile real System compiler entries on one pinned diagnostic F411.

Only BASIC.APP/FOCAL.APP are switched, then restored to their verified
baseline. One new FOCAL fixture is removed. Compiler self-time excludes
nested source/Flash/APP loads, but includes the real frontend/sizing/EMIT.
"""
import argparse
import binascii
from dataclasses import asdict
import fcntl
import hashlib
import json
from pathlib import Path
import re
import statistics
import struct
import sys
import termios
import time

from hil_c5_stack import read_file as read_file_once
from hil_c6_system_bootstrap import write_file, bundle_payload
from hil_multi_device_identity import parse_identity
import hil_packbits_firmware as fingerprints
from hil_portable_apps import ScreenPort, PROMPT, cobs_decode
from hil_turochamp_performance import profile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from m8_codec import encode

FIXTURE = '/CRLFSTATS.foc'
CHANGED = ('BASIC.APP', 'FOCAL.APP')
CASES = (('search', '/Games/Turochamp/search.tbi', 'basic'),
         ('intro', '/Games/High Noon/intro.tbi', 'basic'),
         ('statistics', FIXTURE, 'focal'))

def save(path, result): path.write_text(json.dumps(result, indent=2) + '\n')

class MeasurePort(ScreenPort):
    # Timing comes from independently parsed DWT ASCII counters, not pixels.
    # Discard corrupt screen transport, never accept its pixels, and resync
    # only at a fresh CRC-valid frame begin. Keep every dropped packet visible.
    def __init__(self, path):
        super().__init__(path); self.bad_packets = 0; self.drop_frame = False
    def receive_packet(self, encoded):
        try:
            raw = cobs_decode(encoded)
            assert len(raw) >= 11 and raw[:3] == b'MS\x02'
            assert len(raw) == struct.unpack_from('<H', raw, 7)[0] + 11
            assert binascii.crc_hqx(raw[:-2], 65535) == struct.unpack_from('<H', raw, len(raw) - 2)[0]
            if self.drop_frame and raw[3] in (0x21, 0x22): return
            if raw[3] == 0x20: self.drop_frame = False
            super().receive_packet(encoded)
        except (AssertionError, IndexError, struct.error):
            self.bad_packets += 1; self.drop_frame = True
            self.pending = None; self.pages = set()

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', required=True)
    ap.add_argument('--public-id', required=True)
    ap.add_argument('--usb-serial', required=True)
    ap.add_argument('--build-id', required=True)
    ap.add_argument('--baseline', type=Path, required=True, help='verified baseline System directory')
    ap.add_argument('--candidate', type=Path, required=True, help='candidate System directory')
    ap.add_argument('--output-dir', type=Path, required=True)
    ap.add_argument('--runs', type=int, default=7)
    args = ap.parse_args(); assert 3 <= args.runs <= 15
    out = args.output_dir.resolve(); out.mkdir(parents=True, exist_ok=True)
    result = dict(status='RUNNING', runs=[], variants={}, temporary_file=FIXTURE)
    fixture = encode((ROOT / 'tests/data/language_compression/statistics.foc').read_text())
    written = False; swapped = False; port = None; before_files = None; saved = None

    def read_file(p, path):
        # A missed CDC chunk must never become a valid fingerprint. Retry
        # read-only transfer failures; content equality remains a separate,
        # non-retried assertion after every read/atomic replacement.
        for attempt in range(3):
            try: return read_file_once(p, path)
            except AssertionError as error:
                result.setdefault('transport_read_retries', []).append(dict(
                    path=path, attempt=attempt + 1,
                    error_sha256=hashlib.sha256(str(error).encode()).hexdigest()))
                if attempt == 2: raise AssertionError('CRC/offset read failed: ' + path) from None
                p.pump(.2)
                print('Retrying incomplete read-only CDC transfer:', path, flush=True)
    fingerprints.read_file = read_file
    fingerprint = fingerprints.fingerprint

    def identify(p):
        identity = parse_identity(p.command('identity'))
        assert (identity.public, identity.usb, identity.build, identity.profile) == (
            args.public_id.upper(), args.usb_serial, args.build_id.upper(), 'classic-v3-uc1609'), identity
        return identity
    def connect():
        deadline = time.monotonic() + 30
        while True:
            p = None
            try:
                p = MeasurePort(args.port); fcntl.ioctl(p.fd, termios.TIOCEXCL)
                identify(p); return p
            except (OSError, TimeoutError):
                if p: p.close()
                if time.monotonic() >= deadline: raise
                time.sleep(.15)
            except BaseException:
                if p: p.close()
                raise
    def reset():
        nonlocal port
        identify(port)
        port.drain(); port.write_line('rst now'); time.sleep(.2); port.close()
        port = connect()
    def restore_registers():
        for name in ('R' + c for c in '0123456789ABCDE'): port.command(name + '= 0')
        port.command('cd /')
    def install(system):
        nonlocal swapped
        for name in CHANGED:
            path = '/System/' + name; data = (system / name).read_bytes()
            if read_file(port, path) != data:
                # Same inode and extent count: C8's atomic replacement reuses
                # the existing extent IDs. No unrelated file is removed.
                swapped = True; write_file(port, path, data)
                assert read_file(port, path) == data
                print('Verified System replacement:', name, len(data), flush=True)
    def cancel():
        if not port.attached: return
        for _ in range(3):
            port.key(39); port.pump(.15)
            if PROMPT.search(port.text[port.open_text_start:]): return
        raise TimeoutError('foreground did not finish after ESC')

    try:
        port = connect(); result['identity'] = asdict(identify(port))
        before_files = fingerprint(port)
        assert FIXTURE.casefold() not in {p.casefold() for p in before_files['files']}
        for path in args.baseline.iterdir():
            # HELP text is stored as M8, unlike its UTF-8 bundle source.
            assert read_file(port, '/System/' + path.name) == bundle_payload(args.baseline, path.name), path.name
        saved = {cmd: port.command(cmd, timeout=15) for cmd in ('reg', 'stk', 'dump', 'pwd')}
        numbers = re.findall(r'=\s*([+\-]?\d+\.\d+)\s+([+\-]?\d+)', saved['reg'] + saved['stk'])
        assert len(numbers) == 20 and all(float(n) == 0 for n, _ in numbers), 'reset requires empty calculator'
        codes = re.findall(r'\b[0-9A-F]{2}\b', saved['dump'].split('\r\n', 1)[1])
        assert len(codes) == 105 and set(codes) == {'00'} and '\r\n/\r\n' in saved['pwd']
        reset()
        write_file(port, FIXTURE, fixture); written = True
        assert read_file(port, FIXTURE) == fixture
        result['scope'] = 'Cold real System compiler self-time; real frontend+sizing+EMIT, nested I/O/loads excluded; VM execution and final-key wait not included'
        # Bracket the new compiler with the original one to reveal drift.
        for block, system in (('baseline', args.baseline), ('candidate', args.candidate),
                              ('baseline-repeat', args.baseline)):
            reset(); install(system); rows = {}
            for name, path, language in CASES:
                samples = []
                for repeat in range(args.runs):
                    reset(); port.attach(); port.pump(.15)
                    port.command('prof start'); port.open(path); port.pump(.15)
                    cancel()
                    counters = port.command('prof stop', timeout=15)
                    values = profile(counters)
                    assert values['clock_hz'] == 96000000
                    point = values['points']['app.entry.' + language]
                    assert point['calls'] and point['self_cycles']
                    assert values['points']['zx0.app.' + language]['calls'] == 1
                    assert values['points']['file.source']['calls'] == 1
                    assert sum(m['misses'] for m in values['vm_cache']) == 1 and values['vm_cache_dropped'] == 0
                    assert not values['points']['flash.write']['calls'] and not values['points']['flash.erase']['calls']
                    assert 'CRASH none' in port.command('crash show')
                    (out / f'{block}-{name}-{repeat}-prof.txt').write_text(counters)
                    sample = dict(block=block, source=name, repeat=repeat,
                        compiler_calls=point['calls'], compiler_self_seconds=point['self_seconds'],
                        profile=values, crc_frames=len(port.frames), dropped_screen_packets=port.bad_packets)
                    result['runs'].append(sample); samples.append(point['self_seconds'])
                    save(out / 'report.json', result)
                    print(block, name, repeat, f'{point["self_seconds"] * 1000:.6f} ms compiler self PASS', flush=True)
                    port.send(0x13); port.attached = False; port.pump(.2)
                rows[name] = dict(seconds=samples, median_seconds=statistics.median(samples))
            result['variants'][block] = rows
        result['status'] = 'PASS'
    except BaseException as error:
        result['status'] = 'FAIL'; result['error'] = repr(error)
        raise
    finally:
        if port:
            try:
                if port.attached:
                    cancel(); port.send(0x13); port.attached = False; port.pump(.2)
                if saved is not None:
                    reset(); install(args.baseline)
                    if written:
                        assert read_file(port, FIXTURE) == fixture
                        assert 'Removed 1 entry.' in port.command('rm "' + FIXTURE + '"')
                        written = False; result['fixture_removed'] = True
                    restore_registers()
                    for cmd, text in saved.items(): assert port.command(cmd, timeout=15) == text, cmd
                    assert fingerprint(port) == before_files
                    result['original_files_preserved'] = len(before_files['files'])
                    result['original_registers_stack_program_cwd_restored'] = True
                    result['health_after'] = {cmd: port.command(cmd, timeout=15)
                        for cmd in ('identity', 'df', 'mpu status', 'crash show')}
                    assert 'state=valid' in result['health_after']['df']
                    assert 'layout=ok' in result['health_after']['mpu status']
                    assert 'CRASH none' in result['health_after']['crash show']
            except BaseException as error:
                result['cleanup_error'] = repr(error); result['status'] = 'FAIL'
                raise
            finally:
                port.close(); save(out / 'report.json', result)
        save(out / 'report.json', result)
    assert result['status'] == 'PASS'
    print('Real BASIC/FOCAL compiler A/B and all original-state restoration PASS', flush=True)

if __name__ == '__main__': main()
