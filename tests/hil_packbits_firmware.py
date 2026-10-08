#!/usr/bin/env python3
"""Compare real resident PackBits/USB-frame preparation and host delivery.

Flashes two prepared, source-matched qualification images on one pinned MCU,
then restores the exact original sealed image. One reserved fixture APP is
removed, C6 content fingerprints and calculator RAM are verified unchanged.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import statistics
import struct
import subprocess
import time
import zlib

from hil_c5_stack import read_file
from hil_c6_system_bootstrap import write_file
from hil_multi_device_identity import parse_identity
from hil_portable_apps import ScreenPort, cobs_decode
from hil_usb_disk_transaction import listing_entries

REMOTE = '/PACKCHK.APP'
CASES = ('blank', 'cursor', 'mixed', 'random', 'alternating', 'white', 'rendered_text')
DIGITS_CLASSIC = (4, 9, 8, 7, 14, 13, 12, 19, 18)
PROFILE = re.compile(r'(?m)^PROF ([\w.]+) n=(\d+) min=(\d+) avg=(\d+) max=(\d+) total=(\d+)\r?$')


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def firmware_info(path):
    data = path.read_bytes()
    for at in range(len(data) - 39):
        if data[at:at+8] != b'MK61FWC\0': continue
        magic, version, size, address, length, crc, build, profile, flags, reserved = \
            struct.unpack_from('<8sHH7I', data, at)
        if (version, size, address, length, crc, flags, reserved) != \
           (1, 40, 0x08000000, len(data), build, 1, 0): continue
        raw = bytearray(data)
        raw[at+20:at+28] = bytes(8)
        if zlib.crc32(raw) & 0xffffffff != crc: continue
        return {'path': str(path.resolve()), 'bytes': length, 'footer': at,
                'build': f'{build:08X}', 'sha256': hashlib.sha256(data).hexdigest()}
    raise AssertionError(f'unsealed or invalid firmware: {path}')


def identity(port, args, build=None):
    value = parse_identity(port.command('identity'))
    assert value.public == args.public_id.upper() and value.usb == args.usb_serial
    assert value.profile == 'classic-v3-uc1609'
    if build: assert value.build == build, (value, build)
    return value


def connect(args, build):
    deadline = time.monotonic() + 30
    while True:
        port = None
        try:
            port = ScreenPort(args.port)
            identity(port, args, build)
            return port
        except (OSError, TimeoutError):
            if port is not None: port.close()
            if time.monotonic() >= deadline: raise
            time.sleep(.15)
        except BaseException:
            if port is not None: port.close()
            raise


def flash(args, target, report_path):
    old = None
    try:
        with ScreenPort(args.port) as port:
            old = identity(port, args)
            port.drain()
            port.write_line('dfu')
            time.sleep(.2)
    except FileNotFoundError:
        # An explicitly verified incomplete download leaves the same MCU in
        # ROM DFU. Its pinned serial below also allows finalizer recovery.
        pass
    deadline = time.monotonic() + 15
    while True:
        listing = subprocess.run([str(args.dfu_util), '-l'], capture_output=True,
                                 text=True, timeout=8)
        if '[0483:df11]' in listing.stdout and \
           f'serial="{args.usb_serial}"' in listing.stdout: break
        if time.monotonic() >= deadline: raise TimeoutError('pinned DFU absent')
        time.sleep(.2)
    command = [str(args.dfu_util), '-d', '0483:df11', '-S', args.usb_serial,
               '-a', '0', '-s', '0x08000000:leave', '-D', target['path']]
    try:
        uploaded = subprocess.run(command, capture_output=True, text=True, timeout=180)
        download = {'returncode': uploaded.returncode, 'stdout': uploaded.stdout,
                    'stderr': uploaded.stderr, 'timed_out': False}
    except subprocess.TimeoutExpired as error:
        # Some macOS DFU leaves wait after the transfer. Running-MCU identity
        # plus full image CRC confirms success independently; no blind retry.
        download = {'timed_out': True,
                    'stdout': (error.stdout or b'').decode(errors='replace'),
                    'stderr': (error.stderr or b'').decode(errors='replace')}
    result = {'status': 'VERIFYING', 'old': asdict(old) if old else None, 'download': download}
    save(report_path, result)
    with connect(args, target['build']) as port:
        result['identity'] = asdict(identity(port, args, target['build']))
        result['df'] = port.command('df', timeout=15)
        assert 'FIRMWARE CRC state=valid' in result['df']
        assert 'actual=0x'+target['build'] in result['df']
        result['crash'] = port.command('crash show')
        assert 'CRASH none' in result['crash']
    result['status'] = 'PASS'
    save(report_path, result)
    print('Resident installed and verified:', target['build'], flush=True)


def fingerprint(port):
    files, directories = {}, []
    pending = ['/']
    while pending:
        parent = pending.pop()
        for entry in listing_entries(port.command(f'ls "{parent}"', timeout=20)):
            fields = entry.split('\t')
            name = fields[-1].rstrip('/')
            assert name and '/' not in name and '"' not in name
            path = parent.rstrip('/') + '/' + name
            if fields[0] == 'd':
                directories.append(path)
                pending.append(path)
            else:
                payload = read_file(port, path)
                files[path] = {'bytes': len(payload),
                               'sha256': hashlib.sha256(payload).hexdigest()}
    return {'files': files, 'directories': sorted(directories)}


class MeasurePort(ScreenPort):
    def __init__(self, path):
        super().__init__(path)
        self.frame_metrics = []
        self.frame_wire_bytes = 0
        self.frame_started = 0
    def receive_packet(self, encoded):
        raw = cobs_decode(encoded)
        kind = raw[3]
        if kind == 0x20:
            self.frame_started = time.perf_counter()
            self.frame_wire_bytes = 0
        if kind in (0x20, 0x21, 0x22):
            self.frame_wire_bytes += len(encoded) + 2
        super().receive_packet(encoded) # packet and full-frame CRC verification
        if kind == 0x22:
            self.frame_metrics.append({'received': time.perf_counter(),
                'begin_to_end_seconds': time.perf_counter() - self.frame_started,
                'wire_bytes': self.frame_wire_bytes})


def stable_pixels(frame):
    # Disk overlay has independent lifecycle, so exclude its reserved 16x16
    # area for the cross-firmware pixel oracle, keeping transport CRCs intact.
    return frame[:176] + frame[192:368] + frame[384:]


def expected_bitmap(kind):
    frame = bytearray(1536)
    random = 0x61F411
    for i in range(len(frame)):
        if kind == 0: value = 0
        elif kind == 1: value = 255 if i % 192 == 95 else 0
        elif kind == 2: value = 0 if i % 32 < 16 else i % 7 + 1
        elif kind == 3:
            random ^= (random << 13) & 0xffffffff
            random ^= random >> 17
            random ^= (random << 5) & 0xffffffff
            value = random & 255
        elif kind == 4: value = 255 if i & 1 else 0
        else: value = 255
        frame[i] = value
    return bytes(frame)


def one_frame(port):
    start = len(port.frames)
    sent = time.perf_counter()
    port.send(0x16) # REQUEST_KEYFRAME, same immutable image for every sample
    deadline = time.monotonic() + 3
    while len(port.frames) == start:
        port.pump(.005)
        if time.monotonic() >= deadline: raise TimeoutError('frame absent')
    assert len(port.frames) == start + 1, 'unexpected animated/background frame'
    result = dict(port.frame_metrics[-1])
    result['request_to_end_seconds'] = result['received'] - sent
    return port.frames[-1], result


def check_calculator_restore(port):
    expected, _ = one_frame(port)
    expected_pixels = stable_pixels(expected)
    for detach_in_bitmap in (False, True):
        opened = False
        try:
            port.open(REMOTE)
            opened = True
            port.pump(.15)
            port.key(DIGITS_CLASSIC[0])
            port.pump(.1)
            bitmap, _ = one_frame(port)
            assert stable_pixels(bitmap) == stable_pixels(expected_bitmap(0))
            if detach_in_bitmap:
                port.send(0x13)
                port.attached = False
                port.pump(.1)
                port.attach_waiting()
                restored, _ = one_frame(port)
                assert stable_pixels(restored) == expected_pixels, 'calculator role lost during bitmap detach'
            port.close_app()
            opened = False
            restored, _ = one_frame(port)
            assert stable_pixels(restored) == expected_pixels, 'calculator role lost after graphics_end'
        finally:
            if opened:
                if not port.attached: port.attach_waiting()
                port.close_app()
    return hashlib.sha256(expected_pixels).hexdigest()


def measure(args, variant, target, out, reference=None):
    result = {'status': 'RUNNING', 'build': target['build'], 'cases': {}}
    foreground = False
    with MeasurePort(args.port) as port:
        identity(port, args, target['build'])
        try:
            port.attach()
            result['calculator_restore_sha256'] = check_calculator_restore(port)
            print(variant, 'calculator bitmap exit and detach pixel restoration PASS', flush=True)
            for kind, name in enumerate(CASES):
                samples = []
                digest = None
                for run in range(args.runs):
                    # REQUEST itself maintains the heartbeat. Avoid PONG packets
                    # contaminating the ten outgoing packets per measured frame.
                    port.next_ping = time.monotonic() + 1000
                    foreground = True
                    port.open(REMOTE)
                    port.pump(.15)
                    assert port.frames and b'Open failed!' not in port.text
                    port.key(DIGITS_CLASSIC[kind])
                    port.pump(.1)
                    frame, _ = one_frame(port)
                    pixels = stable_pixels(frame)
                    if kind < 6: assert pixels == stable_pixels(expected_bitmap(kind)), name
                    current_digest = hashlib.sha256(pixels).hexdigest()
                    if digest: assert digest == current_digest, name
                    digest = current_digest
                    if reference: assert digest == reference['cases'][name]['pixel_sha256'], name
                    (out/f'{variant}-{name}.bin').write_bytes(frame)
                    # Ordinary APP blocks terminal command dispatch. The pinned
                    # fixture invokes the exact qualification image's start/stop
                    # callbacks with keys 7/8, guarded by its sealed build ID.
                    port.key(DIGITS_CLASSIC[7])
                    timings = []
                    for _ in range(args.frames):
                        actual, timing = one_frame(port)
                        assert stable_pixels(actual) == pixels, name
                        timings.append(timing)
                    port.key(DIGITS_CLASSIC[8])
                    port.close_app()
                    foreground = False
                    profile = port.command('prof stop')
                    points = {name: {'n': int(n), 'min': int(lo), 'avg': int(avg),
                                    'max': int(hi), 'total': int(total)}
                              for name,n,lo,avg,hi,total in PROFILE.findall(profile)}
                    assert f'clock=96000000' in profile
                    for point, count in (('usb.packbits', 8), ('usb.rect', 8),
                                         ('usb.prepare', 1), ('usb.packet', 10)):
                        assert points[point]['n'] == args.frames * count, (name, point, points)
                    cpu = sum(points[p]['total'] for p in
                              ('usb.prepare','usb.rect','usb.packet')) / args.frames
                    samples.append({'points': points, 'cpu_preparation_cycles_per_frame': cpu,
                        'packbits_cycles_per_frame': points['usb.packbits']['total']/args.frames,
                        'request_to_end_median_seconds': statistics.median(
                            x['request_to_end_seconds'] for x in timings),
                        'wire_bytes_per_frame': sorted(set(x['wire_bytes'] for x in timings)),
                        'timings': timings})
                    (out/f'{variant}-{name}-{run}-prof.txt').write_text(profile)
                    print(variant, name, f'run {run+1}: CPU/frame={cpu:.1f} '
                          f'pack/frame={samples[-1]["packbits_cycles_per_frame"]:.1f}', flush=True)
                result['cases'][name] = {'pixel_sha256': digest, 'samples': samples}
                save(out/f'{variant}-report.json', result)
            result['status'] = 'PASS'
        finally:
            try:
                if foreground and port.attached: port.close_app()
            finally:
                if port.attached:
                    port.send(0x13)
                    port.pump(.2)
                (out/f'{variant}-terminal.txt').write_bytes(port.text)
                save(out/f'{variant}-report.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--public-id', required=True)
    parser.add_argument('--usb-serial', required=True)
    parser.add_argument('--dfu-util', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--restore', type=Path, required=True)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--frames', type=int, default=32)
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--resume', action='store_true',
                        help='resume recorded fixture/state after verified baseline recovery')
    args = parser.parse_args()
    assert 4 <= args.frames <= 128 and 2 <= args.runs <= 5
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    binaries = {name:firmware_info(getattr(args,name))
                for name in ('baseline','candidate','restore')}
    save(out/'images.json', binaries)
    # Preserve an independent local copy before touching the MCU.
    backup = out/'original-firmware.bin'
    backup.write_bytes(args.restore.read_bytes())
    assert firmware_info(backup)['sha256'] == binaries['restore']['sha256']
    binaries['restore']['path'] = str(backup)
    installed = flashed = args.resume
    results = {}
    if args.resume:
        before = json.loads((out/'state-before.json').read_text())
        content_before = json.loads((out/'content-before.json').read_text())
        with ScreenPort(args.port) as port:
            identity(port, args, binaries['baseline']['build'])
            assert read_file(port, REMOTE) == args.app.read_bytes()
    else:
        with ScreenPort(args.port) as port:
            identity(port, args, binaries['restore']['build'])
            before = {c:port.command(c,timeout=15) for c in ('reg','stk','dump','pwd','df')}
            content_before = fingerprint(port)
            assert REMOTE.casefold() not in {p.casefold() for p in content_before['files']}
            save(out/'state-before.json', before)
            save(out/'content-before.json', content_before)
    # A firmware experiment resets volatile RAM. Accept only the recorded idle
    # calculator state, rather than erasing unrelated values or a program.
    numbers = re.findall(r'=\s*([+\-]?\d+\.\d+)\s+([+\-]?\d+)',
                         before['reg'] + before['stk'])
    assert len(numbers) == 20 and all(float(n) == 0 for n,e in numbers), \
        'nonempty calculator registers/stack; preserve them before flashing'
    codes = re.findall(r'\b[0-9A-F]{2}\b', before['dump'].split('\r\n',1)[1])
    assert len(codes) == 105 and set(codes) == {'00'}, 'program memory is not empty'
    assert re.search(r'IP\s*=\s*0\r?$', before['stk'], re.M)
    try:
        if not args.resume:
            with ScreenPort(args.port) as port:
                identity(port, args, binaries['restore']['build'])
                write_file(port, REMOTE, args.app.read_bytes())
                installed = True
                assert read_file(port, REMOTE) == args.app.read_bytes()
        for variant in ('baseline','candidate'):
            flashed = True
            if not (args.resume and variant == 'baseline'):
                flash(args, binaries[variant], out/f'{variant}-flash.json')
            results[variant] = measure(args, variant, binaries[variant], out,
                                       results.get('baseline') if variant=='candidate' else None)
    finally:
        if flashed: flash(args, binaries['restore'], out/'restore-flash.json')
        with connect(args, binaries['restore']['build']) as port:
            if installed:
                assert read_file(port, REMOTE) == args.app.read_bytes()
                removed = port.command(f'rm "{REMOTE}"',timeout=15)
                assert 'Removed 1 entry.' in removed, removed
            # The recorded RAM in this session is the reset calculator state;
            # verify it exactly, rather than claiming general RAM persistence.
            after = {c:port.command(c,timeout=15) for c in ('reg','stk','dump','pwd','df','crash show','mpu status')}
            for c in ('reg','stk','dump','pwd'): assert before[c] == after[c], (c,before[c],after[c])
            assert 'CRASH none' in after['crash show']
            content_after = fingerprint(port)
            assert content_before == content_after, 'C6 content changed'
            save(out/'state-after.json', after)
            save(out/'content-after.json', content_after)
            print('Exact original firmware, calculator RAM and all C6 files restored', flush=True)
    save(out/'report.json', {'status':'PASS','images':binaries,'results':results,
         'frames_per_run':args.frames,'runs':args.runs,
         'timer':'DWT CYCCNT at 96 MHz; real resident code in internal Flash',
         'cpu_scope':'snapshot/CRC + rectangle encode + packet CRC/COBS; PACKBITS is nested in rectangle and is not double-counted',
         'wall_scope':'host REQUEST_KEYFRAME to CRC-verified FRAME_END; includes transport and host scheduling',
         'restored':True})


if __name__ == '__main__':
    main()
