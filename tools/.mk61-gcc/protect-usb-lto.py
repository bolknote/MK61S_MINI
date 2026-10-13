#!/usr/bin/env python3
"""Keep STM32 USB --wrap targets outside whole-program LTO before linking."""

from pathlib import Path
import subprocess
import sys


# Protect definitions interposed by --wrap. F4 replaces the hardware bridge
# below; other targets retain the original strong HAL bridge in LTO.
SOURCES = ('src/cdc/usbd_cdc.c', 'src/usb_device_core.c')


def protect(build_path: Path, library: Path, command: list[str]) -> None:
    for source in SOURCES:
        matches = list((build_path / 'libraries' / 'USBDevice').rglob(Path(source).name + '.o'))
        if len(matches) != 1:
            raise ValueError(f'expected one {source} object, found {len(matches)}')
        # Arduino's compilation database must retain the ordinary compiler
        # invocation for APP packing and stack analysis. Recompile only the
        # two USB target units after Arduino has built them, before its link.
        subprocess.run([*command, '-fno-lto', str(library / source), '-o', str(matches[0])], check=True)
        print(f'USB LTO barrier: {source}', flush=True)

    if any(flag in command for flag in ('-DSTM32F401xC', '-DSTM32F401xE', '-DSTM32F411xE')):
        bridge = build_path / 'sketch/stm32f4_usb_device.cpp'
        matches = list((build_path / 'libraries' / 'USBDevice').rglob('usbd_conf.c.o'))
        if not bridge.is_file() or len(matches) != 1:
            raise ValueError('missing owned F4 USB bridge source/object in build snapshot')
        if bridge.is_file():
            # Replace the generic HAL bridge object; no installed core file is edited.
            subprocess.run([*command, '-std=gnu++17', '-fno-exceptions', '-fno-rtti',
                            '-fno-threadsafe-statics', '-DMK61_USB_BUILD_BRIDGE=1',
                            str(bridge), '-o', str(matches[0])], check=True)
            print('Owned F4 USB device bridge', flush=True)
            requests = bridge.with_name('stm32f4_usbd_ctlreq.c')
            matches = list((build_path / 'libraries' / 'USBDevice').rglob('usb_device_ctlreq.c.o'))
            if len(matches) != 1:
                raise ValueError('expected one USB control request object')
            subprocess.run([*command, '-DMK61_USB_BUILD_CTLREQ=1', str(requests),
                            '-o', str(matches[0])], check=True)
            print('Bounded F4 USB control requests', flush=True)



if __name__ == '__main__':
    if len(sys.argv) < 4:
        raise SystemExit('usage: protect-usb-lto.py BUILD USB_LIBRARY COMPILER [FLAGS...]')
    protect(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:])
