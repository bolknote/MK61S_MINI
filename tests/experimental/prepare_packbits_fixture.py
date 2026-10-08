#!/usr/bin/env python3
"""Prepare a private profiling fixture for two exact qualification images.

Ordinary APPs block terminal command dispatch. This test fixture uses the
already existing start/stop functions in the verified resident images, with
both firmware build IDs checked before any callback. These addresses are
private to this experiment; this APP must never be distributed as a product.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tests'))
from hil_packbits_firmware import firmware_info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--firmware-dir', type=Path, required=True)
    parser.add_argument('--arm-toolchain-bin', type=Path, required=True)
    args = parser.parse_args()
    root = args.firmware_dir.resolve()
    out = root/'qualified-fixture'
    out.mkdir(exist_ok=True)
    variants, evidence = [], {}
    for name in ('baseline','candidate'):
        build = root/name/'build'
        symbols = subprocess.check_output([str(args.arm_toolchain_bin/'arm-none-eabi-nm'),
            '-C','--defined-only',str(build/'mk61s-M.ino.elf')],text=True).splitlines()
        def address(symbol):
            hits = [int(x.split()[0],16)|1 for x in symbols if x.endswith(' T '+symbol)]
            assert len(hits)==1 and 0x08000000<hits[0]<0x08080000, (name,symbol,hits)
            return hits[0]
        image = firmware_info(build/'mk61s-M.ino.bin')
        start, stop = address('dwt_profiler::start()'), address('dwt_profiler::stop()')
        footer = 0x08000000+image['footer']+24
        variants.append((footer,int(image['build'],16),start,stop))
        evidence[name] = {'build':image['build'],'image_sha256':image['sha256'],
            'footer_build_word':hex(footer),'start':hex(start),'stop':hex(stop)}
    header = ('/* Test-only callbacks, guarded by exact sealed build IDs. */\n'
        '#include <stdbool.h>\n#include <stdint.h>\n'
        'typedef struct { bool (*start)(void); void (*stop)(void); } profile_callbacks;\n'
        'static const profile_callbacks* qualified_profiler(void) {\n')
    for i,(footer,build,start,stop) in enumerate(variants):
        header += f'  static const profile_callbacks variant_{i} = {{ (bool(*)(void))(uintptr_t)0x{start:08X}U, (void(*)(void))(uintptr_t)0x{stop:08X}U }};\n'
        header += f'  if(*(const volatile uint32_t*)(uintptr_t)0x{footer:08X}U == 0x{build:08X}U) return &variant_{i};\n'
    header += '  return 0;\n}\n'
    (out/'packbits_profile_callbacks.h').write_text(header)
    source = out/'entry.c'
    source.write_text('#define PACKBITS_QUALIFIED_CALLBACKS 1\n#include "'+
                      str(ROOT/'tests/experimental/packbits_frame_hil.c')+'"\n')
    (out/'callbacks.json').write_text(json.dumps(evidence,indent=2)+'\n')
    subprocess.run([sys.executable,str(ROOT/'tools/build_portable_app.py'),
        '--name','PACKCHK','--source',str(source),'--include',str(out),
        '--arm-toolchain-bin',str(args.arm_toolchain_bin),
        '--output-dir',str(out/'build')],check=True)


if __name__ == '__main__':
    main()
