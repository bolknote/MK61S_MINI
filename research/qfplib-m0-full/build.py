#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build independent original/modified Qfplib images; no firmware linking."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

def main():
    root = Path(__file__).resolve().parent
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--toolchain', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--checked-ln', action='store_true',
                   help='Also build the experimental interval-certified ln entry')
    p.add_argument('--compensated-ln', action='store_true',
                   help='Use the Q82 compensated fast path for checked ln')
    p.add_argument('--near-ln', action='store_true',
                   help='Also use the relative near-one kernel (implies compensated ln)')
    args = p.parse_args()
    if args.near_ln:args.compensated_ln=True
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    cc = args.toolchain.resolve()/'arm-none-eabi-gcc'
    pinned = json.loads((root/'UPSTREAM.json').read_text())
    records = {}
    for label, directory in [('original', 'upstream'), ('modified', 'src')]:
        source = root/directory/'qfplib-m0-full_gcc.S'
        source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
        expected = pinned['upstream_sha256' if label == 'original' else 'modified_sha256']
        if source_sha != expected:
            raise ValueError(f'{label} source differs from UPSTREAM.json')
        elf = out/(label+'.elf')
        obj = out/(label+'.o')
        # Explicit object names avoid gcc's random temporary object filename
        # in the final ELF symbol table, making repeated builds deterministic.
        common = [str(cc), '-mcpu=cortex-m0plus', '-mthumb', '-mfloat-abi=soft']
        subprocess.run(common+['-c', str(source), '-o', str(obj)], check=True)
        subprocess.run(common+['-nostdlib', '-Wl,--build-id=none',
                               '-Wl,-Ttext=0x08000000', '-Wl,-e,qfp_dln',
                               '-Wl,-Map='+str(out/(label+'.map')),
                               str(obj), '-o', str(elf)], check=True)
        records[label] = dict(elf=str(elf),
                             elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),
                             source_sha256=source_sha)
    if args.checked_ln or args.compensated_ln:
        parts=[root/'src/qfplib-m0-full_gcc.S']
        parts += ([root/'src/ln_comp_constants.inc',root/'src/ln_comp96.inc'] if args.compensated_ln
                  else [root/'src/ln_fast96.inc'])
        combined=out/'checked.S'
        combined.write_bytes(b'\n'.join(path.read_bytes() for path in parts))
        asm=out/'checked_asm.o';checked=out/'checked.elf';cpp=out/'checked_ln.o'
        subprocess.run(common+['-c',str(combined),'-o',str(asm)],check=True)
        defines=['-DQFP_COMPENSATED_LN=1'] if args.compensated_ln else []
        if args.near_ln:defines.append('-DQFP_NEAR_LN=1')
        subprocess.run(common+defines+['-Os','-std=c99','-ffreestanding','-fno-builtin',
                               '-fno-unwind-tables','-fno-asynchronous-unwind-tables',
                               '-Wall','-Wextra','-Werror','-c',str(root/'src/ln_checked.c'),
                               '-o',str(cpp)],check=True)
        subprocess.run(common+['-nostdlib','-Wl,--build-id=none',
                               '-Wl,-Ttext=0x08000000','-Wl,-e,qfp_dln_checked',
                               '-Wl,-Map='+str(out/'checked.map'),str(asm),str(cpp),
                               '-o',str(checked)],check=True)
        records['checked']=dict(elf=str(checked),
            variant='compensated_Q82_relative_near66' if args.near_ln else 'compensated_Q82' if args.compensated_ln else 'legacy_Q62',
            elf_sha256=hashlib.sha256(checked.read_bytes()).hexdigest(),
            sources_sha256={str(path.relative_to(root)):hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in parts+[root/'src/ln_checked.c',root/'src/ln_constants.inc']})
    compiler = subprocess.run([str(cc), '--version'], check=True,
                              text=True, capture_output=True).stdout.splitlines()[0]
    (out/'build.json').write_text(json.dumps(dict(status='PASS', compiler=compiler,
                                                images=records,
                                                firmware_linked=False), indent=2)+'\n')
    print('PASS: independent original and modified Qfplib ARM images', flush=True)


if __name__ == '__main__':
    main()
