#!/usr/bin/env python3
"""Build every user APP example for Pico H, without changing STM32 APPs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from build_picocalc import compiler_bin
ROOT=Path(__file__).resolve().parents[1]
APPS={
    'HELLO':(['examples/portable-apps/HELLO/main.c'],None),
    'HELLO_CPP':(['examples/loadable-apps/HELLO/hello_app.cpp'],None),
    'HELLO_RS':(['examples/portable-apps/HELLO-RUST/main.rs'],None),
    'SERVICES':(['examples/portable-apps/SERVICES/main.c'],None),
    'ELIZA':(['examples/portable-apps/ELIZA/main.c','examples/portable-apps/ELIZA/eliza_engine.c'],None),
    'SHEET':(['examples/portable-apps/SHEET/main.cpp','examples/portable-apps/SHEET/sheet_engine.cpp'],'S1'),
    'WBMP':(['examples/portable-apps/WBMP/main.c','examples/portable-apps/WBMP/viewer.cpp','code/wbmp.cpp'],'I1'),
}
ASSETS=('README.txt','ECHO8.ch8','PATTERN.wbmp','BUDGET.sheet','CYCLE.sheet')
README='''MK61S PicoCalc / Pico H: native APP collection, ABI 6 / Cortex-M0+.

HELLO.APP       C example; checks fresh data/BSS and prints HELLO C APP.
HELLO_CPP.APP   C++ manifest example; text, LED, sound; any key exits.
HELLO_RS.APP    no_std Rust example; prints HELLO, MK61S!; any key exits.
SERVICES.APP    Math/formatting example; sqrt(3^2+4^2)=5; any key exits.
ELIZA.APP       DOCTOR 1966 conversation program; Enter advances the intro.
SHEET.APP       Spreadsheet; open .sheet files or start an empty book.
WBMP.APP        Monochrome image handler; open a .wbmp file in Explorer.
ECHO8.ch8       CHIP-8 example; this is a ROM, not a native APP.
PATTERN.wbmp    WBMP pixel-check example.
BUDGET.sheet   Spreadsheet with formulas and Russian headings.
CYCLE.sheet    Spreadsheet with an intentional reference cycle.

Copy this directory to a new folder on microSD and open APPs in Explorer.
Do not replace STM32 /System or /app with this M0+ collection.
PicoCalc system services are resident in the UF2; no external System APPs
are needed. M4/hard-float and M0+/soft-float containers are distinct.
Sources and build information: manifest.json.
'''
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--toolchain',type=Path)
    parser.add_argument('--rustc',type=Path,help='Rust compiler; thumbv6m-none-eabi must be installed')
    parser.add_argument('--output-dir',type=Path,default=ROOT/'binary/picocalc-pico-h/apps')
    parser.add_argument('--build-dir',type=Path,default=ROOT/'.build/picocalc-apps')
    args=parser.parse_args();toolchain=compiler_bin(args.toolchain)
    args.output_dir.mkdir(parents=True,exist_ok=True)
    reports=[]
    for name,(sources,magic) in APPS.items():
        build=args.build_dir/name
        command=[sys.executable,str(ROOT/'tools/build_portable_app.py'),'--target','picocalc-pico-h','--name',name,
                 '--arm-toolchain-bin',str(toolchain),'--output-dir',str(build)]
        for source in sources: command+=['--source',str(ROOT/source)]
        if args.rustc and any(source.endswith('.rs') for source in sources):
            command+=['--rustc',str(args.rustc)]
        if magic: command+=['--handled-magic',magic]
        subprocess.run(command,check=True)
        report=json.loads((build/(name+'.json')).read_text())
        report['sources']=sources
        report['app_sha256']=hashlib.sha256((build/(name+'.APP')).read_bytes()).hexdigest()
        reports.append(report)
    # Publish only after every compiler succeeded, including Rust.
    for name in APPS:
        shutil.copy2(args.build_dir/name/(name+'.APP'),args.output_dir/(name+'.APP'))
    subprocess.run([sys.executable,str(ROOT/'examples/chip8/ECHO-8/assemble.py'),
        str(ROOT/'examples/chip8/ECHO-8/echo8.asm'),str(args.output_dir/'ECHO8.ch8')],check=True)
    # WBMP type 0: 192x64, horizontal bytes, MSB first.
    image=bytearray(b'\0\0\x81\x40\x40')
    for y in range(64):
        for x in range(0,192,8):
            image.append(sum((0x80>>bit) for bit in range(8) if ((x+bit)*3+y*5)%11>=5))
    (args.output_dir/'PATTERN.wbmp').write_bytes(image)
    for name in ('BUDGET','CYCLE'):
        shutil.copy2(ROOT/'programs/sheets'/(name+'.mks'),args.output_dir/(name+'.sheet'))
    (args.output_dir/'README.txt').write_text(README)
    (args.output_dir/'manifest.json').write_text(json.dumps(reports,indent=2)+'\n')
    print('Pico H APPs: '+str(args.output_dir))
if __name__=='__main__': main()
