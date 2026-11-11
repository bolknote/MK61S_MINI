#!/usr/bin/env python3
"""Build a standalone Pico native UART diagnostic; no resident firmware edits."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys
R=Path(__file__).resolve().parents[1];ROOT=R.parents[1]
BASE=ROOT/'.build/stm32-module-runtime-20261107/southbridge-runtime'
TOOL=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
sys.path.insert(0,str(R/'tools'));from elf32 import ELF
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--bench',action='store_true');args=parser.parse_args()
 B=BASE/('pico-bench'if args.bench else'pico-probe');name='S3BENCH'if args.bench else'S3PROBE'
 source='bench_app.c'if args.bench else'probe_app.c'
 B.mkdir(exist_ok=True);package=BASE/('module-bench/q4_m3_bench.s3m'if args.bench else'module/q4_dot.s3m')
 assert sha(package)==('48ea05998ef87eebcd0ba418ae90e2ee929ae2091d8faad3a4ca283e42a630ba'if args.bench else'b41523b6bb827859697ce754511938ac985d070cff7c76d3666ac32ed9c2dae7')
 (B/'module_package.h').write_text('static const unsigned char stm3_package[]={'+','.join(str(v)for v in package.read_bytes())+'};\n')
 cmd=[sys.executable,str(ROOT/'tools/apps/portable/build_portable_app.py'),'--target','picocalc-pico-h','--name',name,
      '--arm-toolchain-bin',str(TOOL),'--include',str(R/'pico'),'--include',str(B),'--output-dir',str(B/'app')]
 for file in [source,'stm3_client.c','pico_uart1.c']:cmd+=['--source',str(R/'pico'/file)]
 with(B/'build.log').open('w')as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
 app=B/'app'/(name+'.APP')
 m=dict(status='COMPILED',app=str(app),bytes=app.stat().st_size,sha256=sha(app),module_sha256=sha(package),
        source_hashes={str(p.relative_to(ROOT)):sha(p)for p in(R/'pico').glob('*')if p.is_file()},
        hardware='RP2040 UART1 GP8TX/GP9RX only; no DMA; restores mux/pads/reset and UART registers',
        physical_io=False,deployed=False,pico_firmware_changed=False)
 (B/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');print(json.dumps(m,indent=2))
if __name__=='__main__':main()
