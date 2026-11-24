"""Run one prepared pow probe during its assigned hardware window (macOS)."""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import time

import hil_mk61_ai as pico
from check_stm32_vectors import ElfImage
from hil_c5_stack import read_file, write_file
from hil_multi_device_identity import parse_identity
from hil_portable_apps import ScreenPort
from hil_usb_disk_transaction import listing_entries


def checked_file(receipt, key):
    saved = receipt['files'][key]
    path = Path(saved['path'])
    if hashlib.sha256(path.read_bytes()).hexdigest() != saved['sha256']:
        raise ValueError(f'{key} differs from the qualified file')
    return path


def usb_nodes():
    # A USB mode change can remove a child while ioreg walks the tree.
    # Discard the entire partial snapshot and take a fresh one.
    for attempt in range(5):
        try:
            roots = plistlib.loads(subprocess.check_output(
                ['/usr/sbin/ioreg','-a','-r','-c','IOUSBHostDevice','-l','-w','0'],
                stderr=subprocess.PIPE,timeout=3))
            break
        except (subprocess.CalledProcessError,plistlib.InvalidFileException):
            if attempt == 4:
                raise
            time.sleep(.1)
    def walk(node):
        yield node
        for child in node.get('IORegistryEntryChildren',[]):
            yield from walk(child)
    return [n for r in roots for n in walk(r)]


def locate(serial, vid, pid, location=None):
    matches = [n for n in usb_nodes() if n.get('USB Serial Number') == serial
               and (n.get('idVendor'),n.get('idProduct')) == (vid,pid)
               and (location is None or n.get('locationID') == location)]
    locations = {n['locationID'] for n in matches}
    if len(locations) != 1:
        raise ValueError(f'expected one USB device matching {serial}')
    return matches[0]


def connect(serial, vid, pid, location, seconds):
    until = time.monotonic()+seconds
    while time.monotonic()<until:
        try:
            nodes = [locate(serial,vid,pid,location)]
            ports = set()
            while nodes:
                n = nodes.pop()
                if n.get('IOCalloutDevice','').startswith('/dev/cu.usbmodem'):
                    ports.add(n['IOCalloutDevice'])
                nodes.extend(n.get('IORegistryEntryChildren',[]))
            pico.PORT, = ports
            return pico.Serial(time.monotonic()+40)
        except (ValueError,OSError):
            time.sleep(.1)
    raise TimeoutError(f'CDC unavailable for {serial}')


def run_pico(args, receipt):
    elf = checked_file(receipt,'ram')
    for kind, _, va, pa, size, mem, _, _ in ElfImage(elf).segments:
        if kind == 1 and not (0x20000000 <= va == pa and size <= mem and va+mem <= 0x20042000):
            raise ValueError('probe has a load outside SRAM')
    uid = pico.UID
    assert uid == receipt['pico_id']
    board = (uid,0xcafe,0x4003)
    location = locate(*board)['locationID']
    tool = args.picotool.resolve()
    def picotool(*cmd):
        return subprocess.run([tool,*cmd,'--ser',uid],check=True,stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,timeout=12,env=dict(os.environ,DYLD_LIBRARY_PATH=str(tool.parent))).stdout

    with closing(connect(*board,location,3)) as term:
        pico.readiness(term.status(),args.build,args.crc)
        term.commands()
        pico.identity(term)
        print(f'PicoCalc {uid} location={location:#x} build={args.build} crc={args.crc}',flush=True)
        term.send(b'\x1e!')
    # picotool's --ser selects the flash ID. BOOTSEL's USB serial is shared.
    until = time.monotonic()+8
    while time.monotonic()<until:
        try:
            locate('E0C9125B0D9B',0x2e8a,3,location)
            break
        except ValueError:
            time.sleep(.1)
    else:
        raise TimeoutError('expected BOOTSEL at the original USB location')
    ids = re.findall(rb'(?mi)^ *flash id:[ \t]+0x([a-f0-9]+)[ \t]*$',picotool('info','-a'))
    if [v.decode().upper() for v in ids] != [uid]:
        raise ValueError('BOOTSEL flash ID mismatch')
    print(f'BOOTSEL flash ID {uid} at {location:#x}',flush=True)
    try:
        picotool('load','-v','-x',str(elf))
        with closing(connect('EEEEEEEEEEEEEEEE',0x2e8a,0x000a,location,5)) as ram:
            ram.send(b'g')
            return ram.wait(lambda b: b'END POW1' in b,30)
    finally:
        # A successful SRAM start has its own watchdog. If the load failed
        # before execution, leave BOOTSEL on that same identified device.
        try:
            locate('E0C9125B0D9B',0x2e8a,3,location)
        except ValueError:
            pass
        else:
            picotool('reboot')
        with closing(connect(*board,location,15)) as term:
            # CDC enumerates before the resident finishes its boot checks.
            until = time.monotonic()+8
            while True:
                try:
                    pico.readiness(term.status(),args.build,args.crc)
                    break
                except ValueError:
                    if time.monotonic() >= until:
                        raise
                    time.sleep(.15)
            print(f'Resident ready {args.build}/{args.crc}, SERVICE=CLOSED',flush=True)


def run_classic(args, receipt):
    app = checked_file(receipt,'app')
    with ScreenPort(args.port) as port:
        ident = parse_identity(port.command('identity',15))
        if (ident.public,ident.usb,ident.build) != (receipt['classic_id'],'2068336B4731',receipt['classic_image']['build']):
            raise ValueError('Classic ID or installed reference build differs from the receipt')
        def names():
            return {s.split('\t')[-1].casefold() for s in listing_entries(port.command('ls "/"',20))}
        remote = ('POWCLASS.APP','POWCLASS.bin')
        if {n.casefold() for n in remote} & names():
            raise ValueError('probe or result name already in use on Classic')
        try:
            write_file(port,'/'+remote[0],app.read_bytes())
            reply = port.command('open "/POWCLASS.APP"',120)
            if 'Open failed!' in reply:
                raise RuntimeError(reply)
            return read_file(port,'/'+remote[1])
        finally:
            port.command('fsput cancel')
            existing = names()
            for name in remote:
                if name.casefold() in existing:
                    assert 'Removed 1 entry.' in port.command(f'rm "/{name}"',30)


def main():
    if not __debug__:
        raise SystemExit('run with Python assertions enabled')
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--receipt',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    modes = p.add_subparsers(dest='mode',required=True)
    rp = modes.add_parser('pico')
    rp.add_argument('--build',required=True)
    rp.add_argument('--crc',required=True)
    rp.add_argument('--picotool',type=Path,required=True)
    modes.add_parser('classic').add_argument('--port',required=True)
    args = p.parse_args()
    receipt = json.loads(args.receipt.read_text())
    if args.output.exists():
        p.error('choose a new output path to preserve the previous capture')
    raw = (run_pico if args.mode=='pico' else run_classic)(args,receipt)
    with args.output.open('xb') as output:
        output.write(raw)


if __name__=='__main__':
    main()
