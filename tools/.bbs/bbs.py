#!/usr/bin/env python3
"""MK61 BBS: USB/TCP bridge and distribution package (Python backend)."""
from __future__ import annotations
import argparse
import binascii
import codecs
from collections import deque
import os
from pathlib import Path
import selectors
import socket
import struct
import sys
import termios
import time
import tty
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from m8_codec import encode as m8_encode, decode as m8_decode

OPEN, ACK, PRINT, INPUT, DATA, CANCEL, CLOSE, ABORT, INPUT_ACK, PING, PONG = range(1, 12)
MORE = 128
OK, END, TIMEOUT, CLOSED, NOT_FOUND, TOO_LONG, NO_SPACE, BUSY, IO, BAD_TEXT = range(10)
HEADER = struct.Struct('<2sBBIHH')


def frame(kind, session, sequence, offset=0, data=b''):
    if len(data) > 32:
        raise ValueError('frame payload exceeds 32 bytes')
    raw = HEADER.pack(b'BT', 1, kind, session, sequence, offset) + data
    raw += struct.pack('<H', binascii.crc_hqx(raw, 0xffff))
    encoded = bytearray(b'\0\0')
    code, run = 1, 1
    for byte in raw:
        if byte:
            encoded.append(byte)
            run += 1
        else:
            encoded[code] = run
            code, run = len(encoded), 1
            encoded.append(0)
    encoded[code] = run
    return bytes(encoded) + b'\0'


class Decoder:
    def __init__(self, receive):
        self.receive, self.packet = receive, None
        self.bad = False

    def feed(self, data):
        for byte in data:
            if byte == 0:
                if self.packet is not None and not self.bad:
                    self.finish(self.packet)
                self.packet = bytearray()
                self.bad = False
            elif self.packet is not None:
                if len(self.packet) < 48:
                    self.packet.append(byte)
                else:
                    self.bad = True

    def finish(self, packet):
        raw, at = bytearray(), 0
        while at < len(packet):
            code = packet[at]
            at += 1
            if not code or at + code - 1 > len(packet):
                return
            raw.extend(packet[at:at + code - 1])
            at += code - 1
            if code != 255 and at < len(packet):
                raw.append(0)
        if not 14 <= len(raw) <= 46 or raw[:3] != b'BT\1':
            return
        if binascii.crc_hqx(raw[:-2], 0xffff) != struct.unpack('<H', raw[-2:])[0]:
            return
        _, _, kind, session, sequence, offset = HEADER.unpack(raw[:12])
        self.receive(kind, session, sequence, offset, bytes(raw[12:-2]))


class Visitor:
    """Bounded line editor; Telnet control sequences never enter BASIC input."""
    def __init__(self, control):
        self.control = control
        self.decoder = codecs.getincrementaldecoder('utf-8')('strict')
        self.lines = deque()
        self.partial = ''
        self.error = OK
        self.telnet = 0
        self.command = 0
        self.cr = False
        self.discard = False
        self.cancel_done = None

    def feed(self, data):
        for byte in data:
            if self.telnet == 1:
                if byte in (251, 252, 253, 254):
                    self.command, self.telnet = byte, 2
                elif byte == 250:
                    self.telnet = 3
                else:
                    self.telnet = 0
                continue
            if self.telnet == 2:
                if self.command in (251, 253):
                    self.control(bytes((255, 254 if self.command == 251 else 252, byte)))
                self.telnet = 0
                continue
            if self.telnet in (3, 4):
                self.telnet = 4 if byte == 255 else (0 if self.telnet == 4 and byte == 240 else 3)
                continue
            if byte == 255:
                self.telnet = 1
                continue
            if byte in (10, 13):
                if byte == 10 and self.cr:
                    self.cr = False
                    continue
                self.cr = byte == 13
                if self.decoder.getstate()[0]:
                    self.error = BAD_TEXT
                if self.discard:
                    self.discard = False
                    done, self.cancel_done = self.cancel_done, None
                    if done:
                        done()
                else:
                    if len(self.lines) >= 4:
                        raise BufferError('visitor input queue full')
                    self.lines.append((self.error, self.partial))
                self.partial, self.error = '', OK
                self.decoder.reset()
                continue
            self.cr = False
            if self.discard:
                continue
            if byte in (8, 127):
                self.partial = self.partial[:-1]
                self.decoder.reset()
                continue
            if self.error:
                continue
            try:
                character = self.decoder.decode(bytes((byte,)))
                if character:
                    m8_encode(character)
                    self.partial += character
                    if len(self.partial) > 255:
                        self.error = TOO_LONG
                        self.partial = ''
            except (UnicodeError, ValueError):
                self.error = BAD_TEXT

    def cancel(self, done):
        self.lines.clear()
        partial = bool(self.partial or self.error or self.decoder.getstate()[0])
        self.partial, self.error = '', OK
        self.decoder.reset()
        self.discard = partial
        if partial:
            self.cancel_done = done
        else:
            done()


class Bridge:
    def __init__(self, send_serial, send_network, disconnect, clock=time.monotonic,
                 drained=lambda: True):
        self.serial, self.network, self.disconnect, self.clock = send_serial, send_network, disconnect, clock
        self.visitor = None
        self.session = 0
        self.offer = None
        self.pending = None
        self.answer = None
        self.print_sequence, self.print_data = None, bytearray()
        self.last_print = None
        self.last_cancel = None
        self.last_seen = self.clock()
        self.last_ping = self.clock()
        self.drained, self.closing = drained, None

    def send(self, kind, sequence, offset=0, data=b''):
        self.serial(frame(kind, self.session, sequence, offset, data))

    def ack(self, sequence, status=OK):
        self.send(ACK, sequence, data=bytes((status,)))

    def attach(self):
        self.visitor = Visitor(self.network)
        self.pair()

    def pair(self):
        if self.visitor and self.offer:
            self.session, sequence = self.offer
            self.offer = None
            self.last_seen = self.clock()
            self.ack(sequence)

    def lost(self):
        if self.session:
            self.send(ABORT, 0)
        self.reset()

    def reset(self):
        self.session = 0
        self.offer = self.pending = self.answer = None
        self.print_sequence = self.last_print = self.last_cancel = None
        self.print_data.clear()
        self.closing = None
        self.visitor = None
        self.disconnect()

    def feed_network(self, data):
        if not self.visitor:
            return
        try:
            self.visitor.feed(data)
            self.deliver()
        except BufferError:
            self.lost()

    def deliver(self):
        if not self.pending or not self.visitor:
            return
        sequence, capacity = self.pending
        if self.answer is None:
            if not self.visitor.lines:
                return
            status, text = self.visitor.lines.popleft()
            payload = m8_encode(text) if not status else b''
            if len(payload) > capacity:
                status, payload = TOO_LONG, b''
            self.answer = status, payload
        status, payload = self.answer
        if status:
            self.ack(sequence, status)
            return
        for at in range(0, max(1, len(payload)), 32):
            chunk = payload[at:at + 32]
            self.send(DATA | (MORE if at + len(chunk) < len(payload) else 0), sequence, at, chunk)

    def receive(self, kind, session, sequence, offset, data):
        if kind == OPEN:
            if self.session == session:
                self.ack(sequence)
            elif not self.session:
                self.offer = session, sequence
                self.pair()
            return
        if session != self.session or not self.session:
            # An abandoned OPEN must also be cancellable before pairing.
            if kind == ABORT and self.offer and self.offer[0] == session:
                self.offer = None
            return
        self.last_seen = self.clock()
        if kind == PONG:
            return
        if kind == ABORT:
            self.reset()
            return
        if kind == CLOSE:
            self.closing = sequence
            self.finish_close()
            return
        if kind == INPUT_ACK:
            if self.pending and sequence == self.pending[0]:
                self.pending = self.answer = None
            return
        if kind == INPUT and len(data) == 1:
            self.last_print = self.last_cancel = None
            if self.pending is None or self.pending[0] != sequence:
                self.pending, self.answer = (sequence, data[0]), None
            self.deliver()
            return
        if kind == CANCEL:
            self.last_print = None
            if sequence == self.last_cancel:
                self.ack(sequence)
                return
            self.pending = self.answer = None
            def done():
                self.last_cancel = sequence
                self.ack(sequence)
            self.visitor.cancel(done)
            return
        if kind & ~MORE != PRINT:
            return
        self.last_cancel = None
        if sequence == self.last_print:
            if not kind & MORE:
                self.ack(sequence)
            return
        newline, at = bool(offset & 0x8000), offset & 0x7fff
        if at == 0:
            self.print_sequence, self.print_data = sequence, bytearray()
        if sequence != self.print_sequence or at != len(self.print_data):
            return
        if len(self.print_data) + len(data) > 255:
            self.ack(sequence, TOO_LONG)
            return
        self.print_data.extend(data)
        if not kind & MORE:
            try:
                output = m8_decode(bytes(self.print_data)) + ('\n' if newline else '')
                self.network(output.replace('\n', '\r\n').encode('utf-8').replace(b'\xff', b'\xff\xff'))
            except UnicodeError:
                self.ack(sequence, BAD_TEXT)
                return
            self.last_print = sequence
            self.ack(sequence)

    def tick(self):
        self.finish_close()
        now = self.clock()
        if self.session:
            if now - self.last_seen > 15:
                self.reset()
            elif now - self.last_ping > 2:
                self.last_ping = now
                self.send(PING, 0)

    def finish_close(self):
        if self.closing is not None and self.drained():
            self.ack(self.closing)
            self.reset()


def serve(port, host, tcp_port):
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((host, tcp_port))
    listener.listen(1)
    listener.setblocking(False)
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    previous = termios.tcgetattr(fd)
    visitor = None
    serial_out, network_out = bytearray(), bytearray()
    selector = selectors.DefaultSelector()
    selector.register(fd, selectors.EVENT_READ, 'serial')
    selector.register(listener, selectors.EVENT_READ, 'listen')

    def disconnect():
        nonlocal visitor
        if visitor:
            selector.unregister(visitor)
            visitor.close()
            visitor = None
        network_out.clear()

    def queue_serial(data):
        if len(serial_out) + len(data) > 4096:
            raise BufferError('USB output queue full')
        serial_out.extend(data)

    def queue_network(data):
        if len(network_out) + len(data) > 4096:
            raise BufferError('visitor output queue full')
        network_out.extend(data)

    bridge = Bridge(queue_serial, queue_network, disconnect,
                    drained=lambda: not network_out)
    decoder = Decoder(bridge.receive)
    try:
        tty.setraw(fd)
        print(f'BBS bridge: {port} -> {host}:{listener.getsockname()[1]}', file=sys.stderr, flush=True)
        while True:
            selector.modify(fd, selectors.EVENT_READ | (selectors.EVENT_WRITE if serial_out else 0), 'serial')
            if visitor:
                selector.modify(visitor, selectors.EVENT_READ | (selectors.EVENT_WRITE if network_out else 0), 'visitor')
            # Drain visitor bytes before USB CANCEL acknowledgement.
            for key, events in sorted(selector.select(.1), key=lambda pair: pair[0].data == 'serial'):
                if key.data == 'listen':
                    client, _ = listener.accept()
                    if visitor:
                        client.sendall(b'BBS busy\r\n')
                        client.close()
                    else:
                        visitor = client
                        visitor.setblocking(False)
                        selector.register(visitor, selectors.EVENT_READ, 'visitor')
                        bridge.attach()
                elif key.data == 'serial':
                    if events & selectors.EVENT_WRITE:
                        try:
                            n = os.write(fd, serial_out)
                            del serial_out[:n]
                        except BlockingIOError:
                            pass
                    if events & selectors.EVENT_READ:
                        data = os.read(fd, 1024)
                        if not data:
                            raise OSError('USB disconnected')
                        decoder.feed(data)
                elif visitor:
                    try:
                        if events & selectors.EVENT_WRITE:
                            n = visitor.send(network_out)
                            del network_out[:n]
                        if events & selectors.EVENT_READ:
                            data = visitor.recv(1024)
                            if data:
                                bridge.feed_network(data)
                            else:
                                bridge.lost()
                    except (ConnectionError, OSError):
                        bridge.lost()
            bridge.tick()
    finally:
        bridge.lost()
        # Best effort ABORT before releasing CDC; never block shutdown.
        if serial_out:
            try:
                os.write(fd, serial_out)
            except OSError:
                pass
        disconnect()
        selector.close()
        listener.close()
        termios.tcsetattr(fd, termios.TCSANOW, previous)
        os.close(fd)


def package(output):
    root = Path(__file__).resolve().parents[2]
    source = root / 'programs/network/BBS'
    if not source.is_dir():
        source = root / 'C6/network/BBS'  # Also works from an extracted package.
    if not (source / 'autoexec.m61').is_file():
        raise OSError('BBS sources not found next to the host tools')
    files = [(path, 'C6/network/BBS/' + path.relative_to(source).as_posix())
             for path in sorted(source.rglob('*')) if path.is_file()]
    host = Path(__file__).resolve().parents[1]
    files += [(host / name, 'host/' + name) for name in
              ('bbs.cmd', '.bbs/bbs.py', '.bbs/bbs.ps1', '.bbs/bridge.ps1')]
    codec = host / 'm8_codec.py'
    if not codec.is_file():
        codec = host / '.bbs/m8_codec.py'
    files.append((codec, 'host/.bbs/m8_codec.py'))
    files += [(root / name, name) for name in ('BBS.md', 'BASIC-TEXT.md')]
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path, name in files:
            archive.write(path, name)
    print(f'{output}: {len(files)} files; firmware/System must be built from this branch')


def main():
    parser = argparse.ArgumentParser(prog='bbs.cmd', description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest='command', required=True)
    server = commands.add_parser('serve', help='bridge USB CDC to one TCP/Telnet visitor', allow_abbrev=False)
    server.add_argument('--port', required=True, help='USB CDC path, e.g. /dev/cu.usbmodem...')
    server.add_argument('--host', default='127.0.0.1')
    server.add_argument('--listen', type=int, default=2323)
    pack = commands.add_parser('package', help='package BBS and both host backends', allow_abbrev=False)
    pack.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'serve' and not 0 <= args.listen <= 65535:
        parser.error('--listen must be in 0..65535')
    try:
        if args.command == 'serve':
            serve(args.port, args.host, args.listen)
        else:
            package(args.output)
    except KeyboardInterrupt:
        pass
    except (OSError, BufferError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
