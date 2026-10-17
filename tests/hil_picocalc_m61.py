#!/usr/bin/env python3
"""Exercise the production M61 runner on PicoCalc, through USB and the UI.

Creates a unique directory on the Pico's mounted microSD. Never formats,
repairs or overwrites existing card files. Requires a calculator idle screen.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import select
import shutil
import subprocess
import termios
import time
import tty

ROOT = Path(__file__).resolve().parents[1]


def disk_info(*args):
    return plistlib.loads(subprocess.check_output(['diskutil', *args], timeout=30))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--directory',help='Reuse this session test directory without writing the card')
    parser.add_argument('--write-test-files', action='store_true', required=True)
    args = parser.parse_args()
    firmware=ROOT/'binary/picocalc-pico-h/mk61s-picocalc-pico-h.uf2'
    firmware_sha256=hashlib.sha256(firmware.read_bytes()).hexdigest()
    fd = os.open(args.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    old = termios.tcgetattr(fd)
    transcript, cases = [], []
    name = args.directory or 'MK61S-M61-' + time.strftime('%Y%m%d-%H%M%S')
    assert name.startswith('MK61S-M61-') and '/' not in name

    def read_for(seconds):
        output = bytearray()
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if select.select([fd], [], [], max(0, end-time.monotonic()))[0]:
                data = os.read(fd, 16384)
                if not data:
                    raise RuntimeError('Pico disconnected')
                output += data
        text = output.decode('utf-8', errors='replace')
        transcript.append(text)
        print(text, end='', flush=True)
        return text

    def query():
        os.write(fd, b'\x05')
        return read_for(.3)

    def wait_for(*expected, timeout=20):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            status = query()
            if all(text in status for text in expected):
                return status
        raise RuntimeError('Expected ' + repr(expected))

    def step(keys, *expected, timeout=20):
        os.write(fd, keys)
        read_for(.1)
        return wait_for(*expected, timeout=timeout)

    def open_scenario(relative, unsaved=False):
        state=wait_for('SERVICE=CLOSED')
        if 'UI=MAIN ' not in state: step(b'\t','UI=MAIN')
        step(bytes([0xB5])*6+bytes([0xB6])*3+b'\n','SERVICE=BROWSER')
        step(b'/', 'SERVICE=PROMPT')
        step((name+'/'+relative).encode()+b'\n', 'SERVICE=EDITOR', 'DIRTY=0')
        if unsaved:
            step(b' \n', 'SERVICE=EDITOR', 'DIRTY=1')
        os.write(fd, b'\x83')

    try:
        tty.setraw(fd)
        os.write(fd, b'\x1e')
        status = query()
        for required in ('MK61S PICOCALC PICO-H 0.', 'SERVICE=CLOSED',
                         'UI=CALCULATOR', 'USB_DISK=0', 'SD=OK', 'RUN=0'):
            if required not in status:
                raise RuntimeError('Initial Pico state: missing ' + required)
        if not args.directory:
            before = set(disk_info('list', '-plist', 'external', 'physical')['WholeDisks'])
            step(b'\t'+bytes([0xB5])*6+bytes([0xB6])+b'\n', 'SERVICE=USB_DISK')
            whole = mount = None
            end = time.monotonic()+60
            while time.monotonic() < end and mount is None:
                for disk in set(disk_info('list', '-plist', 'external', 'physical')['WholeDisks'])-before:
                    info = disk_info('info', '-plist', disk)
                    if info.get('BusProtocol') != 'USB' or 'PicoCalc microSD' not in info.get('MediaName', ''):
                        continue
                    whole = disk
                    for part in disk_info('list', '-plist', whole)['AllDisksAndPartitions'][0].get('Partitions', []):
                        volume = disk_info('info', '-plist', part['DeviceIdentifier'])
                        if volume.get('MountPoint'):
                            mount = Path(volume['MountPoint'])
                            break
                if mount is None:
                    read_for(.5)
            if mount is None:
                raise RuntimeError('PicoCalc microSD did not mount')
            directory = mount/name
            directory.mkdir()  # Refuse an existing name.
            (directory/'lib').mkdir()
            (directory/'lib/init.tbi').write_text('10 A=41\n20 @(3)=1\n30 .R0=COLS\n40 .R1=ROWS\n50 END\n')
            (directory/'lib/keep.tbi').write_text('10 .R2=A+@(3)\n20 END\n')
            (directory/'lib/child.m61').write_text('R3= 42\nret\n')
            (directory/'manual.md').write_text('# Pico M61\n\nPress Esc to return to the running scenario.\n')
            shutil.copy2(ROOT/'programs/games/Turochamp/Turochamp.FMK', directory/'Turochamp.FMK')
            (directory/'main.m61').write_text(
                'reinit\nloadfont Turochamp.FMK\nopen lib/init.tbi\nopen lib/keep.tbi\n'
                'open lib/child.m61\nif r0!=27 run :bad\nif r1!=9 run :bad\n'
                'if r2!=42 run :bad\nif r3!=42 run :bad\n'
                'hin 0000 010E021050\ntrap 2 run :frame\nbind 01 run :one\n'
                'bind OK run :help\nrun\npoke X 3\nret\n'
                ':frame\nprint off\nprint "PICO M61 TRAP {X:m}"\nwait 1800\nprint on\nret\n'
                ':one\nprint off\nprint "PICO M61 KEY"\nret\n'
                ':help\nopen? manual.md\nprint off\nprint "PICO M61 HELP RETURN"\nret\n'
                ':bad\nunknown_command\n')
            for game in ('Turochamp', 'Bumblebee'):
                shutil.copytree(ROOT/'programs/games'/game, directory/game)
            # Flush the mounted volume before handing ownership back to FatFs.
            for attempt in range(3):
                eject=subprocess.run(['diskutil','eject',whole],timeout=30)
                if eject.returncode==0: break
                read_for(2)
            if eject.returncode: raise RuntimeError('Safe SD eject failed; USB disk remains active')
            step(b'\n', 'SERVICE=CLOSED')
            step(b'\t', 'UI=CALCULATOR')
            cases.append('USB SD round trip with new isolated M61 test directory')

        open_scenario('main.m61')
        wait_for('M61_ACTIVE=1 SUSPENDED=1 DISPLAY=1', 'COLS=27 ROWS=9 FONT=1', 'PICO M61 TRAP')
        status = wait_for('SERVICE=CLOSED', 'M61_ACTIVE=1 SUSPENDED=0', 'X_RAW=[ 3.0000000  00]')
        cases.append('Nested M61/BASIC, persistent variables/array, FMK geometry, RUN and TRAP/context return')
        step(b'1', 'PICO M61 KEY', 'M61_ACTIVE=1 SUSPENDED=0', 'X_RAW=[ 3.0000000  00]')
        cases.append('BIND consumes physical calculator opcode without entering the digit')
        step(b'\n', 'SERVICE=VIEWER', 'M61_ACTIVE=1 SUSPENDED=1')
        step(b'\x1B', 'SERVICE=CLOSED', 'PICO M61 HELP RETURN', 'M61_ACTIVE=1 SUSPENDED=0')
        step(b'\x1B', 'M61_ACTIVE=0 SUSPENDED=0', 'FONT=0', 'RUN=0')
        cases.append('OK opens Markdown; viewer Esc returns to scenario; next Esc cancels and restores font')

        open_scenario('main.m61', unsaved=True)
        wait_for('SERVICE=CLOSED', 'M61_ACTIVE=1 SUSPENDED=0', 'X_RAW=[ 3.0000000  00]')
        step(b'\x1B', 'SERVICE=EDITOR', 'DIRTY=1', '/main.m61]', 'M61_ACTIVE=0')
        step(b'\x1B', 'SERVICE=CONFIRM')
        step(b'\n', 'SERVICE=BROWSER', 'DIRTY=0')
        step(b'\x1B', 'SERVICE=CLOSED', 'UI=CALCULATOR')
        cases.append('Unsaved root source survives nested interpreters and cancellation, returns to editor, explicit discard')

        open_scenario('Turochamp/autoexec.m61')
        wait_for('SERVICE=CONSOLE', '/Turochamp/menu.tbi]', 'COLS=27 ROWS=9 FONT=1')
        step(b'\n', 'SERVICE=CONSOLE', '/Turochamp/board.tbi]', 'abcdefgh', timeout=45)
        step(b'r', 'SERVICE=CONSOLE', '/Turochamp/menu.tbi]', timeout=45)
        step(b'\x1B', 'SERVICE=CLOSED', 'M61_ACTIVE=0 SUSPENDED=0', 'FONT=0', timeout=20)
        cases.append('Unmodified Turochamp: autoexec -> side menu -> board -> RUN game menu -> Esc')

        open_scenario('Bumblebee/autoexec.m61')
        wait_for('SERVICE=VIEWER', '/Bumblebee/manual.md]')
        step(b'\x1B', 'SERVICE=CLOSED', 'M61_ACTIVE=1', timeout=30)
        step(b'\n', 'SERVICE=VIEWER', '/Bumblebee/manual.md]', timeout=30)
        step(b'\x1B', 'SERVICE=CLOSED', 'M61_ACTIVE=1', timeout=30)
        final = step(b'\x1B', 'SERVICE=CLOSED', 'M61_ACTIVE=0 SUSPENDED=0', 'RUN=0')
        cases.append('Unmodified Bumblebee: optional manual, real program traps, OK help and cancel')
        if 'M61 ' in final and ': terminal command failed' in final:
            raise RuntimeError('Unexpected scenario error')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if hashlib.sha256(firmware.read_bytes()).hexdigest()!=firmware_sha256:
            raise RuntimeError('Firmware artifact changed during HIL')
        args.output.write_text(json.dumps(dict(passed=True, uf2_sha256=firmware_sha256, directory='/'+name,
            cases=cases, final_status=final, transcript=transcript), ensure_ascii=False, indent=2)+'\n')
        print('PicoCalc full M61 HIL passed')
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, old)
        os.close(fd)


if __name__ == '__main__':
    main()
