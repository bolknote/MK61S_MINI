#!/usr/bin/env python3
"""CRC-corrupt screen transport must never be accepted as a valid frame."""
import binascii
import struct
from hil_language_source_scan import MeasurePort
from hil_portable_apps import cobs_encode

port = MeasurePort.__new__(MeasurePort)
port.keyboard_layout = 1
port.caps = None; port.attached = False
port.frames = []; port.pending = None; port.pages = set()
port.bad_packets = 0; port.drop_frame = False

def packet(kind, payload):
    raw = b'MS\x02' + bytes((kind, 0)) + struct.pack('<HH', 0, len(payload)) + payload
    return cobs_encode(raw + struct.pack('<H', binascii.crc_hqx(raw, 65535)))

port.receive_packet(b'\x05a')
assert port.bad_packets == 1 and port.drop_frame and not port.frames

bitmap = bytes(1536)
for frame_id in (1, 2):
    port.receive_packet(packet(0x20, struct.pack('<HBB', frame_id, 1, 8)))
    for page in range(8):
        data = struct.pack('<HBBBB', frame_id, 0, page, 192, 0) + bytes(192)
        encoded = packet(0x21, data)
        if frame_id == 1 and page == 3:
            damaged = bytearray(encoded); damaged[-1] ^= 1
            port.receive_packet(damaged)
        else: port.receive_packet(encoded)
    port.receive_packet(packet(0x22, struct.pack('<HH', frame_id, binascii.crc_hqx(bitmap, 65535))))
    assert len(port.frames) == frame_id - 1
assert port.bad_packets == 2 and port.frames == [bitmap] and not port.drop_frame
print('Compiler HIL: corrupt COBS/CRC rejected, partial frame discarded, fresh full frame verified PASS')
