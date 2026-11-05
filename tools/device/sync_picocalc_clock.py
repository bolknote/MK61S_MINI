#!/usr/bin/env python3
"""Set an unset PicoCalc RTC from the computer without taking its screen.

Uses Python's standard library on macOS/Linux. Specify the PicoCalc CDC port;
close USB Screen first. --force also replaces an already configured clock.
"""
import argparse
import binascii
from datetime import datetime
import hashlib
import os
import select
import struct
import time
from zoneinfo import ZoneInfo


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


def decode_state(encoded):
    raw = bytearray(); offset = 0
    while offset < len(encoded):
        code = encoded[offset]; offset += 1
        if not code or offset + code - 1 > len(encoded):
            raise ValueError('Malformed clock reply')
        raw.extend(encoded[offset:offset + code - 1]); offset += code - 1
        if code != 255 and offset < len(encoded): raw.append(0)
    if len(raw) < 11 or raw[:3] != b'MS\x02': return None
    size = struct.unpack_from('<H', raw, 7)[0]
    if size > 224 or len(raw) != size + 11:
        raise ValueError('Invalid clock reply length')
    if binascii.crc_hqx(raw[:-2], 65535) != struct.unpack_from('<H', raw, len(raw)-2)[0]:
        raise ValueError('Clock reply CRC mismatch')
    if raw[3] != 0x41: return None
    if size != 9 or raw[9] != 0 or raw[10] not in (0, 1):
        raise ValueError('PicoCalc rejected clock request')
    date = datetime(struct.unpack_from('<H', raw, 11)[0], *raw[13:18])
    if not 2000 <= date.year <= 2099: raise ValueError('Invalid RTC year')
    return bool(raw[10]), date


def exchange(port, mode=1, date=None, timeout=4):
    import fcntl
    import termios
    import tty
    date = date or datetime.now()
    if mode not in (0, 1, 2) or not 2000 <= date.year <= 2099:
        raise ValueError('RTC supports 2000 through 2099')
    payload = struct.pack('<BH5B', mode, date.year, date.month, date.day,
                          date.hour, date.minute, date.second)
    raw = b'MS\x02\x40\0\0\0' + struct.pack('<H', len(payload)) + payload
    raw += struct.pack('<H', binascii.crc_hqx(raw, 65535))
    packet = b'\0' + cobs_encode(raw) + b'\0'
    canonical = os.path.realpath(port).replace('/dev/tty.', '/dev/cu.')
    key = hashlib.sha256(canonical.encode()).hexdigest()[:20]
    lock = os.open(f'/tmp/mk61-hil-cdc-{os.geteuid()}-{key}.lock', os.O_CREAT | os.O_RDWR, 0o600)
    fd = -1; old = None
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        fcntl.ioctl(fd, termios.TIOCEXCL)
        old = termios.tcgetattr(fd)
        tty.setraw(fd)
        end = time.monotonic() + timeout
        offset = 0; frame = None
        while time.monotonic() < end:
            readable, writable, _ = select.select([fd], [fd] if offset < len(packet) else [], [], .05)
            if writable: offset += os.write(fd, packet[offset:])
            if readable:
                for byte in os.read(fd, 8192):
                    if byte == 0:
                        if frame:
                            result = decode_state(frame)
                            if result is not None: return result
                            frame = None
                        else: frame = bytearray()
                    elif frame is not None:
                        frame.append(byte)
                        if len(frame) > 240: frame = None
        raise TimeoutError('No PicoCalc clock reply; requires firmware 0.4.1 or newer')
    finally:
        if fd >= 0:
            try:
                if old is not None: termios.tcsetattr(fd, termios.TCSANOW, old)
                fcntl.ioctl(fd, termios.TIOCNXCL)
            except OSError:
                pass  # The cable may have been removed during the request.
            finally:
                os.close(fd)
        os.close(lock)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True, help='PicoCalc CDC port, e.g. /dev/cu.usbmodem1401')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--force', action='store_true', help='Replace an already set clock')
    modes.add_argument('--read', action='store_true', help='Read without setting the clock')
    parser.add_argument('--timezone', help='IANA zone; default is the computer local time')
    args = parser.parse_args()
    try:
        now = datetime.now(ZoneInfo(args.timezone)) if args.timezone else datetime.now()
        configured, date = exchange(args.port, 0 if args.read else 2 if args.force else 1, now)
        print(f'RTC={date:%Y-%m-%d %H:%M:%S} RTC_SET={int(configured)}')
    except (OSError, ValueError, TimeoutError, KeyError) as error:
        parser.exit(1, f'PicoCalc clock: {error}\n')


if __name__ == '__main__': main()
