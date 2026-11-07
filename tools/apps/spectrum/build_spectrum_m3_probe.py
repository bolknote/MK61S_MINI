#!/usr/bin/env python3
"""Build a finite native Pico probe for actual M3 audio DSP and transport."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from build_spectrum_m3 import ROOT,RUNTIME,compiler_bin,build


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--build-dir',type=Path,required=True)
    ap.add_argument('--optimization',choices=['Os','O2','O3'],default='O2')
    ap.add_argument('--fast-init',type=int,choices=[0,64,80,96],default=96)
    ap.add_argument('--frames',type=int,choices=[64,80,96,120],default=96)
    ap.add_argument('--pwm8',action='store_true')
    ap.add_argument('--direct-read',action='store_true')
    ap.add_argument('--legacy-poll',action='store_true',help='Explicit old-resident comparison only; normal tests use pushed completion')
    args=ap.parse_args()
    folder=args.build_dir.resolve()/'probe';folder.mkdir(parents=True,exist_ok=True)
    module=build(folder.parent/'module',optimization='-'+args.optimization,fast_init=args.fast_init)
    defines=['M3_SOUND_FRAMES='+str(args.frames),'S3_SOUND_PWM8='+str(int(args.pwm8)),
             'S3_SOUND_DIRECT_READ='+str(int(args.direct_read)),'S3_SOUND_PUSH='+str(int(not args.legacy_poll))]
    if args.fast_init:defines+=['EMU2149_M3_AUDIO=1','SPECTRUM_M3_FAST_INIT='+str(args.fast_init)]
    app=ROOT/'examples/portable-apps/SPECTRUM'
    generator=folder/'vectors'
    cmd=['clang','-std=c11','-O2','-Wall','-Wextra','-Werror',*['-D'+d for d in defines],'-I'+str(RUNTIME),
         str(ROOT/'tests/spectrum_m3_probe_vectors.c'),str(app/'m3_audio_module.c'),
         str(ROOT/'third_party/emu2149/emu2149.c'),'-o',str(generator)]
    subprocess.run(cmd,check=True)
    with (folder/'sound_vectors.h').open('w') as out:subprocess.run([str(generator)],stdout=out,check=True)
    package=Path(module['package'])
    (folder/'module_package.h').write_text('static const unsigned char stm3_package[]={'+','.join(map(str,package.read_bytes()))+'};\n')
    wrapper=folder/'probe_app.c'
    wrapper.write_text(''.join('#define '+d.replace('=',' ',1)+'\n' for d in defines)+
                       '#include "'+str(ROOT/'tests/spectrum_m3_probe_app.c')+'"\n')
    sources=[wrapper,RUNTIME/'stm3_client.c',RUNTIME/'pico_uart1.c']
    command=[sys.executable,str(ROOT/'tools/apps/portable/build_portable_app.py'),'--target','picocalc-pico-h',
             '--name','S3SOUND','--arm-toolchain-bin',str(compiler_bin(None)),'--include',str(RUNTIME),
             '--include',str(folder),'--output-dir',str(folder/'app')]
    for source in sources:command+=['--source',str(source)]
    with (folder/'build.log').open('w') as log:subprocess.run(command,check=True,stdout=log,stderr=subprocess.STDOUT)
    binary=folder/'app/S3SOUND.APP';meta=json.loads((folder/'app/S3SOUND.json').read_text())
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    inputs=[*sources,ROOT/'tests/spectrum_m3_probe_app.c',ROOT/'tests/spectrum_m3_probe_input.h',ROOT/'tests/spectrum_m3_probe_vectors.c',
            RUNTIME/'stm3_client.h',RUNTIME/'pico_uart1.h',folder/'sound_vectors.h',folder/'module_package.h']
    result=dict(status='COMPILED',app=str(binary),sha256=sha(binary),memory_bytes=meta['memory_bytes'],
                module=module,frames=args.frames,pwm8=args.pwm8,pushed_completion=not args.legacy_poll,source_pins={str(p):sha(p)for p in inputs},firmware_changed=False,
                physical_io=0,hardware_verified=False,scope='UART1 only; no PWM, Flash, RTC, settings or calculator writes')
    (folder/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({key:value for key,value in result.items() if key not in ('module','source_pins')},indent=2))


if __name__=='__main__':main()
