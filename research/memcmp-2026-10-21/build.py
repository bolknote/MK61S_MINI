#!/usr/bin/env python3
"""Build an SRAM APP with the production SDK and frozen baseline."""
import argparse,hashlib,json,re,shutil,subprocess,sys
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
p.add_argument('--selected-body',choices=('own4','own16','own64'),default='own64')
p.add_argument('--placement',action='store_true',help='M0: compare identical SRAM and Flash bodies in the same round')
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
assert re.fullmatch(r'/MCMP[A-Za-z0-9-]*',a.directory)
for name in ('benchmark.c','candidates.S','baseline-memory.h'):
    shutil.copyfile(HERE/name,a.output/name)
wrapper=a.output/'wrapper.c'
assert not a.selected_runtime or a.shared,'--selected-runtime requires --shared'
assert not a.placement or (a.target=='picocalc-pico-h' and a.flash_header)
wrapper.write_text(('#define BENCH_SELECTED_RUNTIME 1\n#define BENCH_SELECTED_BODY '+a.selected_body+'\n' if a.selected_runtime else '')+'#define BENCH_ROOT '+json.dumps(a.directory)+'\n'+
    ('#define BENCH_M0_PLACEMENT 1\n' if a.placement else '')+
    ('#define BENCH_FLASH_HEADER '+json.dumps(str(a.flash_header.resolve()))+'\n' if a.flash_header else '')+
    '#include '+json.dumps(str((a.output/'benchmark.c').resolve()))+'\n')
cmd=[sys.executable,str(ROOT/'tools/build_portable_app.py'),'--target',a.target,'--name','CMPBEN',
    '--source',str(wrapper),'--source',str(a.output/'candidates.S'),'--output-dir',str(a.output/'app'),
    '--arm-toolchain-bin',str(a.arm_toolchain_bin)]
if a.shared:cmd.append('--shared-runtime')
subprocess.run(cmd,check=True)
app=a.output/'app/CMPBEN.APP'
(a.output/'benchmark.json').write_text(json.dumps(dict(target=a.target,shared=a.shared,selected_runtime=a.selected_runtime,selected_body=a.selected_body,placement=a.placement,directory=a.directory,
    flash_header_sha256=hashlib.sha256(a.flash_header.read_bytes()).hexdigest() if a.flash_header else None,
    app_sha256=hashlib.sha256(app.read_bytes()).hexdigest(),
    sources={name:hashlib.sha256((a.output/name).read_bytes()).hexdigest()
             for name in ('benchmark.c','candidates.S','baseline-memory.h')}),indent=2)+'\n')
