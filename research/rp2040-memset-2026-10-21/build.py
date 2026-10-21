#!/usr/bin/env python3
"""Build one reproducible SRAM benchmark APP with the normal portable SDK."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--arm-toolchain-bin',type=Path,required=True)
    p.add_argument('--directory',required=True)
    p.add_argument('--variant',choices=('initial','fast','standalone','shared'),default='standalone')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    assert re.fullmatch(r'/MK61S-MEMSET-[A-Za-z0-9-]+',a.directory)
    define={'initial':'','fast':'#define BENCH_FAST\n','standalone':'#define BENCH_SDK\n','shared':'#define BENCH_SDK\n'}[a.variant]
    wrapper=a.output/'wrapper.c'
    wrapper.write_text(define+'#define BENCH_ROOT '+json.dumps(a.directory)+'\n#include '+json.dumps(str(HERE/'benchmark.c'))+'\n')
    command=[sys.executable,str(ROOT/'tools/build_portable_app.py'),'--target','picocalc-pico-h',
        '--name','MEMBENCH','--source',str(wrapper),'--source',str(HERE/'candidates.S'),
        '--output-dir',str(a.output/'app'),'--arm-toolchain-bin',str(a.arm_toolchain_bin)]
    if a.variant=='shared':command.append('--shared-runtime')
    subprocess.run(command,check=True)
    app=a.output/'app/MEMBENCH.APP'
    config=dict(variant=a.variant,directory=a.directory,app=str(app.resolve()),
        app_sha256=hashlib.sha256(app.read_bytes()).hexdigest(),
        candidate={'initial':'own16','fast':'own_fast','standalone':'sdk','shared':'sdk'}[a.variant])
    (a.output/'benchmark.json').write_text(json.dumps(config,indent=2)+'\n')

if __name__=='__main__':main()
