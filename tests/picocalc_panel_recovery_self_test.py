#!/usr/bin/env python3
"""Run actual production Panel flush/transfer against a host-only LCD boundary."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]

def run(args, build):
    source=args.source.resolve().read_text()
    first='bool Panel::flush(const Screen& screen) {'
    after='void Panel::configure_dma() {'
    transfer='void Panel::transfer() {'
    end='\n} // namespace picocalc'
    for marker in (first,after,transfer,end):
        if source.count(marker)!=1:
            raise RuntimeError('production extraction boundary changed: '+marker)
    flush=source[source.index(first):source.index(after)]
    body=source[source.index(transfer):source.index(end)]
    extracted=build/'picocalc_panel_production.inc'
    extracted.write_text(flush+'\n'+body)
    command=[os.environ.get('CXX','clang++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror',
             '-I'+str(build),'-I'+str(args.source_root.resolve()/'ports/picocalc'),
             '-I'+str(args.source_root.resolve()/'code')]
    if os.environ.get('MK61_TEST_SANITIZERS')=='1':
        command+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    command+=[str(ROOT/'tests/picocalc_panel_recovery_self_test.cpp'),'-o',str(build/'panel-test')]
    compile_result=subprocess.run(command,capture_output=True,text=True)
    (build/'compile.stdout.log').write_text(compile_result.stdout)
    (build/'compile.stderr.log').write_text(compile_result.stderr)
    if compile_result.returncode:
        print(compile_result.stderr,end='')
        return compile_result.returncode
    start=time.monotonic()
    result=subprocess.run([str(build/'panel-test')],capture_output=True,text=True)
    (build/'stdout.log').write_text(result.stdout)
    (build/'stderr.log').write_text(result.stderr)
    def pin(path):
        data=path.read_bytes()
        return dict(path=str(path),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
    report=dict(status='PASS' if result.returncode==0 else 'FAIL',exit_code=result.returncode,
                elapsed_seconds=time.monotonic()-start,source=pin(args.source.resolve()),
                hardware_header=pin(args.source_root.resolve()/'ports/picocalc/hardware.hpp'),
                extracted_methods=pin(extracted),compile_argv=command,
                limitations='SDK, scanline completion and LCD endpoint are host fixtures; DMA chain/timing/electrical behavior is not measured.')
    (build/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(result.stdout,end='');print(result.stderr,end='')
    return result.returncode

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=ROOT/'ports/picocalc/hardware.cpp')
    parser.add_argument('--source-root',type=Path,default=ROOT)
    parser.add_argument('--build-dir',type=Path)
    args=parser.parse_args()
    if args.build_dir:
        args.build_dir.mkdir(parents=True,exist_ok=False)
        return run(args,args.build_dir.resolve())
    with tempfile.TemporaryDirectory(prefix='picocalc-panel-recovery-') as directory:
        return run(args,Path(directory))

if __name__=='__main__':
    raise SystemExit(main())
