#!/usr/bin/env python3
"""Exercise preinstalled portable System APPs on a Classic V3 via USB Screen.

Generate fixtures locally with --write-fixtures. Hardware mode runs only those
fixtures, changes R0 through R4, and temporarily sends keys/takes the display.
It never flashes firmware or writes C5. The caller must preserve calculator
state and install the matching fixture files before running this test.
"""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import re
import struct
import zlib

from hil_portable_apps import ScreenPort, write_fixtures

SPRITE = bytes.fromhex('f090f080f0')


def fixtures(directory):
    write_fixtures(directory)
    (directory/'Arithmetic.foc').write_text(
        '1.10 S A=2+3*4\n1.20 S .R0=A\n1.30 P 100000000\n'
        '1.40 P A/3\n1.50 E\n')
    (directory/'Arithmetic.tbi').write_text(
        '10 LET A=6*7\n20 LET .R1=A\n'
        '30 .R2=SIN(0)+COS(0)+SQRT(16)+LN(EXP(1))\n'
        '40 PRINT A/3\n50 END\n')
    (directory/'Keys.ch8').write_bytes(
        bytes.fromhex('00e060086104a216d015f20a00e07008d015f20a120c')+SPRITE)
    (directory/'Readme.md').write_text(
        '# ABI 3\n\nPortable **System APP**.\n\n'
        + '\n\n'.join(f'Line {i:02d}: test {i*i}.' for i in range(1,17))+'\n')
    (directory/'Edit.foc').write_text('1.10 S .R0=7\n1.20 E\n')
    (directory/'Edit.tbi').write_text('10 .R1=7\n20 END\n')
    (directory/'GetVars.foc').write_text('1.10 S .R3=A\n1.20 E\n')
    (directory/'GetVars.tbi').write_text('10 .R4=A\n20 END\n')


def chip_frame(x):
    frame = bytearray(1536)
    for y, row in enumerate(SPRITE):
        for bit in range(8):
            if row & (128 >> bit):
                for dy in range(2):
                    for dx in range(2):
                        px, py = 32+(x+bit)*2+dx, (4+y)*2+dy
                        frame[py//8*192+px] |= 1 << (py%8)
    return bytes(frame)


def png(frame, path):
    def chunk(kind, data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
    pixels = b''.join(b'\0'+bytes(0 if frame[y//8*192+x] & (1<<(y%8)) else 255
                                  for x in range(192)) for y in range(64))
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',192,64,8,0,0,0,0))
                     +chunk(b'IDAT',zlib.compress(pixels))+chunk(b'IEND',b''))


def registers(port):
    report = port.command('reg')
    values = {}
    for name, number, exponent in re.findall(r'(?m)^(R[0-9A-F]) =\s*([+\-]?\d+\.\d+)\s+([+\-]?\d+)\r?$',report):
        values[name] = Decimal(number) * Decimal(10)**int(exponent)
    assert len(values) >= 15, report
    return values, report


def zero_registers(port, names):
    for name in names:
        report = port.command(name+'= 0')
        assert 'Unknown command' not in report and 'Usage:' not in report, report
    values, report = registers(port)
    assert all(values[name] == 0 for name in names), report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port')
    parser.add_argument('--public-id')
    parser.add_argument('--directory', default='/SAPPTEST')
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--cycles', type=int, default=3)
    parser.add_argument('--markdown', action='store_true')
    parser.add_argument('--write-fixtures', type=Path)
    args = parser.parse_args()
    if args.write_fixtures:
        fixtures(args.write_fixtures)
        return
    if not (args.port and args.public_id and args.output_dir):
        parser.error('--port, --public-id and --output-dir are required')
    assert 1 <= args.cycles <= 30 and '"' not in args.directory
    args.output_dir.mkdir(parents=True,exist_ok=True)
    foreground = False
    counts = {'language_runs':0,'state_restores':0,'chip8_runs':0,'markdown_runs':0}
    with ScreenPort(args.port) as port:
        identity = port.command('identity')
        assert f'public={args.public_id.upper()}' in identity, identity
        (args.output_dir/'identity.txt').write_text(identity)
        try:
            port.attach()
            for cycle in range(args.cycles):
                for extension, expected in [('foc',{'R0':14}),('tbi',{'R1':42,'R2':6})]:
                    zero_registers(port, expected)
                    start = len(port.frames)
                    foreground = True
                    port.open(f'{args.directory}/Arithmetic.{extension}')
                    port.pump(1)
                    assert len(port.frames) > start, (extension,'no display output')
                    png(port.frames[-1],args.output_dir/f'{extension}-{cycle}.png')
                    port.close_app(); foreground = False; port.pump(.2)
                    actual, report = registers(port)
                    (args.output_dir/f'{extension}-{cycle}-registers.txt').write_text(report)
                    for name, value in expected.items(): assert actual[name] == value, (name,actual,report)
                    counts['language_runs'] += 1
                # One runtime lives in WORKSPACE, the other in the existing
                # single BULK snapshot. Verify their supported exchange before
                # a third workspace consumer can displace that snapshot.
                for extension, name, expected in [('foc','R3',14),('tbi','R4',42)]:
                    zero_registers(port, [name])
                    foreground = True
                    port.open(f'{args.directory}/GetVars.{extension}'); port.pump(.6)
                    port.close_app(); foreground = False; port.pump(.2)
                    actual, report = registers(port)
                    assert actual[name] == expected, ('lost language workspace',name,actual)
                    (args.output_dir/f'state-{extension}-{cycle}.txt').write_text(report)
                    counts['language_runs'] += 1
                    counts['state_restores'] += 1
                start = len(port.frames); foreground = True
                port.open(f'{args.directory}/Keys.ch8')
                port.expect_frame(chip_frame(8), start)
                start = len(port.frames); port.key(13)  # Classic digit 5.
                port.expect_frame(chip_frame(16), start)
                png(chip_frame(16),args.output_dir/f'chip8-{cycle}.png')
                port.close_app(); foreground = False; port.pump(.2)
                counts['chip8_runs'] += 1
                print(f'Cycle {cycle+1}: arithmetic, restored variables, CHIP-8 pixels/input PASS',flush=True)

            if args.markdown:
                reference = None
                for cycle in range(args.cycles):
                    start = len(port.frames); foreground = True
                    port.open(f'{args.directory}/Readme.md'); port.pump(1)
                    assert len(port.frames) > start
                    first = port.frames[-1]
                    assert any(first), 'Markdown produced an empty frame'
                    if reference is None: reference = first
                    assert first == reference, 'Markdown changed across launches'
                    png(first,args.output_dir/f'markdown-{cycle}.png')
                    start = len(port.frames); port.key(36); port.pump(.25)
                    assert len(port.frames) > start and port.frames[-1] != first, 'Markdown did not scroll'
                    png(port.frames[-1],args.output_dir/f'markdown-scroll-{cycle}.png')
                    start = len(port.frames); port.key(38)
                    port.expect_frame(first,start)
                    port.close_app(); foreground = False; port.pump(.2)
                    counts['markdown_runs'] += 1
                print('Markdown: repeatable render, scrolling and return PASS',flush=True)

            for command in ('identity','crash show','mpu status','mem','df'):
                report = port.command(command,timeout=15)
                (args.output_dir/(command.replace(' ','-')+'.txt')).write_text(report)
                if command == 'crash show': assert 'CRASH none' in report, report
                if command == 'mpu status': assert 'enabled=1 layout=ok' in report, report
                if command == 'mem': assert 'MEM invariant=ok' in report, report
                if command == 'df': assert 'FIRMWARE CRC state=valid' in report, report
            counts.update(result='PASS',frames_verified_transport=len(port.frames))
            (args.output_dir/'result.json').write_text(json.dumps(counts,indent=2)+'\n')
        finally:
            (args.output_dir/'terminal.txt').write_bytes(port.text)
            if port.frames: png(port.frames[-1],args.output_dir/'last-frame.png')
            if foreground and port.attached: port.key(39)
            if port.attached: port.send(0x13); port.pump(.2)


if __name__ == '__main__':
    main()
