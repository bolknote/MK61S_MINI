#!/usr/bin/env python3
"""Build deterministic bank files; --check detects stale committed output."""
import argparse
import json
import sys
from pathlib import Path
from game import create_game, check_layout
from assembler import BANK_SIZE

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from program_pack import program_binary
OUT=ROOT/'programs/games/ELITE'

def outputs():
    banks,info=create_game().link()
    check_layout(info)
    # A new layout may leave an entire bank free. Keep the complete image,
    # including zero-filled holes, rather than requiring every bank as a key.
    image=b''.join(banks.get(bank,bytes(BANK_SIZE)) for bank in range(32))
    files={OUT/'elite.bin':program_binary(image)}
    files[OUT/'autoexec.m61']=b'open? manual.md\nreinit\nload 0000 elite.bin\nrun\n'
    files[ROOT/'tools/elite/elite.map.json']=(json.dumps(info,indent=2,ensure_ascii=False)+'\n').encode('utf-8')
    return files

def main():
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');args=p.parse_args()
    files=outputs()
    stale=[]
    for path,data in files.items():
        if args.check:
            if not path.exists() or path.read_bytes()!=data:stale.append(str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    expected=set(files)
    for path in list(OUT.glob('b[0-9][0-9].m61'))+list(OUT.glob('part[0-9][0-9].m61')):
        if path not in expected:
            if args.check:stale.append(str(path.relative_to(ROOT)))
            else:path.unlink()
    if stale:raise SystemExit('Regenerate with tools/elite/build.py: '+', '.join(stale))
    print(f'ELITE: 32 banks in elite.bin; generated files {"verified" if args.check else "written"}')

if __name__=='__main__':main()
