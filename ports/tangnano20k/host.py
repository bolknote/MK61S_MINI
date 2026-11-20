#!/usr/bin/env python3
"""Send model and inference commands to Tang Nano 20K over its USB UART."""

import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import random
import select
import struct
import sys
import termios
import time
import zlib

BAUD = 1_000_000
SDRAM_BYTES = 8 * 1024 * 1024
CONTEXT = 1024
PUT, GET, CRC, DOT, ID, FORWARD, RESET = range(1, 8)
HEADER = struct.Struct("<BBHI")
REPLY = struct.Struct("<BIII")


class Link:
    def __init__(self, fd):
        self.fd = fd
        self.sequence = 0
        self.buffer = bytearray()

    def _wait(self, read, end):
        timeout = end - time.monotonic()
        if timeout <= 0 or not any(select.select([self.fd] if read else [],
                                                 [] if read else [self.fd], [], timeout)[:2]):
            raise TimeoutError("Tang UART deadline")

    def _send(self, packet, end):
        data = memoryview(packet)
        while data:
            self._wait(False, end)
            try:
                data = data[os.write(self.fd, data):]
            except BlockingIOError:
                continue

    def _receive(self, count, end):
        while len(self.buffer) < count:
            self._wait(True, end)
            self.buffer.extend(os.read(self.fd, 4096))
        value = bytes(self.buffer[:count])
        del self.buffer[:count]
        return value

    def call(self, opcode, addr=0, data=b"", timeout=5, corrupt=False, expect_status=0):
        if len(data) > 1024:
            raise ValueError("Tang packet length exceeds 1024 bytes")
        self.sequence = (self.sequence + 1) & 255
        body = HEADER.pack(opcode, self.sequence, len(data), addr) + data
        deadline = time.monotonic() + timeout
        self._send(b"\xa5\x5a" + body + struct.pack("<I", zlib.crc32(body) ^ corrupt), deadline)
        previous = b""
        while True:
            current = self._receive(1, deadline)
            if previous + current == b"\x5a\xa5":
                break
            previous = current
        header = self._receive(HEADER.size, deadline)
        if HEADER.unpack(header) != (opcode | 0x80, self.sequence, REPLY.size, 0):
            raise ValueError(f"Invalid Tang reply header {header.hex()}")
        reply = self._receive(REPLY.size, deadline)
        checksum, = struct.unpack("<I", self._receive(4, deadline))
        if checksum != zlib.crc32(header + reply):
            raise ValueError("Tang reply CRC mismatch")
        status, *values = REPLY.unpack(reply)
        if status != expect_status:
            raise ValueError(f"Tang command {opcode} status {status}, expected {expect_status}, detail {values}")
        return tuple(values)

    def write(self, addr, contents):
        if addr & 3 or len(contents) & 3 or addr + len(contents) > SDRAM_BYTES:
            raise ValueError("Model data must use aligned SDRAM words")
        for offset in range(0, len(contents), 1024):
            chunk = contents[offset:offset+1024]
            count, _, _ = self.call(PUT, addr+offset, chunk)
            if count != len(chunk):
                raise RuntimeError("Incomplete SDRAM write")

    def verify(self, addr, contents):
        checksum, _, _ = self.call(CRC, addr, struct.pack("<I", len(contents)))
        if checksum != zlib.crc32(contents):
            raise ValueError(f"Tang SDRAM checksum mismatch at {addr:#x}: {checksum:08x}")


@contextmanager
def connect(port):
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    original = termios.tcgetattr(fd)
    try:
        settings = termios.tcgetattr(fd)
        settings[0] = settings[1] = settings[3] = 0
        settings[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        settings[4] = settings[5] = termios.B115200
        settings[6][termios.VMIN] = settings[6][termios.VTIME] = 0
        if sys.platform == "darwin":
            termios.tcsetattr(fd, termios.TCSANOW, settings)
            fcntl.ioctl(fd, 0x80045402, struct.pack("<I", BAUD))  # IOSSIOSPEED
        else:
            settings[4] = settings[5] = termios.B1000000
            termios.tcsetattr(fd, termios.TCSANOW, settings)
        termios.tcflush(fd, termios.TCIOFLUSH)
        yield Link(fd)
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSANOW, original)
        finally:
            os.close(fd)


def smoke_test(link):
    version, hz, memory = link.call(ID)
    if version != 0x54323031 or memory != SDRAM_BYTES:
        raise ValueError("This is not the Tang inference bitstream")
    link.call(ID, corrupt=True, expect_status=1)
    generator = random.Random(0x20261120)
    positions = (0, 0x1ff800, 0x200000, 0x3ff800, 0x400000, 0x5ff800, 0x600000, 0x7ff800)
    blocks = [(addr, generator.randbytes(2048)) for addr in positions]
    for addr, block in blocks:
        link.write(addr, block)
    for addr, block in blocks:
        link.verify(addr, block)
        actual, _, _ = link.call(GET, addr)
        if actual != int.from_bytes(block[:4], "little"):
            raise ValueError(f"SDRAM random read mismatch at {addr:#x}")
    vectors = [(0, [-128] * 8), (0xffffffff, [127] * 8), (0x88888888, [127] * 8)]
    vectors += [(generator.getrandbits(32), [generator.randrange(-128, 128) for _ in range(8)])
                for _ in range(512)]
    for weights, activations in vectors:
        value, _, _ = link.call(DOT, data=struct.pack("<I8b", weights, *activations))
        ref = sum((((weights >> (4*j)) & 15) - 8) * x for j, x in enumerate(activations))
        if value != ref & 0xffffffff:
            raise ValueError(f"DSP dot mismatch {weights:08x}: {value:08x}, wanted {ref}")
    return dict(clock_hz=hz, sdram_bytes=memory, sdram_bytes_tested=sum(len(block) for _, block in blocks),
                exact_dsp_vectors=len(vectors), invalid_crc_rejected=True)


def generate(link, tokens, count):
    _, hz, _ = link.call(ID)
    link.call(RESET)
    prefill_cycles = 0
    position = 0
    for token in tokens[:-1]:
        _, _, cycles = link.call(FORWARD, token)
        prefill_cycles += cycles
        position += 1

    token = tokens[-1]
    generated = []
    for _ in range(count):
        packed, checksum, cycles = link.call(FORWARD, token | (1 << 16))
        position += 1
        if packed >> 16 != position:
            raise ValueError(f"Tang returned position {packed >> 16}, expected {position}")
        token = packed & 0xffff
        generated.append(dict(token=token, position=position, checksum=f"{checksum:08x}",
                              cycles=cycles, seconds=cycles/hz))
    return dict(clock_hz=hz, prefill_seconds=prefill_cycles/hz, generated=generated)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("self-test")
    upload = commands.add_parser("load")
    upload.add_argument("image", type=Path)
    inference = commands.add_parser("run", help="Decode from a sequence of token IDs")
    inference.add_argument("tokens", nargs="+", type=int)
    inference.add_argument("--generate", type=int, default=1, metavar="COUNT")
    args = parser.parse_args()
    if args.command == "run" and (any(not 0 <= token <= 0xffff for token in args.tokens)
                                  or not 1 <= args.generate <= CONTEXT - len(args.tokens) + 1):
        parser.error("Token IDs must fit in 16 bits and the run must fit the 1024-position context")
    with connect(args.port) as link:
        if args.command == "self-test":
            print(json.dumps(smoke_test(link), indent=2))
        elif args.command == "load":
            contents = args.image.read_bytes()
            start = time.perf_counter()
            link.write(0, contents)
            link.verify(0, contents)
            print(json.dumps(dict(bytes=len(contents), crc32=f"{zlib.crc32(contents):08x}",
                                  seconds=time.perf_counter() - start), indent=2))
        elif args.command == "run":
            print(json.dumps(generate(link, args.tokens, args.generate), indent=2))


if __name__ == "__main__":
    main()
