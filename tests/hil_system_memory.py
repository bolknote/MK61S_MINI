#!/usr/bin/env python3
"""Compare global memcpy/memcmp in matched residents on the pinned Classic.

One unchanged public-runtime APP measures the actual Flash functions. A valid
original image is required for recovery. Candidate installation is explicit;
any failed check restores the original image and removes the temporary APP.
"""
import argparse
from contextlib import ExitStack
from dataclasses import asdict
import errno
import hashlib
import json
from pathlib import Path
import re
import shutil
import statistics
import struct
import subprocess
import sys
import time

from hil_c6_system_bootstrap import read_file, write_file
from hil_multi_device_identity import parse_identity
from hil_packbits_firmware import firmware_info, fingerprint, stable_pixels
from hil_portable_apps import ScreenPort
from hil_rtc_alarm import warm_reset

REMOTE = '/MEMCHECK.APP'
PUBLIC = 'AEB505B6E0067623'
SERIAL = '2068336B4731'
PROFILE = 'classic-v3-uc1609'
LENGTHS = (0, 1, 2, 3, 4, 7, 8, 15, 16, 31, 32, 63, 64, 128, 256, 512, 1024, 4096)
PATTERNS = ('equal', 'different_first', 'different_last')
KERNELS = ('memcmp', 'memcpy', 'cache_update')
STATE_COMMANDS = ('reg', 'stk', 'dump', 'pwd')


def save(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')


class ExclusiveScreenPort(ScreenPort):
    """Port already owns the advisory lock and TIOCEXCL for its lifetime.

    Repeating TIOCEXCL on the same descriptor returns EBUSY on macOS.
    Keep this name for callers, using Port's acquisition and cleanup.
    """


def connect(path, build=None, wait=30):
    deadline = time.monotonic() + wait
    while True:
        port = None
        try:
            port = ExclusiveScreenPort(path)
            current = parse_identity(port.command('identity', timeout=15))
            assert (current.public, current.usb, current.profile) == (PUBLIC, SERIAL, PROFILE), current
            if build:
                assert current.build == build, (current.build, build)
            return port
        except OSError as error:
            if port is not None:
                port.close()
            if error.errno not in (errno.EBUSY, errno.ENOENT) or time.monotonic() >= deadline:
                raise
            time.sleep(.3)
        except TimeoutError:
            if port is not None:
                port.close()
            if time.monotonic() >= deadline:
                raise
            time.sleep(.3)
        except BaseException:
            if port is not None:
                port.close()
            raise


def health(port, build):
    value = {c: port.command(c, timeout=15) for c in ('df', 'crash show', 'mpu status') + STATE_COMMANDS}
    assert 'FIRMWARE CRC state=valid' in value['df'] and 'actual=0x' + build in value['df']
    assert 'CRASH none' in value['crash show'], value['crash show']
    return value


def require_empty(state):
    numbers = re.findall(r'=\s*([+\-]?\d+\.\d+)\s+([+\-]?\d+)', state['reg'] + state['stk'])
    assert len(numbers) == 20 and all(float(n) == 0 for n, e in numbers), 'flashing requires empty calculator'
    codes = re.findall(r'\b[0-9A-F]{2}\b', state['dump'].split('\r\n', 1)[1])
    assert len(codes) == 105 and set(codes) == {'00'} and '\r\n/\r\n' in state['pwd']


def flash(args, target, output):
    previous = None
    try:
        with connect(args.port, wait=0) as port:
            previous = asdict(parse_identity(port.command('identity')))
            port.drain()
            port.write_line('dfu')
            time.sleep(.2)
    except FileNotFoundError:
        pass  # Recovery is allowed only through the same pinned ROM DFU serial.
    deadline = time.monotonic() + 15
    while True:
        listing = subprocess.run([str(args.dfu_util), '-l'], capture_output=True, text=True, timeout=8)
        if '[0483:df11]' in listing.stdout and f'serial="{SERIAL}"' in listing.stdout:
            break
        if time.monotonic() >= deadline:
            raise TimeoutError('pinned Classic DFU absent')
        time.sleep(.2)
    command = [str(args.dfu_util), '-d', '0483:df11', '-S', SERIAL,
               '-a', '0', '-s', '0x08000000:leave', '-D', target['path']]
    try:
        downloaded = subprocess.run(command, capture_output=True, text=True, timeout=60)
        transfer = {'returncode': downloaded.returncode, 'stdout': downloaded.stdout,
                    'stderr': downloaded.stderr, 'timed_out': False}
    except subprocess.TimeoutExpired as error:
        transfer = {'timed_out': True, 'stdout': (error.stdout or b'').decode(errors='replace'),
                    'stderr': (error.stderr or b'').decode(errors='replace')}
    result = {'status': 'VERIFYING', 'old': previous, 'firmware': target, 'transfer': transfer}
    save(output, result)
    with connect(args.port, target['build']) as port:
        result['identity'] = asdict(parse_identity(port.command('identity')))
        result['health'] = health(port, target['build'])
    result['status'] = 'PASS'
    save(output, result)
    print('Resident Flash CRC verified:', target['build'], flush=True)


def code_oracle(binary, elf, toolchain):
    text = subprocess.check_output([str(toolchain / 'arm-none-eabi-nm'), '-P', '-S', str(elf)], text=True)
    symbols = {line.split()[0]: line.split()[1:] for line in text.splitlines() if len(line.split()) >= 3}
    image = binary.read_bytes()
    result = {}
    for name in ('memcmp', 'memcpy'):
        kind, value = symbols[name][:2]
        assert kind == 'T', (name, kind)  # One strong, global implementation.
        address = int(value, 16)
        assert 0x08000000 <= address < 0x08080000
        result[name] = {'address': address | 1,
                        'code_hex': image[address - 0x08000000:address - 0x08000000 + 64].hex()}
    return result


def parse(frame, page, oracle):
    data = stable_pixels(frame)
    magic, version, actual, count, failures, cmp, cpy, length, pattern, pages, demcr, control, sink, a, b, c = \
        struct.unpack_from('<4s15I', data)
    assert (magic, version, actual, failures, pages, a, b, c) == (b'SMC1', 1, page, 0, len(LENGTHS) * 3, 0, 0, 0)
    assert (length, pattern, count) == (LENGTHS[page // 3], page % 3, 48 if page % 3 == 0 else 32)
    assert cmp == oracle['memcmp']['address'] and cpy == oracle['memcpy']['address']
    for i, name in enumerate(('memcmp', 'memcpy')):
        assert data[1376 + i * 64:1440 + i * 64].hex() == oracle[name]['code_hex'], name
    rows = []
    for i in range(count):
        kernel, p, sa, ta, iterations, minimum, median, maximum = struct.unpack_from('<4B4I', data, 64 + i * 20)
        assert kernel < 3 and p == pattern and sa < 4 and ta < 4 and iterations > 0
        assert minimum <= median <= maximum
        rows.append({'kernel': KERNELS[kernel], 'pattern': PATTERNS[pattern], 'bytes': length,
                     'source_alignment': sa, 'target_alignment': ta, 'iterations': iterations,
                     'min_cycles': minimum / iterations, 'median_cycles': median / iterations,
                     'max_cycles': maximum / iterations})
    assert len({(r['kernel'], r['source_alignment'], r['target_alignment']) for r in rows}) == count
    return {'page': page, 'demcr_before': demcr, 'dwt_control_before': control, 'sink': sink, 'rows': rows}


def measure(args, name, target, oracle, original_files, original_state, calculator, output):
    output.mkdir()
    runs = []
    installed = foreground = False
    with ExitStack() as contexts:
        port = contexts.enter_context(connect(args.port, target['build']))
        before = health(port, target['build'])
        for c in STATE_COMMANDS:
            assert before[c] == original_state[c], c
        try:
            write_file(port, REMOTE, args.app.read_bytes())
            installed = True
            read_file(port, REMOTE, args.app.read_bytes())
            port.attach()
            port.pump(.2)
            assert port.frames and stable_pixels(port.frames[-1]) == calculator
            for run in range(args.runs):
                start = len(port.frames)
                foreground = True
                port.open(REMOTE)
                batches = []
                for page in range(len(LENGTHS) * 3):
                    deadline = time.monotonic() + 40
                    frame = None
                    while time.monotonic() < deadline:
                        port.pump(.03)
                        frame = next((f for f in port.frames[start:] if f.startswith(b'SMC1') and
                                      struct.unpack_from('<I', f, 8)[0] == page), None)
                        if frame is not None:
                            break
                    assert frame is not None, f'report absent: {port.text[-1400:]!r}'
                    batches.append(parse(frame, page, oracle))
                    (output / f'frame-{run}-{page}.bin').write_bytes(frame)
                    if page % 3 == 2:
                        print(name, f'run {run + 1}: {LENGTHS[page // 3]} bytes, three patterns/all 16 alignments PASS', flush=True)
                    start = len(port.frames)
                    if page + 1 < len(LENGTHS) * 3:
                        port.key(9)  # Classic digit 1.
                port.close_app()
                foreground = False
                port.send(0x16)
                port.pump(.15)
                assert stable_pixels(port.frames[-1]) == calculator, 'calculator face changed'
                runs.append(batches)
                save(output / 'runs.json', runs)
            assert len({(b['demcr_before'], b['dwt_control_before']) for run in runs for b in run}) == 1
        finally:
            try:
                if foreground and port.attached:
                    port.close_app()
            finally:
                if port.attached:
                    port.send(0x13)
                    port.pump(.2)
                for c in STATE_COMMANDS:
                    assert port.command(c, timeout=15) == original_state[c], c
                if installed:
                    # Release retained APP caches before the removal transaction.
                    fresh, path, elapsed = warm_reset(port, port.path, PUBLIC)
                    fresh.close()
                    port = contexts.enter_context(connect(path, target['build']))
                    read_file(port, REMOTE, args.app.read_bytes())
                    removed = port.command(f'rm "{REMOTE}"', timeout=15)
                    assert 'Removed 1 entry.' in removed, removed
                after = health(port, target['build'])
                for c in STATE_COMMANDS:
                    assert after[c] == original_state[c], c
                files = fingerprint(port)
                assert files == original_files, 'original storage content changed'
                save(output / 'content-after.json', files)
                (output / 'terminal.txt').write_bytes(port.text)
                save(output / 'report.json', {'status': 'PASS' if len(runs) == args.runs else 'INCOMPLETE',
                    'firmware': target, 'code_oracle': oracle, 'before': before, 'after': after,
                    'runs': runs, 'original_file_hashes_preserved': len(files['files'])})
    return runs


def summarize(baseline, candidate):
    def grouped(runs):
        rows = {}
        for run in runs:
            for batch in run:
                for row in batch['rows']:
                    key = (row['bytes'], row['pattern'], row['kernel'], row['source_alignment'], row['target_alignment'])
                    rows.setdefault(key, []).append(row['median_cycles'])
        return {k: statistics.median(v) for k, v in rows.items()}
    old, new = grouped(baseline), grouped(candidate)
    assert old.keys() == new.keys()
    result = []
    for length in LENGTHS:
        for pattern in PATTERNS:
            for kernel in KERNELS:
                keys = [k for k in old if k[:3] == (length, pattern, kernel)]
                if not keys:
                    continue
                aligned = (length, pattern, kernel, 0, 0)
                result.append({'bytes': length, 'pattern': pattern, 'kernel': kernel,
                    'baseline_aligned_cycles': old[aligned], 'candidate_aligned_cycles': new[aligned],
                    'aligned_speedup': old[aligned] / new[aligned],
                    'speedup_range_all_alignments': [min(old[k] / new[k] for k in keys), max(old[k] / new[k] for k in keys)],
                    'worst_delta_cycles_all_alignments': max(new[k] - old[k] for k in keys)})
    return result


def chess_measure(args, target, output):
    # Keep the checked-in game/UI oracle: book off, level 2, 420 nodes,
    # complete e2-e3 board. Adapt only its serial transport/reset banner.
    import hil_turochamp_performance as chess

    class ExclusiveTimedPort(chess.TimedScreenPort, ExclusiveScreenPort):
        pass

    old_port, old_timed, old_identify, old_argv = chess.Port, chess.TimedScreenPort, chess.identify, sys.argv

    def identify_after_boot(port, options):
        try:
            return old_identify(port, options)
        except AssertionError as error:
            if 'not a canonical MK61 identity response:' not in str(error) or 'MK61s-Classic-V3 ver.' not in str(error):
                raise
            time.sleep(.3)
            return old_identify(port, options)

    chess.Port = ExclusiveScreenPort
    chess.TimedScreenPort = ExclusiveTimedPort
    chess.identify = identify_after_boot
    sys.argv = ['hil_turochamp_performance.py', '--port', args.port, '--public-id', PUBLIC,
                '--build-id', target['build'], '--output-dir', str(output), '--runs', str(args.runs),
                '--reset-before']
    try:
        chess.main()
    finally:
        chess.Port, chess.TimedScreenPort, chess.identify, sys.argv = old_port, old_timed, old_identify, old_argv
    result = json.loads((output / 'report.json').read_text())
    assert result['result'] == 'PASS'
    # The preflight required a wholly empty calculator, so a reset restores
    # its initial RAM and releases the game's retained code caches.
    with connect(args.port, target['build']) as port:
        fresh, path, elapsed = warm_reset(port, port.path, PUBLIC)
        fresh.close()
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port', required=True)
    p.add_argument('--dfu-util', type=Path, required=True)
    p.add_argument('--toolchain-bin', type=Path, required=True)
    p.add_argument('--app', type=Path, required=True)
    p.add_argument('--original', type=Path, required=True)
    for name in ('baseline', 'candidate'):
        p.add_argument('--' + name, type=Path, required=True)
        p.add_argument('--' + name + '-elf', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--runs', type=int, default=3)
    p.add_argument('--install-candidate', action='store_true')
    p.add_argument('--with-chess', action='store_true', help='also time cold/warm installed Turochamp UI')
    p.add_argument('--reuse-baseline', type=Path,
                   help='reuse a completed identical baseline after tuning only the candidate')
    p.add_argument('--recover-original', type=Path,
                   help='recover original after manual DFU entry; directory of saved preflight fingerprints/state')
    args = p.parse_args()
    assert 1 <= args.runs <= 10
    output = args.output_dir.resolve()
    output.mkdir(parents=True)
    targets = {name: firmware_info(getattr(args, name)) for name in ('original', 'baseline', 'candidate')}
    if args.recover_original:
        flash(args, targets['original'], output / 'recover-flash.json')
        saved_files = json.loads((args.recover_original / 'content-before.json').read_text())
        saved_state = json.loads((args.recover_original / 'state-before.json').read_text())
        with connect(args.port, targets['original']['build']) as port:
            restored = health(port, targets['original']['build'])
            assert fingerprint(port) == saved_files
            for c in STATE_COMMANDS:
                assert restored[c] == saved_state[c], c
            fresh, path, elapsed = warm_reset(port, port.path, PUBLIC)
            fresh.close()
        with connect(path, targets['original']['build']) as port:
            restored = health(port, targets['original']['build'])
            for c in STATE_COMMANDS:
                assert restored[c] == saved_state[c], c
        save(output / 'recovery.json', {'status': 'PASS', 'firmware': targets['original'],
                                      'health': restored, 'original_files_preserved': len(saved_files['files'])})
        print('Original recovered; all original files and calculator state preserved', flush=True)
        return
    oracles = {name: code_oracle(getattr(args, name), getattr(args, name + '_elf'), args.toolchain_bin)
               for name in ('baseline', 'candidate')}
    with connect(args.port, targets['original']['build']) as port:
        original_state = health(port, targets['original']['build'])
        require_empty(original_state)
        original_files = fingerprint(port)
        assert REMOTE.casefold() not in {s.casefold() for s in original_files['files']}
        port.attach()
        port.pump(.2)
        assert port.frames
        calculator = stable_pixels(port.frames[-1])
        port.send(0x13)
        port.pump(.2)
    shutil.copy2(args.original, output / 'original.bin')
    save(output / 'content-before.json', original_files)
    save(output / 'state-before.json', original_state)
    if args.reuse_baseline:
        old_files = json.loads((args.reuse_baseline / 'content-before.json').read_text())
        old_state = json.loads((args.reuse_baseline / 'state-before.json').read_text())
        old_baseline = json.loads((args.reuse_baseline / 'baseline/report.json').read_text())
        assert old_files == original_files
        assert old_baseline['status'] == 'PASS' and old_baseline['firmware']['sha256'] == targets['baseline']['sha256']
        assert old_baseline['code_oracle'] == oracles['baseline']
        assert len(old_baseline['runs']) == args.runs
        for c in STATE_COMMANDS:
            assert old_state[c] == original_state[c], c
    result = {'status': 'RUNNING', 'firmwares': targets, 'runs_per_firmware': args.runs,
              'app_sha256': hashlib.sha256(args.app.read_bytes()).hexdigest(), 'app_bytes': args.app.stat().st_size,
              'scope': 'DWT SRAM operations through actual global Flash helpers; 7 samples, '
                       'all 16 source/dest alignments. Primitive times, not NOR/USB/end-to-end firmware speed.'}
    save(output / 'report.json', result)
    completed = False
    try:
        runs = {}
        chess_runs = {}
        for name in ('baseline', 'candidate'):
            if name == 'baseline' and args.reuse_baseline:
                runs[name] = old_baseline['runs']
                if args.with_chess:
                    chess_runs[name] = json.loads((args.reuse_baseline / 'baseline-chess/report.json').read_text())
                    assert chess_runs[name]['result'] == 'PASS' and chess_runs[name]['build'] == targets[name]['build']
                result['reused_baseline'] = str(args.reuse_baseline.resolve())
                continue
            flash(args, targets[name], output / (name + '-flash.json'))
            runs[name] = measure(args, name, targets[name], oracles[name], original_files,
                                 original_state, calculator, output / name)
            if args.with_chess:
                chess_runs[name] = chess_measure(args, targets[name], output / (name + '-chess'))
        result['summary'] = summarize(runs['baseline'], runs['candidate'])
        if chess_runs:
            assert chess_runs['baseline']['runs'][0]['board_frame_sha256'] == chess_runs['candidate']['runs'][0]['board_frame_sha256']
            result['chess'] = chess_runs
            result['chess_comparison'] = {
                'cold_seconds': {k: v['runs'][0]['seconds'] for k, v in chess_runs.items()},
                'warm_median_seconds': {k: v['warm_median_seconds'] for k, v in chess_runs.items()},
                'cold_time_change_percent': 100 * (chess_runs['candidate']['runs'][0]['seconds'] / chess_runs['baseline']['runs'][0]['seconds'] - 1),
                'warm_time_change_percent': 100 * (chess_runs['candidate']['warm_median_seconds'] / chess_runs['baseline']['warm_median_seconds'] - 1)}
        result['original_file_hashes_preserved'] = len(original_files['files'])
        completed = True
    finally:
        if not completed or not args.install_candidate:
            flash(args, targets['original'], output / 'restore-flash.json')
        with connect(args.port, targets['candidate' if completed and args.install_candidate else 'original']['build']) as port:
            result['final_identity'] = asdict(parse_identity(port.command('identity')))
            result['final_health'] = health(port, result['final_identity']['build'])
            assert fingerprint(port) == original_files
            for c in STATE_COMMANDS:
                assert result['final_health'][c] == original_state[c], c
            fresh, path, elapsed = warm_reset(port, port.path, PUBLIC)
            fresh.close()
        with connect(path, result['final_identity']['build']) as port:
            result['final_health'] = health(port, result['final_identity']['build'])
            for c in STATE_COMMANDS:
                assert result['final_health'][c] == original_state[c], c
        result['status'] = 'PASS' if completed else 'INCOMPLETE'
        result['candidate_installed'] = completed and args.install_candidate
        save(output / 'report.json', result)
        print('Final firmware', result['final_identity']['build'],
              f'; all {len(original_files["files"])} original files/state preserved; MEMCHECK removed', flush=True)


if __name__ == '__main__':
    main()
