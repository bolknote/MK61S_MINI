#!/usr/bin/env python3
"""Matched buffer kernels on a physical STM32, without flashing firmware.

Install one reserved temporary APP, receive its DWT report via USB Screen,
then remove the APP and verify the original C6 listing and firmware identity.
Both sides execute from SRAM; these are kernel timings, not resident-Flash or
end-to-end UI/USB timings. No timing threshold is imposed on experiments.
"""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import struct
import time

from hil_c6_system_bootstrap import read_file, write_file
from hil_portable_apps import ScreenPort
from hil_rtc_alarm import warm_reset
from hil_usb_disk_transaction import listing_entries

KERNELS = ('valid_scalar', 'valid_dsp', 'valid_swar', 'strict_scalar',
           'strict_ascii', 'diff_scalar', 'diff_word',
           'packbits_scalar', 'packbits_word')
TEXT_CASES = ('ascii4', 'ascii16', 'ascii64', 'ascii256', 'ascii1024',
              'cyrillic1024', 'mixed1024', 'emoji1024', 'malformed1024')
FRAME_CASES = ('unchanged', 'cursor', 'mixed', 'random', 'alternating')
REMOTE = '/SIMDCHK.APP'


def parse_report(frame):
    payload = frame[:176] + frame[192:368] + frame[384:]
    magic, version, count, failures, address, control, optimization, checksum = \
        struct.unpack_from('<4s7I', payload)
    assert magic == b'BSC1' and version == 1 and count == 62
    assert failures == 0, f'kernel differential/DWT failures: {failures}'
    assert 0x20000000 <= address < 0x20020000, 'expected SRAM kernel'
    rows = []
    for i in range(count):
        kernel, dataset, alignment, _, iterations, minimum, median, maximum = \
            struct.unpack_from('<4B4I', payload, 32 + i * 20)
        assert kernel < len(KERNELS) and iterations and minimum <= median <= maximum
        cases = TEXT_CASES if kernel < 5 else FRAME_CASES
        rows.append({'kernel': KERNELS[kernel], 'case': cases[dataset],
                     'alignment': alignment, 'iterations': iterations,
                     'min_cycles': minimum / iterations,
                     'median_cycles': median / iterations,
                     'max_cycles': maximum / iterations})
    return {'code_address': hex(address), 'dwt_control_before': control,
            'optimization': 'O3' if optimization == 3 else 'Os',
            'checksum': checksum, 'rows': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--public-id', required=True)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--reset-after', action='store_true',
                        help='authorized warm reset before removing the probe; '
                             'releases retained APP/overlay caches')
    args = parser.parse_args()
    assert 1 <= args.runs <= 10
    args.output_dir.mkdir(parents=True, exist_ok=True)
    payload = args.app.read_bytes()
    assert payload and len(payload) < 16000
    runs = []
    installed = foreground = False
    with ExitStack() as contexts:
        port = contexts.enter_context(ScreenPort(args.port))
        identity = port.command('identity')
        assert f'public={args.public_id.upper()}' in identity, identity
        root = listing_entries(port.command('ls /'))
        assert not any(line.split('\t')[-1].casefold().split('.')[0] == 'simdchk'
                       for line in root), f'reserved path {REMOTE} already exists'
        before = {name: port.command(name, timeout=15)
                  for name in ('df', 'crash show', 'mpu status')}
        assert 'CRASH none' in before['crash show']
        try:
            write_file(port, REMOTE, payload)
            installed = True
            read_file(port, REMOTE, payload)
            port.attach()
            for run in range(args.runs):
                start = len(port.frames)
                foreground = True
                port.open(REMOTE)
                deadline = time.monotonic() + 25
                frame = None
                while time.monotonic() < deadline:
                    port.pump(.05)
                    frame = next((x for x in port.frames[start:]
                                  if x.startswith(b'BSC1')), None)
                    if frame is not None: break
                assert frame is not None, f'no benchmark report: {port.text[-1000:]!r}'
                result = parse_report(frame)
                runs.append(result)
                (args.output_dir / f'frame-{run}.bin').write_bytes(frame)
                port.close_app()
                foreground = False
                print(f"Run {run + 1}: 62 matched DWT kernels and differential checks PASS",
                      flush=True)
        finally:
            log = bytearray()
            try:
                try:
                    if foreground and port.attached: port.close_app()
                finally:
                    if port.attached:
                        port.send(0x13)
                        port.pump(.2)
                    if installed and args.reset_after:
                        log.extend(port.text)
                        next_port, path, _ = warm_reset(port, port.path, args.public_id)
                        next_port.close()
                        port = contexts.enter_context(ScreenPort(path))
                    if installed:
                        result = port.command(f'rm "{REMOTE}"', timeout=15)
                        assert 'Removed 1 entry.' in result, result
                    assert listing_entries(port.command('ls /')) == root, 'C6 listing changed'
                    after_identity = port.command('identity')
                    assert after_identity == identity, 'firmware or device identity changed'
                    after = {name: port.command(name, timeout=15)
                             for name in ('df', 'crash show', 'mpu status')}
                    assert 'CRASH none' in after['crash show']
                    assert 'FIRMWARE CRC state=valid' in after['df']
                    (args.output_dir / 'report.json').write_text(json.dumps({
                        'status': 'PASS' if len(runs) == args.runs else 'INCOMPLETE',
                        'identity': identity.strip(), 'before': before, 'after': after,
                        'app_bytes': len(payload), 'runs': runs,
                        'warm_reset_after': args.reset_after,
                        'restored': ['original C6 listing', 'firmware identity',
                                     'DWT control', 'display foreground'],
                        'scope': 'Physical STM32 DWT; matched code in SRAM, input in SRAM. '
                                 'No resident-Flash or end-to-end speed claim.'
                    }, indent=2) + '\n')
            finally:
                log.extend(port.text)
                (args.output_dir / 'terminal.txt').write_bytes(log)


if __name__ == '__main__':
    main()
