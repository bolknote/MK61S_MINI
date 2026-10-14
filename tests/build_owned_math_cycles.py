#!/usr/bin/env python3
"""Build a standalone SRAM benchmark with the resident's no-LTO EABI policy."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--arm-toolchain-bin',type=Path,required=True)
p.add_argument('--output-dir',type=Path,required=True)
a=p.parse_args();out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
flags=['-mcpu=cortex-m4','-mthumb','-mfpu=fpv4-sp-d16','-mfloat-abi=hard','-Os',
       '-mword-relocations','-ffunction-sections','-fdata-sections','-fno-builtin',
       '-fno-lto','-Wall','-Wextra','-Werror','-DMK61_NATIVE_RUNTIME=1','-DMK61_USE_NATIVE_EABI=1']
commands=[]
def run(cmd):
    commands.append([str(x) for x in cmd]);subprocess.run(cmd,check=True)
run([a.arm_toolchain_bin/'arm-none-eabi-g++',*flags,'-std=c++17','-fno-rtti','-fno-exceptions',
     '-c',ROOT/'code/native_eabi.cpp','-o',out/'native-eabi.o'])
run([a.arm_toolchain_bin/'arm-none-eabi-gcc',*flags,'-c',ROOT/'tests/fixtures/math_cycles_owned_runtime.S',
     '-o',out/'native-eabi-arm.o'])
archive=out/'libnative-eabi.a'
run([a.arm_toolchain_bin/'arm-none-eabi-ar','rcs',archive,out/'native-eabi.o',out/'native-eabi-arm.o'])
run([sys.executable,ROOT/'tools/build_portable_app.py','--name','SEGGD',
     '--source',ROOT/'tests/fixtures/math_cycles_double.cpp','--library',archive,
     '--output-dir',out,'--arm-toolchain-bin',a.arm_toolchain_bin])
(out/'native-eabi-build.json').write_text(json.dumps({'commands':commands,'source_sha256':{
    name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in (
        'code/compact_math.cpp','code/native_eabi.cpp','code/native_eabi_arm.S','code/native_eabi_fixed.S')}},indent=2)+'\n')
