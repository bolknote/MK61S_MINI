#!/usr/bin/env python3
"""Build separate SRAM ALU probes; Qfplib is an optional external reference."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from build_picocalc import compiler_bin

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--qfplib-source',type=Path)
    parser.add_argument('--baseline-library',type=Path,help='Also time a previously built owned runtime archive')
    parser.add_argument('--addition-streams',action='store_true',help='Time six streams of varied addition operands')
    parser.add_argument('--directory',default='MK61S-M0-ALU-20261018')
    parser.add_argument('--toolchain',type=Path)
    parser.add_argument('--math-probe',action='store_true',help='Also build all eleven local binary64 functions for hardware qualification')
    args=parser.parse_args()
    if '/' in args.directory or not args.directory.startswith('MK61S-M0-ALU-'):
        parser.error('Use a new MK61S-M0-ALU-* directory basename')
    tc=compiler_bin(args.toolchain);out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    flags=['-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-Os','-mword-relocations',
        '-fno-lto','-fno-builtin','-ffunction-sections','-fdata-sections','-DMK61_USE_M0_EABI=1','-DMK61_M0_RP2040_EABI=1',
        '-DMK61_USE_COMPACT_LIBM=1','-DMK61_MATH_BACKEND=0','-I'+str(ROOT/'code')]
    objects=[]
    sources=['code/native_eabi_m0.cpp','code/native_eabi_m0.S','code/native_eabi_m0_rp2040.S']
    if args.math_probe:sources.append('code/compact_math.cpp')
    for src in sources:
        source=ROOT/src;obj=out/(source.name+'.o');objects.append(obj)
        subprocess.run([str(tc/('arm-none-eabi-g++' if source.suffix=='.cpp' else 'arm-none-eabi-gcc')),*flags,
            *(['-std=c++17','-fno-exceptions','-fno-rtti'] if source.suffix=='.cpp' else []),'-c',str(source),'-o',str(obj)],check=True)
    subprocess.run([str(tc/'arm-none-eabi-ar'),'rcs',str(out/'owned.a'),*[str(p) for p in objects]],check=True)
    variants=[('OWN',''),('GCC','#define M0_BENCH_RESIDENT 1\n')]
    if args.baseline_library:variants.insert(1,('BASE',''))
    if args.qfplib_source:
        subprocess.run([str(tc/'arm-none-eabi-gcc'),*flags,'-c',str(args.qfplib_source),'-o',str(out/'qfplib.o')],check=True)
        subprocess.run([str(tc/'arm-none-eabi-ar'),'rcs',str(out/'qfplib.a'),str(out/'qfplib.o')],check=True)
        variants.append(('QFP','#define M0_BENCH_QFPLIB 1\n'))
    results={}
    for name,define in variants:
        wrapper=out/(name+'.c')
        fixture=ROOT/'tests/fixtures'/('m0_eabi_add_benchmark.c' if args.addition_streams else 'm0_eabi_benchmark.c')
        wrapper.write_text(define+f'#define M0_BENCH_OUTPUT "{name}"\n#define M0_BENCH_MARKER "/{args.directory}/marker.bin"\n#include "{fixture}"\n')
        cmd=[sys.executable,str(ROOT/'tools/build_portable_app.py'),'--target','picocalc-pico-h','--name',name,
            '--source',str(wrapper),'--arm-toolchain-bin',str(tc),'--output-dir',str(out/name)]
        if name!='GCC':
            library=args.baseline_library.resolve() if name=='BASE' else out/('owned.a' if name=='OWN' else 'qfplib.a')
            cmd+=['--library',str(library)]
        with (out/(name+'.log')).open('w') as log:subprocess.run(cmd,check=True,stdout=log,stderr=subprocess.STDOUT)
        app=out/name/(name+'.APP');results[name]={'file':str(app),'bytes':app.stat().st_size,'sha256':hashlib.sha256(app.read_bytes()).hexdigest()}
        print(name,results[name],flush=True)
    metadata={'directory':'/'+args.directory,'apps':results,'code_location':'All local implementations execute in SRAM; GCC control uses resident Flash.',
        'corpus':'addition-streams' if args.addition_streams else 'four-operations',
        'baseline_library_sha256':hashlib.sha256(args.baseline_library.read_bytes()).hexdigest() if args.baseline_library else None,
        'qfplib_source_sha256':hashlib.sha256(args.qfplib_source.read_bytes()).hexdigest() if args.qfplib_source else None}
    if args.math_probe:
        fixture=(ROOT/'tests/fixtures/compact_math_probe_app.c').read_text()
        assert fixture.count('s->math(')==2
        wrapper=out/'MATHLOCAL.c'
        wrapper.write_text(f'#define MK61_MATH_VECTOR_ROOT "/{args.directory}"\nextern double m0_probe_math(unsigned,double,double);\n'+fixture.replace('s->math(','m0_probe_math('))
        dispatch=out/'math-local.cpp'
        names=('sin','cos','tan','asin','acos','atan','ln','log10','exp','sqrt','pow')
        dispatch.write_text('#include "compact_math.hpp"\nextern "C" double m0_probe_math(unsigned op,double a,double b) {switch(op) {\n'+''.join(
            f'case {i}:return compact_math::{name}(a'+(',b' if name=='pow' else '')+');\n' for i,name in enumerate(names))+'default:return 0;}}\n')
        cmd=[sys.executable,str(ROOT/'tools/build_portable_app.py'),'--target','picocalc-pico-h','--name','MATHLOCAL',
            '--source',str(wrapper),'--source',str(dispatch),'--include',str(ROOT/'code'),
            '--arm-toolchain-bin',str(tc),'--output-dir',str(out/'MATHLOCAL'),'--library',str(out/'owned.a')]
        with (out/'MATHLOCAL.log').open('w') as log:subprocess.run(cmd,check=True,stdout=log,stderr=subprocess.STDOUT)
        app=out/'MATHLOCAL/MATHLOCAL.APP';metadata['math_probe']={'file':str(app),'sha256':hashlib.sha256(app.read_bytes()).hexdigest()}
        print('MATHLOCAL',app.stat().st_size,'bytes',flush=True)
    (out/'benchmark.json').write_text(json.dumps(metadata,indent=2)+'\n')
if __name__=='__main__':main()
