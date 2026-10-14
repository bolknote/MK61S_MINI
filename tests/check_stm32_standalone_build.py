#!/usr/bin/env python3
"""Require the owned runtime and an explicit CMSIS/USB/LL source allowlist."""
import argparse
import json
from pathlib import Path
import shlex

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('compile_commands', type=Path)
a = p.parse_args()
entries = json.loads(a.compile_commands.read_text())
allowed = {
    'usb_device_core.c', 'usb_device_ioreq.c', 'usbd_desc.c',
    'cdc_queue.c', 'stm32f4xx_ll_usb.c',
    'startup_stm32f401xc.s', 'startup_stm32f411xe.s',
}
owned = 0
vendor = set()
for entry in entries:
    source = Path(entry['file']).resolve()
    assert source.name != 'ERM19264_graphics.cpp', 'generic graphics must not enter the native source set'
    args = entry.get('arguments') or shlex.split(entry['command'])
    if source.name == 'firmware_main.cpp' or source.parent.name == 'code':
        owned += 1
        assert '-DMK61_NATIVE_RUNTIME=1' in args, source
    else:
        assert source.name in allowed, ('unexpected runtime/library object', str(source))
        assert '/cores/arduino/' not in source.as_posix(), source
        vendor.add(source.name)
    assert not any('/cores/arduino' in v or '/libraries/SrcWrapper' in v for v in args), source
assert owned >= 100, 'project sources missing'
assert len(vendor) == 6 and any(s.startswith('startup_stm32') for s in vendor), vendor
assert any(Path(e['file']).name == 'stm32f4_runtime.cpp' for e in entries)
print('Standalone source gate: owned project/runtime + 6 CMSIS/USB/LL sources; no Arduino Core, HAL or generic libraries PASS')
