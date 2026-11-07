#!/usr/bin/env python3
"""Build identical finite Cosmic runs for local/M3 sound comparison."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from build_spectrum_app import ROOT,SOURCES
from build_spectrum_m3 import compiler_bin

RUNTIME_FILES=('AY.S3M','48.rom','128-0.rom','128-1.rom')
ROM_BYTES={'48.rom':16384,'128-0.rom':16384,'128-1.rom':16384}

def stage_runtime(runtime_dir,app_dir):
    """Make a game-probe APP directory directly runnable from the SD card."""
    runtime_dir=Path(runtime_dir);app_dir=Path(app_dir)
    result={}
    for name in RUNTIME_FILES:
        source=runtime_dir/name
        if not source.is_file():raise ValueError('Missing Spectrum runtime file: '+str(source))
        data=source.read_bytes()
        if name in ROM_BYTES and len(data)!=ROM_BYTES[name]:
            raise ValueError(name+' must be exactly 16384 bytes')
        if name=='AY.S3M' and (len(data)<64 or data[:4]!=b'S3M1'):
            raise ValueError('AY.S3M is not a valid S3M1 module')
        target=app_dir/name;shutil.copy2(source,target)
        if target.read_bytes()!=data:raise ValueError('Runtime copy differs: '+name)
        result[name]=hashlib.sha256(data).hexdigest()
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--build-dir',type=Path,required=True)
    ap.add_argument('--frames',type=int,default=600)
    ap.add_argument('--fixture-dir',required=True)
    ap.add_argument('--runtime-dir',type=Path,required=True,
                    help='Folder containing AY.S3M and the three Spectrum ROMs')
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
        runtime=stage_runtime(args.runtime_dir,folder/'app')
        meta=json.loads((folder/'app/S3GAME.json').read_text())
        inputs=[*sources,ROOT/'tests/spectrum_m3_game_probe.c',ROOT/SOURCES[0],
                *sorted((ROOT/'examples/portable-apps/SPECTRUM').glob('*.h'))]
        sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        meta.update(app=str(folder/'app/S3GAME.APP'),sha256=sha(folder/'app/S3GAME.APP'),frames=args.frames,
                    runtime_files=runtime,source_pins={str(p):sha(p)for p in inputs})
        (folder/'manifest.json').write_text(json.dumps(meta,indent=2)+'\n')
        print(('local' if local else 'M3')+': '+str(meta['memory_bytes'])+'/49152bytes')

if __name__=='__main__':main()
