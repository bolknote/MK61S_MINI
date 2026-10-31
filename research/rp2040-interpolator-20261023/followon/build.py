#!/usr/bin/env python3
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OUT=ROOT/'.build/rp2040-interpolator-20261023/followon'
sys.path.insert(0,str(ROOT/'tools'))
from build_picocalc import compiler_bin

def main():
 p=argparse.ArgumentParser();p.add_argument('--apps',action='store_true');a=p.parse_args()
 out=OUT;out.mkdir(parents=True,exist_ok=True);tc=compiler_bin(None)
 flags=['-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-Os','-fno-builtin','-ffunction-sections','-fdata-sections','-I'+str(HERE)]
 objs=[]
 for name in ('lookup.cpp','pop.cpp','roots.cpp','sqrt-full.S','divide.S'):
  source=HERE/name;obj=out/(name+'.o');objs.append(obj)
  cmd=[tc/('arm-none-eabi-g++' if source.suffix=='.cpp' else 'arm-none-eabi-gcc'),*flags,
       *(['-std=c++17','-fno-exceptions','-fno-rtti'] if source.suffix=='.cpp' else []),'-c',source,'-o',obj]
  subprocess.run([str(x) for x in cmd],check=True)
 ld=out/'kernels.ld';ld.write_text('SECTIONS { . = 0x10001000; .text : { *(.text*) *(.m0_pow*) *(.rodata*) } . = 0x20000000; .data : { *(.data*) } .bss : { *(.bss*) *(COMMON) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) } }\n')
 subprocess.run([str(x) for x in [tc/'arm-none-eabi-gcc',*flags,'-nostdlib',*objs,'-Wl,-T,'+str(ld),'-Wl,-e,fo_ln_cpu','-lgcc','-o',out/'kernels.elf']],check=True)
 if a.apps:
  apps={}
  for ident,(variant,name,sources) in enumerate((('lookup','FLOOK',('lookup.cpp',)),('pop','FPOP',('pop.cpp',)),('sqrt','FSQRT',('roots.cpp','sqrt-full.S','divide.S')),('rsqrt','FRSQRT',('roots.cpp','divide.S'))),1):
   dest=out/'apps'/variant;dest.mkdir(parents=True,exist_ok=True)
   wrapper=dest/'entry.c';wrapper.write_text(f'#define INTERP_VARIANT {ident}\n'+('#define INTERP_SAMPLES 32\n' if variant=='pop' else '')+f'#include "{HERE}/benchmark.c"\n')
   cmd=[sys.executable,ROOT/'tools/build_portable_app.py','--target','picocalc-pico-h','--name',name,'--source',wrapper,'--include',HERE,'--arm-toolchain-bin',tc,'--output-dir',dest]
   for source in sources:cmd+=['--source',HERE/source]
   with (dest/'build.log').open('w') as f:subprocess.run([str(x) for x in cmd],check=True,stdout=f,stderr=subprocess.STDOUT)
   layout=json.loads((dest/(name+'.json')).read_text());app=dest/(name+'.APP')
   assert layout['memory_bytes']<=24576,(variant,layout['memory_bytes'])
   apps[variant]=dict(name=name,path=str(app),sha256=hashlib.sha256(app.read_bytes()).hexdigest(),app_bytes=app.stat().st_size,memory_bytes=layout['memory_bytes'],elf=str(dest/(name+'.elf')))
  (out/'app-manifest.json').write_text(json.dumps(dict(status='BUILT',schema=4,namespace='/INTRP02',apps=apps),indent=2)+'\n')
  print(json.dumps(apps,indent=2))
 else:print(str(out/'kernels.elf'))
if __name__=='__main__':main()
