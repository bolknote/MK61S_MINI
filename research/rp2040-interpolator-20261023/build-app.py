#!/usr/bin/env python3
"""Build a relocatable SRAM APP. Never opens a serial port or flashes firmware."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from build_picocalc import compiler_bin

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--output',type=Path,default=ROOT/'.build/rp2040-interpolator-20261023/app')
 p.add_argument('--toolchain',type=Path);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
 tc=compiler_bin(a.toolchain);apps={}
 for ident,(variant,name) in enumerate((('alu','IALU'),('rsqrt','IRSQ'),('sqrt','ISQRT'),('address','IADDR')),1):
  dest=out/variant;dest.mkdir(parents=True,exist_ok=True)
  wrapper=dest/'entry.c';wrapper.write_text(f'#define INTERP_VARIANT {ident}\n#include "{HERE}/benchmark.c"\n')
  command=[sys.executable,ROOT/'tools/build_portable_app.py','--target','picocalc-pico-h','--name',name,
    '--include',HERE,'--arm-toolchain-bin',tc,'--output-dir',dest,'--source',wrapper]
  for source in ('kernels.cpp','divide.S','root_seed.S'):command+=['--source',HERE/source]
  with (dest/'build.log').open('w') as f:subprocess.run([str(x) for x in command],check=True,stdout=f,stderr=subprocess.STDOUT)
  app=dest/(name+'.APP');layout=json.loads((dest/(name+'.json')).read_text())
  assert layout['memory_bytes']<=24576,(variant,'A748 free heap headroom',layout['memory_bytes'])
  apps[variant]=dict(name=name,app=str(app),app_bytes=app.stat().st_size,memory_bytes=layout['memory_bytes'],elf=str(dest/(name+'.elf')),
    app_sha256=hashlib.sha256(app.read_bytes()).hexdigest(),command=[str(x) for x in command])
 report=dict(status='PREPARED_NOT_HARDWARE_TESTED',hardware_verified=False,apps=apps,
   directory='/INTRP01',created_objects=['IALU.app','IRSQ.app','ISQRT.app','IADDR.app','MARKER.bin','RESULT.bin'],
   target_build='A7483AE6',target_uid='E6657CD423721C35',core=0,
   timing='4096-call batches; seven ABBA/BAAB rounds; raw monotonic microseconds; interrupts enabled; output outside timings',
   state='Save ACCUM/BASE/CTRL on both core-local interpolators, no POP reads; restore and readback after each batch. Idle divider preserved.',
   per_call_mode='Includes snapshot of both interpolators, setup and restore for every candidate call; prepared mode amortises setup across a batch.')
 (out/'app-manifest.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(dict(status=report['status'],apps={k:{x:v[x] for x in ('name','app_bytes','memory_bytes','app_sha256')} for k,v in apps.items()}),indent=2))
if __name__=='__main__':main()
