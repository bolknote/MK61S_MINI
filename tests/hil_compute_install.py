#!/usr/bin/env python3
"""Install one sealed Classic image with full readback and current tail preservation.

No old firmware restoration. The ROM transfer is addressed by its exact serial;
CDC binding, running CRC and the sealed image identify both endpoints.
"""
import argparse
import importlib.util
import json
import subprocess
import time
from pathlib import Path
from hil_classic_cdc_guard import current_binding, require_no_holders
from hil_compute_clock import connect
from hil_packbits_firmware import firmware_info
from hil_system_memory import valid_classic_dfu_listing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--current-build', required=True)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    target = firmware_info(args.image)
    port_path = '/dev/cu.usbmodem2068336B47311'
    tool = '/Users/bolk/Library/Arduino15/packages/arduino/tools/dfu-util/0.11.0-arduino5/dfu-util'
    require_no_holders(current_binding(port_path))
    with connect(port_path, args.current_build) as port:
        (args.output / 'identity-before.txt').write_text(port.command('identity'))
        port.write_line('dfu')
        time.sleep(.2)
    deadline = time.monotonic() + 15
    while True:
        listed = subprocess.run([tool, '-l'], capture_output=True, text=True, timeout=8)
        if valid_classic_dfu_listing(listed.stdout, listed.stderr, listed.returncode):
            break
        if time.monotonic() >= deadline:
            raise TimeoutError('exact Classic ROM DFU descriptor absent')
        time.sleep(.2)
    (args.output / 'dfu-listing.txt').write_text(listed.stdout + listed.stderr)
    common = [tool, '-d', '0483:df11', '-S', '2068336B4731', '-a', '0']

    def transfer(name, arguments, timeout=120):
        with (args.output / (name + '.log')).open('w') as log:
            result = subprocess.run(common + arguments, stdout=log,
                                    stderr=subprocess.STDOUT, timeout=timeout)
        assert result.returncode == 0, (name, result.returncode)

    transfer('read-current', ['-s', '0x08000000:524288', '-U', str(args.output / 'current.bin')])
    current = (args.output / 'current.bin').read_bytes()
    assert len(current) == 524288
    script = Path(__file__).resolve().parents[1] / 'dev/lib/seal-firmware-elf.py'
    spec = importlib.util.spec_from_file_location('firmware_seal', script)
    seal = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seal)
    offset, fields = seal.unique_footer(current, 'current internal Flash')
    seal.validate_bin(current[:fields[4]], offset, fields)
    assert f'{fields[6]:08X}' == args.current_build
    data = args.image.read_bytes()
    if len(data) > fields[4]:
        extension = current[fields[4]:len(data)]
        # A prior larger diagnostic image may have left this exact suffix.
        # Accept only erased bytes or bytes already identical to the target;
        # arbitrary nonempty tail data must still stop the installation.
        assert all(old == 255 or old == new for old, new in
                   zip(extension, data[fields[4]:])), 'new code overlaps nonempty internal data'
    merged = bytearray(current)
    # Bytes owned by a larger previous resident are code, not user tail.
    merged[:max(fields[4], len(data))] = b'\xFF' * max(fields[4], len(data))
    merged[:len(data)] = data
    # Restore any non-erased tail in the same download, but do not spend
    # transfer time writing the erased remainder of the final sector.
    length = max(len(data), len(merged.rstrip(b'\xFF')))
    (args.output / 'transfer.bin').write_bytes(merged[:length])
    print('Pinned Classic; writing', length, 'bytes, target', target['build'], flush=True)
    transfer('download', ['-s', '0x08000000', '-D', str(args.output / 'transfer.bin')])
    transfer('readback', ['-s', '0x08000000:524288', '-U', str(args.output / 'readback.bin')])
    assert (args.output / 'readback.bin').read_bytes() == bytes(merged), 'full internal readback mismatch'
    transfer('leave', ['-s', '0x08000000:leave', '-U', str(args.output / 'leave.bin'), '-Z', '1'])
    with connect(port_path, target['build']) as port:
        health = {name: port.command(name, timeout=15)
                  for name in ('identity', 'df', 'crash show', 'mpu status')}
        assert 'FIRMWARE CRC state=valid' in health['df']
        assert 'CRASH none' in health['crash show'] and 'layout=ok' in health['mpu status']
    (args.output / 'health.json').write_text(json.dumps(health, indent=2) + '\n')
    print('Exact full readback and running firmware CRC PASS:', target['build'], flush=True)


if __name__ == '__main__':
    main()
