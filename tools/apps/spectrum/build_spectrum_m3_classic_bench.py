#!/usr/bin/env python3
"""Build a finite Classic APP around an unchanged Cortex-M3 module binary."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
from build_spectrum_m3 import ROOT,RUNTIME,compiler_bin

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--module-dir',type=Path,required=True)
    ap.add_argument('--build-dir',type=Path,required=True)
    ap.add_argument('--name',default='S3BENCH')
    args=ap.parse_args();module=args.module_dir.resolve();out=args.build_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    package=(module/'AY.S3M').read_bytes();meta=json.loads((module/'manifest.json').read_text())
    image_bytes,bss,entry,relocs=struct.unpack_from('<4I',package,16)
    assert meta['sha256']==hashlib.sha256(package).hexdigest() and image_bytes+bss<=6144 and entry&1
    image=package[64:64+image_bytes];offsets=struct.unpack_from('<'+'I'*relocs,package,64+image_bytes)
    for at in offsets:assert at%4==0 and at+4<=image_bytes and 0x20000000<=struct.unpack_from('<I',image,at)[0]<=0x20000000+image_bytes+bss
    (out/'module_image.h').write_text(
        f'#define SOUND_MODULE_SHA256 "{meta["sha256"]}"\n#define SOUND_ENTRY_OFFSET {entry}u\n'+
        f'#define SOUND_IMAGE_BYTES {image_bytes}u\n#define SOUND_MEMORY_BYTES {image_bytes+bss}u\n#define SOUND_RELOCATIONS {relocs}u\n'+
        f'static unsigned char sound_module_image[{image_bytes+bss}] __attribute__((aligned(4)))={{'+','.join(map(str,image))+'};\n'+
        'static const unsigned short sound_module_relocations[]={'+','.join(map(str,offsets))+'};\n')
    defines=['M3_SOUND_FRAMES=96','S3_SOUND_PWM8=1','EMU2149_M3_AUDIO=1','SPECTRUM_M3_FAST_INIT=96']
    generator=out/'vectors'
    subprocess.run(['clang','-std=c11','-O2',*['-D'+s for s in defines],'-I'+str(RUNTIME),
                    str(ROOT/'tests/spectrum_m3_probe_vectors.c'),str(ROOT/'examples/portable-apps/SPECTRUM/m3_audio_module.c'),
                    str(ROOT/'third_party/emu2149/emu2149.c'),'-o',str(generator)],check=True)
    with (out/'sound_vectors.h').open('w') as f:subprocess.run([str(generator)],check=True,stdout=f)
    result_name=args.name[:6]+'R'
    wrapper=out/'bench.c';wrapper.write_text('#define SOUND_RESULT_NAME "'+result_name+'"\n'+''.join('#define '+s.replace('=',' ',1)+'\n'for s in defines)+
        '#include "'+str(ROOT/'tests/spectrum_m3_classic_bench.c')+'"\n')
    cmd=[sys.executable,str(ROOT/'tools/apps/portable/build_portable_app.py'),'--target','stm32','--name',args.name,
         '--arm-toolchain-bin',str(compiler_bin(None)),'--include',str(RUNTIME),'--include',str(ROOT/'tests'),
         '--include',str(out),'--source',str(wrapper),'--output-dir',str(out/'app')]
    with (out/'build.log').open('w') as f:subprocess.run(cmd,check=True,stdout=f,stderr=subprocess.STDOUT)
    app=out/'app'/f'{args.name}.APP';report=json.loads((out/'app'/f'{args.name}.json').read_text())
    result=dict(status='COMPILED',app=str(app),app_sha256=hashlib.sha256(app.read_bytes()).hexdigest(),
        memory_bytes=report['memory_bytes'],module_sha256=meta['sha256'],kernel_cpu='cortex-m3',kernel_float_abi='soft',
        wrapper_cpu='cortex-m4',hardware_verified=False,physical_io=False,clock_changes=False,result_path='/'+result_name+'.txt',
        measurements='DWT cycles on M4 are comparative kernel measurements, not M3 real-time timing',
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in
            [ROOT/'tests/spectrum_m3_classic_bench.c',ROOT/'tests/spectrum_m3_probe_input.h',ROOT/'tests/spectrum_m3_probe_vectors.c',Path(__file__)]})
    (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
