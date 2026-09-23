#!/usr/bin/env python3
"""Build deterministic bank files; --check detects stale committed output."""
import argparse
import json
import sys
from pathlib import Path
from game import create_game, check_layout

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from program_pack import program_lines
OUT=ROOT/'programs/games/ELITE'

def pack_parts(lines):
    parts=[]
    current=''
    for line in lines:
        if len(current)+len(line)>1536:
            parts.append(current)
            current=''
        current+=line
    if current:parts.append(current)
    return parts

def outputs():
    banks,info=create_game().link()
    check_layout(info)
    image=b''.join(banks[bank] for bank in range(max(banks)+1))
    parts={OUT/f'part{i:02d}.m61':text for i,text in enumerate(pack_parts(program_lines(image)))}
    files=dict(parts)
    files[OUT/'autoexec.m61']='open? manual.md\nreinit\n'+''.join(f'open {p.name}\n' for p in parts)+'run\n'
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
    for path in list(OUT.glob('b[0-9][0-9].m61'))+list(OUT.glob('part[0-9][0-9].m61')):
        if path not in expected:
            if args.check:stale.append(str(path.relative_to(ROOT)))
            else:path.unlink()
    if stale:raise SystemExit('Regenerate with tools/elite/build.py: '+', '.join(stale))
    part_count=sum(path.name.startswith('part') for path in files)
    print(f'ELITE: 32 banks in {part_count} parts; generated files {"verified" if args.check else "written"}')

if __name__=='__main__':main()
