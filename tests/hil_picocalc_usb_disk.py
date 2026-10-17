#!/usr/bin/env python3
"""macOS PicoCalc USB round trip, using only uniquely named test files.

Verifies sources produced by hil_picocalc_services.py, writes one new BASIC
source through the mounted USB disk, safely ejects, then opens/runs it via
the device's Explorer. Never formats or erases a disk.
"""
import argparse
import json
import os
from pathlib import Path
import plistlib
import select
import subprocess
import termios
import time
import tty


def plist(*arguments):
    return plistlib.loads(subprocess.check_output(['diskutil', *arguments], timeout=30))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--sources-report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--write-test-file', action='store_true', required=True)
    args = parser.parse_args()
    sources = json.loads(args.sources_report.read_text())['sources']
    before = set(plist('list', '-plist', 'external', 'physical')['WholeDisks'])
    fd = os.open(args.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    old = termios.tcgetattr(fd)
    transcript = []

    def read_for(seconds):
        data = bytearray()
        end = time.monotonic()+seconds
        while time.monotonic()<end:
            if select.select([fd], [], [], max(0, end-time.monotonic()))[0]:
                chunk = os.read(fd, 16384)
                if not chunk:
                    raise RuntimeError('Pico disconnected')
                data += chunk
        text = data.decode('utf-8', errors='replace')
        transcript.append(text)
        print(text, end='', flush=True)
        return text

    def query():
        os.write(fd, b'\x05')
        return read_for(.4)

    def step(keys, expected):
        os.write(fd, keys)
        text = read_for(.2)
        end = time.monotonic()+10
        while time.monotonic()<end:
            text += query()
            if expected in text:
                return text
        raise RuntimeError('Expected '+expected)

    try:
        tty.setraw(fd)
        os.write(fd, b'\x1e')
        read_for(.2)
        status = query()
        if 'MK61S PICOCALC PICO-H' not in status or 'UI=CALCULATOR' not in status or 'SERVICE=CLOSED' not in status:
            raise RuntimeError('Start on PicoCalc calculator screen')
        step(b'\t'+bytes([0xB5])*6+bytes([0xB6])+b'\n', 'SERVICE=USB_DISK')
        whole = None
        end = time.monotonic()+45
        while time.monotonic()<end and not whole:
            for candidate in set(plist('list', '-plist', 'external', 'physical')['WholeDisks'])-before:
                info = plist('info', '-plist', candidate)
                if info.get('BusProtocol') == 'USB' and 'PicoCalc' in info.get('MediaName', ''):
                    whole = candidate
                    break
            if not whole:
                read_for(.5)
        if not whole:
            raise RuntimeError('PicoCalc microSD USB media did not appear')
        mount = None
        end = time.monotonic()+35
        while time.monotonic()<end and not mount:
            partitions = plist('list', '-plist', whole)['AllDisksAndPartitions'][0].get('Partitions', [])
            for part in partitions:
                info = plist('info', '-plist', part['DeviceIdentifier'])
                if info.get('MountPoint'):
                    mount = Path(info['MountPoint'])
                    break
            if not mount:
                read_for(.5)
        if not mount:
            raise RuntimeError('microSD partition was not mounted')
        checked = []
        for name, expected in sources.items():
            if not name.startswith('MK61S-HIL-') or Path(name).name != name:
                raise RuntimeError('Unexpected test filename in sources report')
            actual = (mount/name).read_text()
            if actual != expected:
                raise RuntimeError('USB file mismatch: '+name)
            checked.append(name)
        name = 'MK61S-USB-'+time.strftime('%Y%m%d-%H%M%S')+'.bas'
        returned = '10 .X=12345\n20 PRINT "USB ROUND TRIP"\n30 END\n'
        with (mount/name).open('x', encoding='utf-8', newline='\n') as file:
            file.write(returned)
            file.flush()
            os.fsync(file.fileno())
        subprocess.run(['diskutil', 'eject', whole], check=True)
        step(b'\n', 'SERVICE=CLOSED')
        step(bytes([0xB6])*2+b'\n', 'SERVICE=BROWSER')  # USB item 1 -> Explorer 3.
        step(b'/', 'SERVICE=PROMPT')
        step(name.encode('ascii')+b'\n', f'PATH=[/{name}]')
        status = query()
        if f'SOURCE={len(returned)} DIRTY=0' not in status:
            raise RuntimeError('Returned file did not open in the editor')
        os.write(fd, b'\x83')
        run = read_for(2)+query()
        if 'VM_RESULT=OK' not in run or 'USB ROUND TRIP' not in run or 'X_RAW=[ 1.2345000  04]' not in run:
            raise RuntimeError('Returned USB source did not execute correctly')
        step(b'\x1B', 'SERVICE=EDITOR')
        step(b'\x1B', 'SERVICE=BROWSER')
        step(b'\x1B', 'SERVICE=CLOSED')
        final = step(b'\t', 'UI=CALCULATOR')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(dict(passed=True, disk=whole, checked_files=checked,
            returned_file=name, returned_source=returned, final_status=final, transcript=transcript),
            ensure_ascii=False, indent=2)+'\n')
        print('PicoCalc USB disk / Explorer round trip passed')
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, old)
        os.close(fd)


if __name__ == '__main__':
    main()
