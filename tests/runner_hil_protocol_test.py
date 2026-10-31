#!/usr/bin/env python3
"""Runner HIL protocol regressions; no serial descriptors are opened."""
import binascii
import struct

from hil_portable_apps import cobs_encode
from hil_runner_campaign import TimedPort


def packet(kind, payload):
    raw = b'MS\x02' + bytes((kind, 0)) + struct.pack('<HH', 1, len(payload)) + payload
    return cobs_encode(raw + struct.pack('<H', binascii.crc_hqx(raw, 65535)))


def receiver():
    p = TimedPort.__new__(TimedPort)
    p.frames, p.timeline = [], []
    p.accept_frames = p.attached = True
    p.native_display = False
    p.keyboard_layout = 1
    p.detach_watch = False
    p.detach_offer = p.server_detach = None
    return p


def main():
    p = receiver()
    offer = bytes((192, 0, 64, 8, 0, 0, 0, 0, 1, 40))
    # Host DETACH is one-way. The subsequent server OFFER proves WAITING;
    # waiting for an echoed DETACH would misclassify a successful cleanup.
    p.receive_packet(packet(0x10, offer))
    assert p.attached and p.detach_offer is None
    p.detach_watch = True
    p.receive_packet(packet(0x10, offer))
    assert not p.attached and p.detach_offer

    p = receiver()
    p.detach_watch = True
    bad = bytearray(packet(0x10, offer))
    bad[-1] ^= 1
    try:
        p.receive_packet(bytes(bad))
    except AssertionError:
        pass
    else:
        raise AssertionError('Corrupt OFFER was accepted')
    assert p.detach_offer is None and p.attached

    p.receive_packet(packet(0x10, bytes((64, 1, 64, 8)) + offer[4:]))
    assert p.detach_offer is None, 'Foreign display OFFER proved detach'
    p.receive_packet(packet(0x13, b''))
    assert p.server_detach and not p.attached
    p.receive_packet(packet(0x12, offer + bytes(4)))
    assert p.attached and p.server_detach is None, 'Old DETACH survived a new session'
    print('Runner HIL: one-way DETACH/OFFER, server DETACH, CRC, display and session boundaries: OK')


if __name__ == '__main__':
    main()
