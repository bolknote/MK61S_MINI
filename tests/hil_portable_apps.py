#!/usr/bin/env python3
"""Exercise preinstalled portable CHECK/WBMP APPs through the real USB screen.

No firmware or C5 writes. The test temporarily takes the display and sends
virtual keys. CHECK.APP is built from portable_app_hil_check.c; Wide/Tall WBMP
fixtures use the independent pixel formula below. See sdk/portable/README.md.
"""
import argparse
import binascii
import hashlib
import json
import os
import re
import select
import struct
import time
from pathlib import Path

from hil_rtc_alarm import Port, PROMPT


def cobs_encode(data):
    out = bytearray([0]); start = 0; code = 1
    for byte in data:
        if byte == 0:
            out[start] = code; start = len(out); out.append(0); code = 1
        else:
            out.append(byte); code += 1
            if code == 255:
                out[start] = code; start = len(out); out.append(0); code = 1
    out[start] = code
    return bytes(out)


def cobs_decode(data):
    out = bytearray(); position = 0
    while position < len(data):
        code = data[position]; position += 1
        assert code and position + code - 1 <= len(data)
        out.extend(data[position:position + code - 1]); position += code - 1
        if code < 255 and position < len(data): out.append(0)
    return bytes(out)


def packbits(data):
    out = bytearray(); i = 0
    while i < len(data):
        count = data[i]; i += 1
        assert count != 128
        if count < 128:
            assert i + count + 1 <= len(data)
            out.extend(data[i:i + count + 1]); i += count + 1
        else:
            assert i < len(data)
            out.extend([data[i]] * (257 - count)); i += 1
    return bytes(out)


class ScreenPort(Port):
    def __init__(self, path):
        super().__init__(path)
        self.packet = None; self.text = bytearray(); self.frames = []
        self.sequence = 0; self.attached = False; self.next_ping = 0
        self.caps = None; self.pending = None; self.pages = set()

    def send(self, kind, payload=b''):
        raw = b'MS\x02' + bytes((kind, 0)) + struct.pack('<HH', self.sequence, len(payload)) + payload
        self.sequence = (self.sequence + 1) & 65535
        raw += struct.pack('<H', binascii.crc_hqx(raw, 65535))
        wire = b'\0' + cobs_encode(raw) + b'\0'
        offset = 0
        while offset < len(wire): offset += os.write(self.fd, wire[offset:])

    def receive_packet(self, encoded):
        raw = cobs_decode(encoded)
        assert len(raw) >= 11 and raw[:3] == b'MS\x02'
        assert binascii.crc_hqx(raw[:-2], 65535) == struct.unpack_from('<H', raw, len(raw) - 2)[0]
        size = struct.unpack_from('<H', raw, 7)[0]
        assert len(raw) == size + 11
        kind, payload = raw[3], raw[9:-2]
        if kind == 0x12:
            self.caps = payload
            assert payload[:4] == bytes((192, 0, 64, 8))
            assert payload[8:10] == bytes((1, 40)), 'test requires the Classic keyboard layout'
            self.attached = True
            self.next_ping = time.monotonic() + .7
        elif kind == 0x20:
            self.frame_id, full, pages = struct.unpack('<HBB', payload)
            assert full == 1 and pages == 8
            self.pending = bytearray(1536); self.pages = set()
        elif kind == 0x21:
            frame_id, x, page, width, codec = struct.unpack_from('<HBBBB', payload)
            assert frame_id == self.frame_id and x == 0 and width == 192 and page < 8
            assert page not in self.pages and codec in (0, 1)
            pixels = payload[6:] if codec == 0 else packbits(payload[6:])
            assert len(pixels) == width
            self.pending[page * 192:page * 192 + width] = pixels
            self.pages.add(page)
        elif kind == 0x22:
            frame_id, checksum = struct.unpack('<HH', payload)
            assert frame_id == self.frame_id and len(self.pages) == 8
            assert binascii.crc_hqx(self.pending, 65535) == checksum
            self.frames.append(bytes(self.pending)); self.pending = None
        elif kind == 0x13:
            self.attached = False

    def pump(self, duration=.05):
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            now = time.monotonic()
            if self.attached and now >= self.next_ping:
                self.send(0x14, b'\x61\0'); self.next_ping = now + .7
            ready, _, _ = select.select([self.fd], [], [], min(.03, max(0, deadline - now)))
            if not ready: continue
            for byte in os.read(self.fd, 8192):
                if byte == 0:
                    if self.packet is None: self.packet = bytearray()
                    elif self.packet:
                        self.receive_packet(self.packet); self.packet = None
                elif self.packet is None: self.text.append(byte)
                else: self.packet.append(byte)

    def command(self, command, timeout=5):
        self.pump(.02); start = len(self.text)
        self.write_line(command)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.pump()
            if PROMPT.search(self.text[start:]): return self.text[start:].decode('utf-8', 'replace')
        raise TimeoutError(f'{command}: {self.text[start:]!r}')

    def attach(self):
        self.command('uscreen')
        self.attach_waiting()

    def attach_waiting(self):
        self.caps = None
        # Do not send PING until CAPS: the firmware has one response slot,
        # so an immediate heartbeat could replace the handshake response.
        self.send(0x11)
        deadline = time.monotonic() + 3
        while self.caps is None and time.monotonic() < deadline: self.pump()
        assert self.caps is not None, 'USB Screen did not attach'

    def key(self, raw):
        self.send(0x30, bytes((raw, 1))); self.pump(.06)
        self.send(0x30, bytes((raw, 0))); self.pump(.06)

    def open(self, path):
        self.pump(.05)
        self.open_text_start = len(self.text)
        # `open` owns the foreground until the APP exits; its prompt is late.
        self.write_line(f'open "{path}"')

    def close_app(self):
        self.key(39)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.pump()
            response = self.text[self.open_text_start:]
            if PROMPT.search(response):
                assert b'Open failed!' not in response, response
                return
        raise TimeoutError(f'APP did not exit: {self.text[self.open_text_start:]!r}')

    def expect_frame(self, expected, start, timeout=4):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if expected in self.frames[start:]: return
            self.pump()
        actual = hashlib.sha256(self.frames[-1]).hexdigest() if self.frames else 'none'
        raise AssertionError(f'expected frame not received; last={actual}; terminal={self.text[-600:]!r}')


def oracle(width, height, x0=0, y0=0):
    pixels = bytearray(1536)
    for y in range(64):
        for x in range(192):
            if x + x0 < width and y + y0 < height and ((x + x0) * 3 + (y + y0) * 5) % 11 < 5:
                pixels[(y // 8) * 192 + x] |= 1 << (y % 8)
    return bytes(pixels)


def write_fixtures(directory):
    directory.mkdir(parents=True, exist_ok=True)
    for name, width, height in (('Wide', 208, 48), ('Tall', 144, 80)):
        # Both widths need two WBMP variable-length octets; heights need one.
        data = bytearray((0, 0, 0x80 | (width >> 7), width & 127, height))
        pixels = bytearray([255] * (width // 8 * height))
        for y in range(height):
            for x in range(width):
                if (x * 3 + y * 5) % 11 < 5:
                    pixels[y * (width // 8) + x // 8] &= ~(128 >> (x % 8))
        (directory / (name + '.wbmp')).write_bytes(data + pixels)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port')
    parser.add_argument('--public-id')
    parser.add_argument('--directory', default='/PAPPTEST')
    parser.add_argument('--cycles', type=int, default=10)
    parser.add_argument('--minimum-stack-remaining', type=int, default=0,
                        help='required watermark headroom in bytes (F411 release: 12288)')
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--relocation-app', type=Path,
                        help='installed CHECK.APP built from portable_app_hil_relocation.c')
    parser.add_argument('--write-fixtures', type=Path,
                        help='only generate Wide/Tall.wbmp locally; no device access')
    args = parser.parse_args()
    if args.minimum_stack_remaining < 0:
        parser.error('--minimum-stack-remaining must be nonnegative')
    if args.write_fixtures:
        write_fixtures(args.write_fixtures)
        return
    if not (args.port and args.public_id and args.output_dir):
        parser.error('--port, --public-id and --output-dir are required for hardware tests')
    assert 1 <= args.cycles <= 100 and '"' not in args.directory
    args.output_dir.mkdir(parents=True, exist_ok=True)
    expected_check = bytes(((i * 17 + i // 16) ^ 0xA5) & 255 for i in range(1536))
    relocation_address = None
    if args.relocation_app:
        container = args.relocation_app.read_bytes()
        assert len(container) >= 64 and struct.unpack_from('<H', container, 12)[0] == 4
        memory_size = struct.unpack_from('<I', container, 32)[0]
        assert 0 < memory_size < 20480
    foreground = False
    with ScreenPort(args.port) as port:
        report = port.command('identity')
        assert f'public={args.public_id.upper()}' in report, report
        (args.output_dir / 'identity.txt').write_text(report)
        if args.relocation_app:
            report = port.command('mpu status')
            match = re.search(r' guard=0x([0-9A-Fa-f]+)', report)
            assert match and 'enabled=1 layout=ok' in report, report
            relocation_address = int(match.group(1), 16) - ((memory_size + 31) & ~31)
            expected_check = struct.pack('<I', relocation_address) + expected_check[4:]
        try:
            port.attach()
            for cycle in range(args.cycles):
                start = len(port.frames); foreground = True
                port.open(f'{args.directory}/CHECK.APP')
                port.expect_frame(expected_check, start)
                port.close_app(); foreground = False
                port.pump(.15)
            print(f'C startup: {args.cycles} fresh launches, full .data/BSS bitmap PASS', flush=True)
            if relocation_address is not None:
                print(f'ARM relocations: data/function/packed/end pointers and PC at '
                      f'{relocation_address:#010x} PASS', flush=True)

            for name, width, height, steps in (
                    ('Wide', 208, 48, ((36, 8, 0), (36, 16, 0), (38, 8, 0))),
                    ('Tall', 144, 80, ((28, 0, 16), (27, 0, 0)))):
                for repeat in range(3):
                    start = len(port.frames); foreground = True
                    port.open(f'{args.directory}/{name}.wbmp')
                    port.expect_frame(oracle(width, height), start)
                    for key, x, y in steps:
                        start = len(port.frames); port.key(key)
                        port.expect_frame(oracle(width, height, x, y), start)
                    port.close_app(); foreground = False
                    port.pump(.15)
                print(f'WBMP {name}: 3 launches, all viewport pixels and scroll positions PASS', flush=True)

            # On UC1609 this also exercises the physical graphics path between
            # DETACH and ATTACH. Pixel comparison covers the USB surface only.
            start = len(port.frames); foreground = True
            port.open(f'{args.directory}/Wide.wbmp')
            port.expect_frame(oracle(208, 48), start)
            port.send(0x13); port.attached = False; port.pump(.4)
            start = len(port.frames)
            port.attach_waiting()
            port.expect_frame(oracle(208, 48), start)
            start = len(port.frames); port.key(36)
            port.expect_frame(oracle(208, 48, 8), start)
            port.close_app(); foreground = False
            print('WBMP: physical/USB display switch and resumed scrolling PASS', flush=True)

            # Switching overlay owners must still initialize the next C APP.
            start = len(port.frames); foreground = True
            port.open(f'{args.directory}/CHECK.APP')
            port.expect_frame(expected_check, start)
            port.close_app(); foreground = False
            for command, filename in (('crash show', 'crash.txt'), ('mpu status', 'mpu.txt'),
                                      ('mem', 'memory.txt'), ('df', 'firmware.txt')):
                report = port.command(command, timeout=10)
                (args.output_dir / filename).write_text(report)
                if command == 'crash show': assert 'CRASH none' in report, report
                if command == 'mpu status':
                    assert 'enabled=1 layout=ok' in report and 'watermark=1' in report, report
                    remaining = int(re.search(r' observed_remaining=(\d+)', report)[1])
                    assert remaining >= args.minimum_stack_remaining, (remaining, args.minimum_stack_remaining)
                if command == 'mem': assert 'MEM invariant=ok' in report, report
                if command == 'df': assert 'FIRMWARE CRC state=valid' in report, report
            result = {'startup_launches': args.cycles + 1, 'wbmp_launches': 7,
                      'display_switches': 2,
                      'minimum_stack_remaining': remaining,
                      'frames_verified_transport': len(port.frames), 'result': 'PASS'}
            if relocation_address is not None:
                result.update(relocation_address=f'{relocation_address:#010x}',
                              app_sha256=hashlib.sha256(container).hexdigest())
            (args.output_dir / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
            print('Runtime: CRC, MPU, no crash, SRAM ownership PASS', flush=True)
        finally:
            (args.output_dir / 'terminal.txt').write_bytes(port.text)
            if port.frames: (args.output_dir / 'last-frame.bin').write_bytes(port.frames[-1])
            if foreground and port.attached:
                port.key(39)
            if port.attached:
                port.send(0x13); port.pump(.2)


if __name__ == '__main__':
    main()
