#!/usr/bin/env python3
"""Build ordinary ABI 6 APP examples for Pico H, without changing STM32 APPs."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from build_picocalc import compiler_bin
ROOT=Path(__file__).resolve().parents[1]
APPS={
    'HELLO':(['HELLO/main.c'],None),
    'SERVICES':(['SERVICES/main.c'],None),
    'ELIZA':(['ELIZA/main.c','ELIZA/eliza_engine.c'],None),
    'SHEET':(['SHEET/main.cpp','SHEET/sheet_engine.cpp'],'S1'),
    'WBMP':(['WBMP/main.c','WBMP/viewer.cpp'],'I1'),
}
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--toolchain',type=Path)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'binary/picocalc-pico-h/apps')
    parser.add_argument('--build-dir',type=Path,default=ROOT/'.build/picocalc-apps')
    args=parser.parse_args();toolchain=compiler_bin(args.toolchain)
    args.output_dir.mkdir(parents=True,exist_ok=True)
    reports=[]
    for name,(sources,magic) in APPS.items():
        build=args.build_dir/name
        command=[sys.executable,str(ROOT/'tools/build_portable_app.py'),'--target','picocalc-pico-h','--name',name,
                 '--arm-toolchain-bin',str(toolchain),'--output-dir',str(build)]
        for source in sources: command+=['--source',str(ROOT/'examples/portable-apps'/source)]
        if name=='WBMP': command+=['--source',str(ROOT/'code/wbmp.cpp')]
        if magic: command+=['--handled-magic',magic]
        subprocess.run(command,check=True)
        shutil.copy2(build/(name+'.APP'),args.output_dir/(name+'.APP'))
        reports.append(json.loads((build/(name+'.json')).read_text()))
    (args.output_dir/'manifest.json').write_text(json.dumps(reports,indent=2)+'\n')
    print('Pico H APPs: '+str(args.output_dir))
if __name__=='__main__': main()
