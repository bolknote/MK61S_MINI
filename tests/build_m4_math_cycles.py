#!/usr/bin/env python3
"""Build per-operation SRAM DWT diagnostics from a frozen math source root."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
NAMES=('sin','cos','tan','asin','acos','atan','ln','log10','exp','sqrt','pow')

def bits(x):
    return struct.unpack('<Q',struct.pack('<d',x))[0]

def cases(op):
    if op in ('sin','cos','tan'):
        values=[0.,-0.,.00390625,-.125,.75,1.,-3.,100.,100000.,2.**40,1e300,
                math.nextafter(math.pi/2,0.),math.pi/2,math.nextafter(math.pi/2,math.inf)]
    elif op in ('ln','log10'):
        values=[.5,.6875038842146042,math.nextafter(1.,0.),1.,math.nextafter(1.,2.),
                1.001,1.1,2.,10.,2.**-1000,1e300,2.**-1074]
    elif op=='atan':
        values=[0.,-0.,.00390625,-.125,.75,1.,-3.,100.,2.**40,1e300]
    elif op=='exp':
        values=[0.,-0.,1e-10,-.125,.75,1.,1.624944042189414,-3.,100.,-700.,700.,-744.]
    elif op in ('asin','acos'):
        values=[-.99,-.5,0.,.125,.5,.99]
    elif op=='sqrt':
        values=[0.,2.**-1074,.5,1.,2.,10.,1e300]
    else:
        return [(bits(x),bits(y)) for x,y in ((.5,-3.),(1.001,20.),(2.,.5),(10.,1.125))]
    return [(bits(x),0) for x in values]

def build(source_root,out,operations):
    sys.path.insert(0,str(ROOT/'tools'))
    from build_picocalc import compiler_bin
    tc=compiler_bin(None);out.mkdir(parents=True,exist_ok=True);commands=[]
    def run(cmd):
        cmd=list(map(str,cmd));commands.append(cmd);subprocess.run(cmd,check=True)
    flags=['-mcpu=cortex-m4','-mthumb','-mfpu=fpv4-sp-d16','-mfloat-abi=hard','-Os',
        '-mword-relocations','-ffunction-sections','-fdata-sections','-fno-builtin',
        '-fno-lto','-Wall','-Wextra','-Werror','-DMK61_NATIVE_RUNTIME=1','-DMK61_USE_NATIVE_EABI=1']
    run([tc/'arm-none-eabi-g++',*flags,'-std=c++17','-fno-rtti','-fno-exceptions',
         '-c',source_root/'code/native_eabi.cpp','-o',out/'native-eabi.o'])
    assembly=out/'runtime.S'
    assembly.write_text('#define MK61_NATIVE_RUNTIME 1\n#define MK61_USE_NATIVE_EABI 1\n'+
        ''.join('#include '+json.dumps(str(source_root/'code'/name))+'\n'
                for name in ('native_eabi_arm.S','native_eabi_fixed.S')))
    run([tc/'arm-none-eabi-gcc',*flags,'-c',assembly,'-o',out/'native-eabi-arm.o'])
    archive=out/'libnative-eabi.a'
    run([tc/'arm-none-eabi-ar','rcs',archive,out/'native-eabi.o',out/'native-eabi-arm.o'])
    reports={}
    for op in operations:
        target=out/op;target.mkdir(exist_ok=True);source=target/'probe.cpp'
        inputs=','.join('{UINT64_C(0x%016X),UINT64_C(0x%016X)}'%pair for pair in cases(op))
        source.write_text('#define MK61_MATH_BACKEND 0\n#define MK61_USE_COMPACT_LIBM 1\n'+
            '#define MK61_USE_M0_EABI 0\n#define MK61_USE_NATIVE_EABI 1\n'+
            '#define M4_BENCH_OPERATION '+str(NAMES.index(op))+'\n#define M4_BENCH_CASES '+inputs+'\n'+
            '#include '+json.dumps(str(source_root/'code/compact_math.cpp'))+'\n'+
            '#include '+json.dumps(str(ROOT/'tests/fixtures/m4_math_cycles.cpp'))+'\n')
        run([sys.executable,ROOT/'tools/build_portable_app.py','--name','M4MATH',
             '--source',source,'--library',archive,'--output-dir',target,'--arm-toolchain-bin',tc])
        # A -lgcc argument in the generic APP builder must not extract code.
        link_map=(target/'M4MATH.map').read_text()
        assert not any('libgcc.a(' in line for line in link_map.splitlines()),op
        app=target/'M4MATH.APP'
        reports[op]={'app_sha256':hashlib.sha256(app.read_bytes()).hexdigest(),
                     'inputs':[[f'{x:016X}',f'{y:016X}'] for x,y in cases(op)]}
    dependencies=['compact_math.cpp','compact_math.hpp','compact_math_tables.hpp','mk_math.hpp',
        'native_eabi.cpp','native_eabi.hpp','native_eabi_arm.S','native_eabi_fixed.S',
        'native_eabi_m0_log_table.inc','compact_math_m4.inc','compact_math_m4_tables.inc']
    report={'source_root':str(source_root),'commands':commands,'operations':reports,
        'source_sha256':{'code/'+name:hashlib.sha256((source_root/'code'/name).read_bytes()).hexdigest()
            for name in dependencies if (source_root/'code'/name).exists()},
        'probe_sha256':hashlib.sha256((ROOT/'tests/fixtures/m4_math_cycles.cpp').read_bytes()).hexdigest()}
    (out/'build.json').write_text(json.dumps(report,indent=2)+'\n')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--operations',nargs='+',choices=NAMES,default=['sin','cos','tan','atan','ln','log10','exp'])
    a=p.parse_args();build(a.source_root.resolve(),a.output_dir.resolve(),a.operations)

if __name__=='__main__':main()
