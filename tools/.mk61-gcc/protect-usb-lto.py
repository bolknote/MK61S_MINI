#!/usr/bin/env python3
"""Keep STM32 USB --wrap targets outside whole-program LTO before linking."""

from pathlib import Path
import subprocess
import sys


# Protect the definitions interposed by --wrap. Keep the HAL bridge in LTO:
# HAL's weak no-op callbacks must see its strong MSP/IRQ implementations.
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


if __name__ == '__main__':
    if len(sys.argv) < 4:
        raise SystemExit('usage: protect-usb-lto.py BUILD USB_LIBRARY COMPILER [FLAGS...]')
    protect(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:])
