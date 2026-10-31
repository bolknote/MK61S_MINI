#!/usr/bin/env python3
"""Build paired-kernel/optional-runtime APPs from an isolated SDK prototype."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-tree',type=Path,required=True);p.add_argument('--target',choices=('stm32','picocalc-pico-h'),required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--directory',required=True)
    p.add_argument('--arm-toolchain-bin',type=Path,required=True);p.add_argument('--shared',action='store_true')
    p.add_argument('--flash-header',type=Path);p.add_argument('--flash-data-only',action='store_true')
    p.add_argument('--runtime-count',type=int,choices=(26,27),default=26)
    p.add_argument('--services-size',type=int,choices=(28,32))
    p.add_argument('--wide',action='store_true')
    a=p.parse_args();source=a.source_tree.resolve();out=a.output.resolve()
    assert ROOT/'.build' in source.parents and source.relative_to(ROOT/'.build').parts[0].startswith('memchr-')
    assert 'MK61_RUNTIME_OPTIONAL_ISO_C(memchr' in (source/'code/loadable_system_runtime.def').read_text()
    assert a.directory.startswith('/MCHR-') and '"' not in a.directory and a.directory.count('/')==1
    assert not a.flash_data_only or a.flash_header
    out.mkdir(parents=True,exist_ok=False);cpu='m4' if a.target=='stm32' else 'm0'
    names=['benchmark.c','baseline.c','candidates.S','pair-candidates.S','fast-candidates.S']+(['dsp-candidates.S'] if cpu=='m4' else [])
    if a.wide:names+=['balanced-candidates.S']+(['compact-candidates.S'] if cpu=='m4' else [])
    for name in names:shutil.copy2(HERE/name,out/name)
    services_size=a.services_size or (28 if a.runtime_count==26 else 32)
    (out/'wrapper.c').write_text('#define BENCH_RUNTIME_MATRIX 1\n#define BENCH_EXPECT_RUNTIME_COUNT '+str(a.runtime_count)+
        '\n#define BENCH_EXPECT_SERVICES_SIZE '+str(services_size)+'\n#define BENCH_ROOT '+json.dumps(a.directory)+'\n'+
        ('#define BENCH_WIDE_MATRIX 1\n' if a.wide else '')+
        ('#define BENCH_FLASH_DATA_ONLY 1\n' if a.flash_data_only else '')+
        ('#define BENCH_FLASH_HEADER '+json.dumps(str(a.flash_header.resolve()))+'\n' if a.flash_header else '')+
        '#include "benchmark.c"\n')
    reference=ROOT/('.build/memchr-20261022/'+cpu+'-v1')
    shutil.copy2(reference/'libc.o',out/'libc.o')
    command=[sys.executable,str(source/'tools/build_portable_app.py'),'--target',a.target,'--name','CHRBEN']
    for name in ['wrapper.c',*names[1:]]:command+=['--source',str(out/name)]
    command+=['--library',str(out/'libc.o'),'--output-dir',str(out/'app'),'--arm-toolchain-bin',str(a.arm_toolchain_bin)]
    if a.shared:command.append('--shared-runtime')
    result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    (out/'build.log').write_text(result.stdout)
    if result.returncode:print(result.stdout);raise RuntimeError('Isolated APP build failed')
    roles=['baseline','libc']+(['dsp16','pair64','fast64','dsp32'] if cpu=='m4' else ['pair16','fast16','pair64','fast64'])+['sdk','public-runtime-or-byte']
    symbols=['baseline','libc_search',*roles[2:6],'memchr','byte_search']
    if a.wide:
        roles=['baseline','libc','byte','own4','own16','own64','pair16','balanced16','pair64','balanced64']+\
            (['dsp16','dsp32','compact8'] if cpu=='m4' else ['fast16','fast64'])+['sdk','public-body-or-byte','public-veneer-or-byte']
        symbols=['baseline','libc_search',*roles[2:-3],'memchr',
            '@resident_memchr' if a.runtime_count==27 else 'byte_search','indirect_search' if a.runtime_count==27 else 'byte_search']
        symbols=[n if n!='byte' else 'byte_search' for n in symbols]
    manifest=dict(cpu=cpu,target=a.target,directory=a.directory,shared=a.shared,roles=roles,symbols=symbols,
        expected_runtime_count=a.runtime_count,expected_services_size=services_size,
        report_version=4 if a.wide else 3,rows_per_chunk=7 if a.wide else 12,fp_base=36 if a.wide else 16,
        public_runtime='Present only when the host advertises slot 26; otherwise column 7 is byte_search',
        placement='flash' if a.flash_header and not a.flash_data_only else 'sram',
        flash_header=str(a.flash_header.resolve()) if a.flash_header else None,
        flash_header_sha256=sha(a.flash_header) if a.flash_header else None,
        app_sha256=sha(out/'app/CHRBEN.APP'),elf_sha256=sha(out/'app/CHRBEN.elf'),
        command=command,sources={n:sha(out/n) for n in [*names,'wrapper.c','libc.o']},
        sdk_sources={n:sha(source/n) for n in ('code/loadable_app_services.h','code/loadable_system_runtime.def',
            'sdk/portable/memory.c','sdk/portable/shared_runtime.c','sdk/portable/system/runtime.S','code/memory_search_arm.h','code/memchr_arm.inc')})
    (out/'benchmark.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(dict(cpu=cpu,shared=a.shared,app_sha256=manifest['app_sha256'],sizes=json.loads((out/'app/CHRBEN.json').read_text())),indent=2))

if __name__=='__main__':main()
