#!/usr/bin/env python3
"""Reject unsafe Flash spans before the RP2040 placement experiment writes."""
import hashlib
import importlib.util
from pathlib import Path

path = Path(__file__).with_name('run-pico-flash.py')
spec = importlib.util.spec_from_file_location('placement', path)
placement = importlib.util.module_from_spec(spec)
spec.loader.exec_module(placement)
placement.verify_payload_receipts(path.parent / 'evidence/m0-prepared/placement-payload')
firmware = b'firmware' * 4096
backup = firmware + b'\xff' * (placement.FLASH_BYTES - len(firmware))
payload = b'\x70\x47' * 2170
layout = dict(cpu='m0', base=0x101E0000, bytes=len(payload),
              sha256=hashlib.sha256(payload).hexdigest())
manifest = dict(flash_bytes=len(firmware), bin_sha256=hashlib.sha256(firmware).hexdigest(),
                settings_flash_offset=placement.SETTINGS_OFFSET)
result = placement.make_candidate(backup, payload, layout, firmware, manifest)
start = layout['base'] - placement.FLASH_BASE
assert result[:start] == backup[:start]
assert result[start:start + len(payload)] == payload
assert result[start + len(payload):] == backup[start + len(payload):]
cases = [
    (backup[:-1], payload, layout, firmware, manifest),
    (backup, payload, dict(layout, base=0x10001000), firmware, manifest),
    (backup, payload, dict(layout, base=0x101E0001), firmware, manifest),
    (backup, payload, dict(layout, base=0x101FE000), firmware, manifest),
    (backup, payload, dict(layout, cpu='m4'), firmware, manifest),
    (backup, payload + b'\0', layout, firmware, manifest),
    (backup, payload, dict(layout, sha256='0' * 64), firmware, manifest),
    (backup, payload, layout, firmware[:-1] + b'!', manifest),
    (backup[:start] + b'\0' + backup[start + 1:], payload, layout, firmware, manifest),
]
for index, arguments in enumerate(cases):
    try:
        placement.make_candidate(*arguments)
    except AssertionError:
        pass
    else:
        raise AssertionError(('Unsafe candidate accepted', index))
print('PASS: unchanged firmware/settings, exact payload, 9 unsafe inputs rejected')
