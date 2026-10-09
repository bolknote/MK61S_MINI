#!/usr/bin/env python3
"""Build the qualification APP against an exact sealed resident ELF/BIN pair.

Only public runtime slots are used except strcmp/strnlen, which have no slots.
Their test-only addresses are pinned to the full resident CRC and public
memcpy/memcmp anchors. This tool never connects to or flashes a device.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests'))
from hil_packbits_firmware import firmware_info

FUNCTIONS = ('memcpy', 'memcmp', 'memmove', 'memset', 'strlen', 'strnlen', 'strcmp', 'strncmp')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bin', type=Path, required=True)
    parser.add_argument('--elf', type=Path, required=True)
    parser.add_argument('--arm-toolchain-bin', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    fixture = firmware_info(args.bin)
    image = args.bin.read_bytes()
    toolchain = args.arm_toolchain_bin.resolve()
    with tempfile.TemporaryDirectory(prefix='mk61-aux-pair-') as temporary:
        flat = Path(temporary) / 'resident.bin'
        subprocess.run([str(toolchain / 'arm-none-eabi-objcopy'), '-O', 'binary',
                        str(args.elf.resolve()), str(flat)], check=True)
        assert flat.read_bytes() == image, 'ELF does not reproduce the exact sealed BIN'
    listing = subprocess.check_output([str(toolchain / 'arm-none-eabi-nm'),
                                      '-P', '-S', str(args.elf.resolve())], text=True)
    symbols = {parts[0]: parts[1:] for line in listing.splitlines()
               if len(parts := line.split()) >= 4}
    fixture['symbols'] = {}
    for name in FUNCTIONS:
        kind, value, size = symbols[name][:3]
        address = int(value, 16)
        assert kind == 'T' and 0x08000000 <= address < 0x08080000, (name, kind, value)
        offset = address - 0x08000000
        assert offset + 32 <= len(image) and int(size, 16) > 0
        fixture['symbols'][name] = {'address': address | 1,
                                   'code_hex': image[offset:offset + 32].hex()}
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    defines = (('AUX_RESIDENT_STRCMP', 'strcmp'), ('AUX_RESIDENT_STRNLEN', 'strnlen'),
               ('AUX_ANCHOR_MEMCPY', 'memcpy'), ('AUX_ANCHOR_MEMCMP', 'memcmp'))
    (output / 'memory_aux_resident.hpp').write_text(
        '// Qualification-only addresses: generated from the exact sealed resident.\n' +
        ''.join(f'#define {macro} 0x{fixture["symbols"][name]["address"]:08X}U\n'
                for macro, name in defines))
    (output / 'resident.json').write_text(json.dumps(fixture, indent=2) + '\n')
    subprocess.run([sys.executable, str(ROOT / 'tools/build_portable_app.py'),
                    '--name', 'MEMAUX', '--shared-runtime', '--source',
                    str(ROOT / 'tests/experimental/memory_aux_hil.cpp'),
                    '--include', str(output), '--arm-toolchain-bin', str(toolchain),
                    '--output-dir', str(output)], check=True)


if __name__ == '__main__':
    main()
