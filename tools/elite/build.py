#!/usr/bin/env python3
"""Build deterministic bank files; --check detects stale committed output."""
import argparse
import json
from pathlib import Path
from game import create_game

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'programs/games/ELITE'

def outputs():
    banks,info=create_game().link()
    files={OUT/f'b{b:02d}.m61':f'hin {b*112:04d} {bytes(code).hex().upper()}\n' for b,code in sorted(banks.items())}
    files[OUT/'autoexec.m61']='reinit\n'+''.join(f'open b{b:02d}.m61\n' for b in sorted(banks))+'run\n'
    files[ROOT/'tools/elite/elite.map.json']=json.dumps(info,indent=2,ensure_ascii=False)+'\n'
    return files

def main():
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');args=p.parse_args()
    files=outputs()
    stale=[]
    for path,text in files.items():
        if args.check:
            if not path.exists() or path.read_text()!=text:stale.append(str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
    expected=set(files)
    for path in OUT.glob('b[0-9][0-9].m61'):
        if path not in expected:
            if args.check:stale.append(str(path.relative_to(ROOT)))
            else:path.unlink()
    if stale:raise SystemExit('Regenerate with tools/elite/build.py: '+', '.join(stale))
    print(f'ELITE: {len([p for p in files if p.name.startswith("b")])} banks; generated files {"verified" if args.check else "written"}')

if __name__=='__main__':main()
