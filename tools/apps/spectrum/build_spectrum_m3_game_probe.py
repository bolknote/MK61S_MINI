#!/usr/bin/env python3
"""Build identical finite Cosmic runs for local/M3 sound comparison."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from build_spectrum_app import ROOT,SOURCES
from build_spectrum_m3 import compiler_bin

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--build-dir',type=Path,required=True)
    ap.add_argument('--frames',type=int,default=600)
    ap.add_argument('--fixture-dir',required=True)
    args=ap.parse_args()
    if not 60<=args.frames<=3100:ap.error('frames must be60..3100')
    for local in (False,True):
        folder=args.build_dir.resolve()/('local' if local else 'remote');folder.mkdir(parents=True,exist_ok=True)
        wrapper=folder/'game.c';wrapper.write_text('#define S3_FORCE_LOCAL '+str(int(local))+
            '\n#define S3_GAME_FOLDER '+json.dumps(args.fixture_dir)+'\n#define S3_GAME_FRAMES '+str(args.frames)+'u\n#include "'+str(ROOT/'tests/spectrum_m3_game_probe.c')+'"\n')
        sources=[wrapper,*[ROOT/s for s in SOURCES[1:]]]
        command=[sys.executable,str(ROOT/'tools/apps/portable/build_portable_app.py'),'--target','picocalc-pico-h',
            '--name','S3GAME','--shared-runtime','--arm-toolchain-bin',str(compiler_bin(None)),'--output-dir',str(folder/'app')]
        for source in sources:command+=['--source',str(source)]
        with (folder/'build.log').open('w') as log:subprocess.run(command,check=True,stdout=log,stderr=subprocess.STDOUT)
        meta=json.loads((folder/'app/S3GAME.json').read_text())
        inputs=[*sources,ROOT/'tests/spectrum_m3_game_probe.c',ROOT/SOURCES[0],
                *sorted((ROOT/'examples/portable-apps/SPECTRUM').glob('*.h'))]
        sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        meta.update(app=str(folder/'app/S3GAME.APP'),sha256=sha(folder/'app/S3GAME.APP'),frames=args.frames,
                    source_pins={str(p):sha(p)for p in inputs})
        (folder/'manifest.json').write_text(json.dumps(meta,indent=2)+'\n')
        print(('local' if local else 'M3')+': '+str(meta['memory_bytes'])+'/49152bytes')

if __name__=='__main__':main()
