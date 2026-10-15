#!/usr/bin/env python3
'''Build normal matched residents; only the encoder implementation differs.'''
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests'))
from hil_packbits_firmware import firmware_info
from prepare_zx0_prototypes import BASELINE_REF

def run(command,env):
    subprocess.run(list(map(str,command)),env=env,check=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--variant',choices=('control','candidate'),required=True)
    p.add_argument('--jobs',type=int,default=6)
    p.add_argument('--base-ref',default=BASELINE_REF,help='common immutable source commit for both images')
    a=p.parse_args();out=a.output_dir.resolve()/a.variant
    source=out/'source';assert not source.exists(),'use a fresh source snapshot'
    source.mkdir(parents=True)
    commit=subprocess.check_output(['git','rev-parse',a.base_ref],cwd=ROOT,text=True).strip()
    archive=subprocess.check_output(['git','archive',commit],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:tar.extractall(source,filter='data')
    shutil.copy2(ROOT/'code/zx0_encode_kernels.hpp',source/'code/zx0_encode_kernels.hpp')
    if a.variant=='candidate':shutil.copy2(ROOT/'code/zx0_encode.cpp',source/'code/zx0_encode.cpp')
    else:
        original=subprocess.check_output(['git','show',BASELINE_REF+':code/zx0_encode.cpp'],cwd=ROOT)
        (source/'code/zx0_encode.cpp').write_bytes(original)
    epoch=subprocess.check_output(['git','show','-s','--format=%ct',commit],cwd=ROOT,text=True).strip()
    env=dict(os.environ,SOURCE_DATE_EPOCH=epoch)
    command=[sys.executable,source/'tools/.mk61-gcc/build-standalone.py',
        '--source-root',source,'--build-path',out/'build','--profile','classic-v3','--mcu','f411',
        '--jobs',a.jobs]
    (out/'build-command.json').write_text(json.dumps(list(map(str,command)),indent=2)+'\n')
    run(command,env)
    binary=out/'build/resident.bin';elf=out/'build/resident.elf'
    run(['bash',source/'tools/seal-firmware.sh','seal','--max-size','524288',binary],env)
    run(['bash',source/'tools/seal-firmware.sh','check','--max-size','524288',binary],env)
    run([sys.executable,source/'tools/seal-firmware-elf.py','--bin',binary,'--elf',elf,
        '--compile-commands',out/'build/compile_commands.json'],env)
    hashes={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (source/'code').rglob('*') if p.is_file()}
    evidence=dict(variant=a.variant,source_commit=commit,baseline_encoder_ref=BASELINE_REF,
        firmware=firmware_info(binary),elf=str(elf),source_hashes=hashes,
        profile=json.loads((out/'build/standalone-profile.json').read_text()),source_date_epoch=epoch)
    (out/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(a.variant,evidence['firmware'],flush=True)
if __name__=='__main__':main()
