#!/usr/bin/env python3
"""Freeze and build the APP-only memchr experiment; public runtime stays intact."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--arm-toolchain-bin',type=Path,required=True)
p.add_argument('--target',choices=('stm32','picocalc-pico-h'),required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--directory',required=True)
p.add_argument('--shared',action='store_true')
p.add_argument('--flash-header',type=Path)
p.add_argument('--flash-data-only',action='store_true',help='Keep code in SRAM and read the verified Flash payload data')
a=p.parse_args()
assert re.fullmatch(r'/MCHR[A-Za-z0-9-]*',a.directory)
assert not a.flash_data_only or a.flash_header
out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
spec=importlib.util.spec_from_file_location('kernels',HERE/'build-kernels.py')
kernels=importlib.util.module_from_spec(spec);spec.loader.exec_module(kernels)
layout=kernels.build(a.arm_toolchain_bin,out/'kernels','m0' if a.target=='picocalc-pico-h' else 'm4')
for filename in ('benchmark.c','baseline.c','candidates.S'):
    shutil.copyfile(HERE/filename,out/filename)
wrapper=out/'wrapper.c'
wrapper.write_text('#define BENCH_ROOT '+json.dumps(a.directory)+'\n'+
    ('#define BENCH_FLASH_DATA_ONLY 1\n' if a.flash_data_only else '')+
    ('#define BENCH_FLASH_HEADER '+json.dumps(str(a.flash_header.resolve()))+'\n' if a.flash_header else '')+
    '#include '+json.dumps(str(out/'benchmark.c'))+'\n')
command=[sys.executable,str(ROOT/'tools/build_portable_app.py'),'--target',a.target,'--name','CHRBEN',
    '--source',str(wrapper),'--source',str(out/'baseline.c'),'--source',str(out/'candidates.S'),
    '--library',str(out/'kernels/libc.o'),'--output-dir',str(out/'app'),
    '--arm-toolchain-bin',str(a.arm_toolchain_bin)]
if a.shared:command.append('--shared-runtime')
subprocess.run(command,check=True)
result=dict(target=a.target,shared=a.shared,directory=a.directory,public_memchr_runtime=False,
    placement='sram' if not a.flash_header or a.flash_data_only else 'flash',
    indirect_target='own64',kernels=layout,flash_header_sha256=hashlib.sha256(a.flash_header.read_bytes()).hexdigest() if a.flash_header else None,
    sources={n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in ('benchmark.c','baseline.c','candidates.S','wrapper.c')},
    app_sha256=hashlib.sha256((out/'app/CHRBEN.APP').read_bytes()).hexdigest())
(out/'benchmark.json').write_text(json.dumps(result,indent=2)+'\n')
