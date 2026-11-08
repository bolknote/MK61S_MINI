#!/usr/bin/env python3
"""Diagnostic packet collector; every corrupted packet fails the owning row.

Keep reading after bad data so an expected fault cannot destroy subsequent
RAM observations. Frame assembly is deliberately outside this collector;
packet CRC and the original nonce-PONG deadline remain mandatory.
"""
import binascii
import struct
import time
from hil_portable_apps import cobs_decode
from hil_vm_cache_latency import PingPort


class CapturePort(PingPort):
    def __init__(self, path):
        self.bad_packets = []
        self.types = {}
        self.valid_packets = 0
        self.responses = []
        super().__init__(path)

    def receive_packet(self, encoded):
        try:
            raw = cobs_decode(encoded)
            assert len(raw) >= 11 and raw[:3] == b'MS\x02', 'header'
            assert len(raw) == struct.unpack_from('<H', raw, 7)[0] + 11, 'length'
            assert binascii.crc_hqx(raw[:-2], 65535) == struct.unpack_from('<H', raw, len(raw)-2)[0], 'CRC'
        except (AssertionError, IndexError, struct.error) as error:
            self.bad_packets.append(dict(at=time.monotonic(), reason=str(error),
                                         cobs=bytes(encoded).hex(),
                                         raw=raw.hex() if 'raw' in locals() else None))
            return
        self.valid_packets += 1
        self.types[str(raw[3])] = self.types.get(str(raw[3]), 0) + 1
        # GAP/CPU diagnostics use terminal/file results. Keep transport CRC
        # independent from screen assembly, which cannot recover a lost rect.
        if raw[3] >= 0x20:
            if raw[3] == 0x26 and len(raw) == 23:
                self.responses.append(struct.unpack('<III', raw[9:-2]))
            self.packets_crc_verified += 1
            return
        super().receive_packet(encoded)
