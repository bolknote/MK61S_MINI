"""Frozen established project methods; stdlib only. No import-time device access."""
import binascii
import fcntl
import hashlib
import os
import re
import select
import statistics
import struct
import termios
import time
PROMPT=re.compile(rb"(?:^|[\r\n])[^\r\n]*>\s*$")
def cobs_encode(data):
    out = bytearray([0])
    start = 0
    code = 1
    for byte in data:
        if byte == 0:
            out[start] = code
            start = len(out)
            out.append(0)
            code = 1
        else:
            out.append(byte)
            code += 1
            if code == 255:
                out[start] = code
                start = len(out)
                out.append(0)
                code = 1
    out[start] = code
    return bytes(out)

def cobs_decode(data):
    out = bytearray()
    position = 0
    while position < len(data):
        code = data[position]
        position += 1
        assert code and position + code - 1 <= len(data)
        out.extend(data[position:position + code - 1])
        position += code - 1
        if code < 255 and position < len(data):
            out.append(0)
    return bytes(out)

def packbits(data):
    out = bytearray()
    i = 0
    while i < len(data):
        count = data[i]
        i += 1
        assert count != 128
        if count < 128:
            assert i + count + 1 <= len(data)
            out.extend(data[i:i + count + 1])
            i += count + 1
        else:
            assert i < len(data)
            out.extend([data[i]] * (257 - count))
            i += 1
    return bytes(out)

class Port:

    def __init__(self, path: str, require_echo: bool=False):
        self.path = path
        self.require_echo = require_echo
        self.fd = -1
        canonical = os.path.realpath(path).replace('/dev/tty.', '/dev/cu.')
        key = hashlib.sha256(canonical.encode()).hexdigest()[:20]
        self.lock_fd = os.open(f'/tmp/mk61-hil-cdc-{os.geteuid()}-{key}.lock', os.O_CREAT | os.O_RDWR, 384)
        try:
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            fcntl.ioctl(self.fd, termios.TIOCEXCL)
            attrs = termios.tcgetattr(self.fd)
            attrs[0] = 0
            attrs[1] = 0
            attrs[2] &= ~(termios.CSIZE | termios.PARENB | termios.CSTOPB)
            attrs[2] |= termios.CS8 | termios.CREAD | termios.CLOCAL
            attrs[3] = 0
            attrs[4] = termios.B115200
            attrs[5] = termios.B115200
            attrs[6][termios.VMIN] = 0
            attrs[6][termios.VTIME] = 0
            termios.tcsetattr(self.fd, termios.TCSANOW, attrs)
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        if self.fd >= 0:
            try:
                fcntl.ioctl(self.fd, termios.TIOCNXCL)
            except OSError:
                pass
            os.close(self.fd)
            self.fd = -1
        if self.lock_fd >= 0:
            fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
            os.close(self.lock_fd)
            self.lock_fd = -1

    def __enter__(self) -> 'Port':
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def drain(self) -> None:
        while True:
            readable, _, _ = select.select([self.fd], [], [], 0)
            if not readable:
                return
            if not os.read(self.fd, 4096):
                return

    def write_line(self, text: str) -> None:
        payload = text.encode('cp1251') + b'\r'
        offset = 0
        while offset < len(payload):
            _, writable, _ = select.select([], [self.fd], [], 1.0)
            if not writable:
                raise TimeoutError(f'serial write timeout: {self.path}')
            offset += os.write(self.fd, payload[offset:])

    def read_prompt(self, timeout: float) -> str:
        deadline = time.monotonic() + timeout
        data = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            readable, _, _ = select.select([self.fd], [], [], min(0.1, remaining))
            if readable:
                block = os.read(self.fd, 4096)
                if block:
                    data.extend(block)
                    if PROMPT.search(data):
                        return data.decode('cp1251', 'replace')
        raise TimeoutError(f'terminal prompt timeout on {self.path}: {data!r}')

    def command(self, text: str, timeout: float=4.0) -> str:
        self.drain()
        self.write_line(text)
        if not getattr(self, 'require_echo', False):
            return self.read_prompt(timeout)
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f'no correlated reply for {text!r}')
            reply = self.read_prompt(remaining)
            if re.search('(?m)^(?:[^\\r\\n]*>\\s*)?' + re.escape(text) + '\\r?$', reply):
                return reply

class ScreenPort(Port):

    def __init__(self, path, keyboard_layout=1):
        super().__init__(path)
        assert keyboard_layout in (0, 1, 2)
        self.keyboard_layout = keyboard_layout
        self.native_display = False
        self.frame_width = 192
        self.frame_height = 64
        self.packet = None
        self.text = bytearray()
        self.frames = []
        self.sequence = 0
        self.attached = False
        self.next_ping = 0
        self.caps = None
        self.pending = None
        self.pages = set()

    def send(self, kind, payload=b''):
        raw = b'MS\x02' + bytes((kind, 0)) + struct.pack('<HH', self.sequence, len(payload)) + payload
        self.sequence = self.sequence + 1 & 65535
        raw += struct.pack('<H', binascii.crc_hqx(raw, 65535))
        wire = b'\x00' + cobs_encode(raw) + b'\x00'
        offset = 0
        while offset < len(wire):
            offset += os.write(self.fd, wire[offset:])

    def receive_packet(self, encoded):
        raw = cobs_decode(encoded)
        assert len(raw) >= 11 and raw[:3] == b'MS\x02'
        assert binascii.crc_hqx(raw[:-2], 65535) == struct.unpack_from('<H', raw, len(raw) - 2)[0]
        size = struct.unpack_from('<H', raw, 7)[0]
        assert len(raw) == size + 11
        kind, payload = (raw[3], raw[9:-2])
        if kind == 18:
            self.caps = payload
            if self.native_display:
                assert len(payload) == 16 and payload[:4] == bytes((64, 1, 64, 8)) and (payload[14:] == bytes((64, 1)))
                self.frame_width = self.frame_height = 320
            else:
                assert payload[:4] == bytes((192, 0, 64, 8))
            assert payload[8:10] == bytes((self.keyboard_layout, 40)), 'unexpected keyboard layout'
            self.attached = True
            self.next_ping = time.monotonic() + 0.7
        elif kind == 32:
            self.frame_id, full, pages = struct.unpack('<HBB', payload)
            assert full == 1 and pages == (80 if self.native_display else 8)
            self.pending = bytearray(self.frame_width * self.frame_height // 8)
            self.pages = set()
        elif kind == 33:
            frame_id, x, page, width, codec = struct.unpack_from('<HBBBB', payload)
            assert frame_id == self.frame_id and page < self.frame_height // 8
            assert x in ((0, 160) if self.native_display else (0,)) and width == (160 if self.native_display else 192)
            assert (page, x) not in self.pages and codec in (0, 1)
            pixels = payload[6:] if codec == 0 else packbits(payload[6:])
            assert len(pixels) == width
            self.pending[page * self.frame_width + x:page * self.frame_width + x + width] = pixels
            self.pages.add((page, x))
        elif kind == 34:
            frame_id, checksum = struct.unpack('<HH', payload)
            assert frame_id == self.frame_id and len(self.pages) == (80 if self.native_display else 8)
            assert binascii.crc_hqx(self.pending, 65535) == checksum
            self.frames.append(bytes(self.pending))
            self.pending = None
        elif kind == 19:
            self.attached = False

    def pump(self, duration=0.05):
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            now = time.monotonic()
            if self.attached and now >= self.next_ping:
                self.send(20, b'a\x00')
                self.next_ping = now + 0.7
            ready, _, _ = select.select([self.fd], [], [], min(0.03, max(0, deadline - now)))
            if not ready:
                continue
            for byte in os.read(self.fd, 8192):
                if byte == 0:
                    if self.packet is None:
                        self.packet = bytearray()
                    elif self.packet:
                        self.receive_packet(self.packet)
                        self.packet = None
                elif self.packet is None:
                    self.text.append(byte)
                else:
                    self.packet.append(byte)

class MathPort(ScreenPort):

    def command(self, command, timeout=5):
        if command.startswith('fsget '):
            timeout = max(timeout, 120)
        self.pump(0.002)
        start = len(self.text)
        self.write_line(command)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.pump(0.002)
            if re.search(b'(?:^|[\\r\\n])mk61> ', self.text[start:]):
                return self.text[start:].decode('cp1251', 'replace')
        raise TimeoutError((command, bytes(self.text[start:])))

    def status(self):
        self.pump(0.03)
        start = len(self.text)
        os.write(self.fd, b'\x05')
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            self.pump(0.05)
            if re.search(b'MSC_SD_READ_US=[^\\r\\n]*\\r?\\n', self.text[start:]):
                return self.text[start:].decode('utf-8', 'replace')
        raise TimeoutError(bytes(self.text[start:]))

def posix_cksum(payload: bytes) -> int:
    """The fsget wire checksum: POSIX cksum, including the byte length."""

    def update(crc: int, value: int) -> int:
        crc ^= value << 24
        for _ in range(8):
            crc = crc << 1 ^ (79764919 if crc & 2147483648 else 0)
            crc &= 4294967295
        return crc
    crc = 0
    for value in payload:
        crc = update(crc, value)
    length = len(payload)
    while length:
        crc = update(crc, length & 255)
        length >>= 8
    return crc ^ 4294967295

def require_file_contents(report: str, expected: bytes) -> None:
    """Verify C6 bytes, not merely a directory entry or the host's cache."""
    markers = [line for line in report.splitlines() if line.startswith('@MKC:')]
    checksum = posix_cksum(expected)
    if len(markers) < 2 or markers[0] != f'@MKC:GET {len(expected)} {checksum}' or markers[-1] != f'@MKC:END {len(expected)} {checksum}':
        raise AssertionError(f'invalid C6 file readback framing/checksum:\n{report}')
    received = bytearray()
    for line in markers[1:-1]:
        match = re.fullmatch('@MKC:DATA ([0-9]+) ([0-9A-Fa-f]+)', line)
        if not match or int(match.group(1)) != len(received):
            raise AssertionError(f'invalid C6 file readback chunk: {line!r}')
        encoded = match.group(2)
        if len(encoded) % 2 or len(received) + len(encoded) // 2 > len(expected):
            raise AssertionError(f'invalid C6 file readback size: {line!r}')
        received.extend(bytes.fromhex(encoded))
    if received != expected:
        raise AssertionError('C6 file readback differs from the written fixture')

def read_file(port, path, *, m8=False):
    report = port.command(f'fsget "{path}"' + (' m8' if m8 else ''), timeout=15)
    data = bytearray()
    for offset, block in re.findall('(?m)^@MKC:DATA (\\d+) ([0-9A-Fa-f]+)\\r?$', report):
        assert int(offset) == len(data), report
        data.extend(bytes.fromhex(block))
    require_file_contents(report, bytes(data))
    return bytes(data)

def write_file(port, path, data):
    checksum = posix_cksum(data)
    report = port.command(f'fsput begin "{path}" {len(data)} {checksum}')
    assert f'@MKC:READY {len(data)}' in report, report
    for offset in range(0, len(data), 96):
        report = port.command(f'fsput data {offset} {data[offset:offset + 96].hex()}')
        assert f'@MKC:ACK {min(offset + 96, len(data))}' in report, report
    report = port.command('fsput end', timeout=30)
    assert f'@MKC:DONE {len(data)} {checksum}' in report, report
    assert read_file(port, path) == data, path

def canonical_state_reply(reply: str) -> str:
    """Ignore only the optional final prompt space, retaining all state bytes.

    CDC can split immediately after '>'; read_prompt then returns before the
    final space arrives. Values, program bytes, cwd and line endings stay exact.
    """
    assert re.search('(?:^|[\\r\\n])[^\\r\\n]*> ?\\Z', reply), 'Missing state prompt'
    return reply[:-1] if reply.endswith('> ') else reply

def ordered(x, width):
    sign = 1 << width - 1
    mask = (1 << width) - 1
    return ~x & mask if x & sign else x | sign

def order_balanced(timings):
    rounds = len(timings['own']['paired_us'])
    assert rounds == len(timings['qfplib']['paired_us']) and rounds >= 2
    paired = {}
    for name in ('own', 'qfplib'):
        values = timings[name]['paired_us']
        paired[name] = [(values[i] + values[i + 1]) / 2 for i in range(0, rounds - 1, 2)]
    medians = {name: statistics.median(v) for name, v in paired.items()}
    differences = [x - y for x, y in zip(paired['own'], paired['qfplib'])]
    return dict(rounds_used=2 * (rounds // 2), rounds_excluded=rounds % 2, pair_means_us=paired, us_per_call=medians, own_over_qfplib=medians['own'] / medians['qfplib'] if medians['qfplib'] > 0 else None, paired_differences_us=differences, median_paired_delta_us=statistics.median(differences), mean_paired_delta_us=statistics.mean(differences), empirical_delta_range_us=[min(differences), max(differences)], method='Average each adjacent pair of rounds with opposite library order, then take the median of those pair averages. The empirical range is not a confidence interval.')

def decode(raw, chunk, inputs):
    h = struct.unpack_from('<10I', raw)
    cases, loops = (chunk['cases'], chunk['loops'])
    kind = chunk['kind']
    assert h[0] == 1295012432 and h[1] in (1, 2, 3, 4), h
    rounds = 9 if h[1] in (1, 2) else 12
    cached = h[1] in (2, 4)
    assert h[2:7] == (chunk['index'], kind, cases, loops, rounds), h
    assert not h[7] and h[8] == 4294967295, ('Owned result mismatch', h)
    counter_offset = 40 + 16 * rounds
    result_offset = counter_offset + (32 * rounds if cached else 0)
    assert len(raw) == result_offset + 16 * cases
    timings = struct.unpack_from('<' + 'I' * (4 * rounds), raw, 40)
    n = cases * loops
    series = {}
    for index, name in enumerate(('own', 'qfplib')):
        start = index * rounds
        elapsed = timings[start:start + rounds]
        control = timings[2 * rounds + start:3 * rounds + start]
        paired = [(x - y) / n for x, y in zip(elapsed, control)]
        series[name] = dict(median_us=statistics.median(paired), mean_us=statistics.mean(paired), min_us=min(paired), max_us=max(paired), raw_batch_us=list(elapsed), control_batch_us=list(control), paired_us=paired)
        if cached:
            counters = struct.unpack_from('<' + 'I' * (8 * rounds), raw, counter_offset)
            hits = counters[start:start + rounds]
            accesses = counters[2 * rounds + start:3 * rounds + start]
            control_hits = counters[4 * rounds + start:5 * rounds + start]
            control_accesses = counters[6 * rounds + start:7 * rounds + start]
            assert all((0 <= x <= y < 4294967295 for x, y in zip(hits + control_hits, accesses + control_accesses)))
            misses = [(acc - hit - (ca - ch)) / n for acc, hit, ca, ch in zip(accesses, hits, control_accesses, control_hits)]
            series[name]['cache'] = dict(hits=list(hits), accesses=list(accesses), control_hits=list(control_hits), control_accesses=list(control_accesses), paired_misses_per_call=misses, median_misses_per_call=statistics.median(misses), median_accesses_per_call=statistics.median(((x - y) / n for x, y in zip(accesses, control_accesses))))
    wrong = 0
    worst = 0
    rows = []
    width = 32 if kind in (6, 7, 11, 12) else 64
    floating = kind <= 5 or kind in (10, 11)
    for i in range(cases):
        a, b, expected = struct.unpack_from('<3Q', inputs, 32 + 24 * i)
        own, qfp = struct.unpack_from('<2Q', raw, result_offset + 16 * i)
        assert own == expected, (chunk['operation'], hex(a), hex(b), hex(own), hex(expected))
        error = abs(ordered(qfp, width) - ordered(expected, width)) if floating else int(qfp != expected)
        wrong += qfp != expected
        worst = max(worst, error)
        rows.append(dict(a=f'{a:016X}', b=f'{b:016X}', expected=f'{expected:016X}', own=f'{own:016X}', qfplib=f'{qfp:016X}'))
    row = dict(index=chunk['index'], stream_index=chunk['stream_index'], part=chunk['part'], operation=chunk['operation'], stream=chunk['stream'], cases=cases, samples=n, rounds=rounds, app_warmup_us=h[9], timings=series, order_balanced=order_balanced(series), owned_wrong_rounding=0, qfplib_wrong_results=wrong, qfplib_worst_ulp=worst if floating else None, results=rows)
    row.update({k: chunk[k] for k in ('reference_kind', 'reference_formula', 'reference_domain') if k in chunk})
    return row
