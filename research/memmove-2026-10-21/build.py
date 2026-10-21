#!/usr/bin/env python3
"""Build an SRAM APP with the production SDK and frozen baseline."""
import argparse,hashlib,json,re,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--target',choices=('stm32','picocalc-pico-h'),required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--directory',required=True)
p.add_argument('--arm-toolchain-bin',type=Path,required=True)
p.add_argument('--shared',action='store_true')
p.add_argument('--selected-runtime',action='store_true')
p.add_argument('--flash-header',type=Path)
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
assert re.fullmatch(r'/MMOV[A-Za-z0-9-]*',a.directory)
wrapper=a.output/'wrapper.c'
assert not a.selected_runtime or a.shared,'--selected-runtime requires --shared'
wrapper.write_text(('#define BENCH_SELECTED_RUNTIME 1\n' if a.selected_runtime else '')+'#define BENCH_ROOT '+json.dumps(a.directory)+'\n'+
    ('#define BENCH_FLASH_HEADER '+json.dumps(str(a.flash_header.resolve()))+'\n' if a.flash_header else '')+
    '#include '+json.dumps(str(HERE/'benchmark.c'))+'\n')
cmd=[sys.executable,str(ROOT/'tools/build_portable_app.py'),'--target',a.target,'--name','MOVEBEN',
    '--source',str(wrapper),'--source',str(HERE/'candidates.S'),'--output-dir',str(a.output/'app'),
    '--arm-toolchain-bin',str(a.arm_toolchain_bin)]
if a.shared:cmd.append('--shared-runtime')
subprocess.run(cmd,check=True)
app=a.output/'app/MOVEBEN.APP'
(a.output/'benchmark.json').write_text(json.dumps(dict(target=a.target,shared=a.shared,selected_runtime=a.selected_runtime,directory=a.directory,
    app_sha256=hashlib.sha256(app.read_bytes()).hexdigest()),indent=2)+'\n')
