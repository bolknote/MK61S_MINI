"""Replace only the frozen prefix section in a diagnostic link with an experimental factor route."""
import hashlib
import json
from pathlib import Path
import re
import shlex
import struct
import subprocess

import argparse
root=Path.cwd();archive=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--parent-work',type=Path,required=True,help='Frozen V122 source/build/firmware work directory')
parser.add_argument('--output',type=Path,required=True,help='New private output directory')
args=parser.parse_args()
parent=args.parent_work.resolve();work=args.output.resolve()
assert not work.exists(),work
work.mkdir(parents=True)
unit=next(r for r in json.loads((parent/'build/compile_commands.json').read_text()) if r['file'].endswith('/code/native_eabi_m0.cpp'))
compiler=Path(shlex.split(unit['command'])[0])
objcopy=compiler.with_name('arm-none-eabi-objcopy');nm=compiler.with_name('arm-none-eabi-nm')
old=next((parent/'build/CMakeFiles/mk61s-picocalc-pico-h.dir').rglob('native_eabi_m0_rp2040.S.o'))
stripped=work/'native_eabi_m0_rp2040.S.o'
subprocess.run([str(objcopy),'--strip-debug','--remove-section=.m0_pow_root_prefix',
    '--remove-section=.ARM.exidx.m0_pow_root_prefix',str(old),str(stripped)],check=True)
table=(parent/'source/code/native_eabi_m0_rsqrt_table.inc').read_text().split('={',1)[1]
words=[int(n) for n in re.findall(r'\b(\d+)U\b',table)]
assert len(words)==512
data=(parent/'firmware/mk61s-picocalc-pico-h.elf').read_bytes();block=struct.pack('<512I',*words)
offset=data.find(block);assert offset>=0 and data.find(block,offset+1)<0
phoff=struct.unpack_from('<I',data,28)[0];size,count=struct.unpack_from('<HH',data,42)
for i in range(count):
    typ,pos,va,pa,filesz,memsz,flags,align=struct.unpack_from('<8I',data,phoff+i*size)
    if typ==1 and pos<=offset and offset+len(block)<=pos+filesz:seed_address=va+offset-pos
lines=subprocess.check_output(['/opt/homebrew/bin/ninja','-C',str(parent/'build'),'-t','commands','mk61s-picocalc-pico-h.elf'],text=True).splitlines()
line=next(s for s in reversed(lines) if ' -o mk61s-picocalc-pico-h.elf ' in s)
tokens=shlex.split(line);start=next(i for i,t in enumerate(tokens) if t.endswith('arm-none-eabi-g++'))
end=next((i for i in range(start+1,len(tokens)) if tokens[i]=='&&'),len(tokens));link_base=tokens[start:end]
index=next(i for i,s in enumerate(link_base) if s.endswith('/code/native_eabi_m0_rp2040.S.o'))
link_base[index]=str(stripped)
before=(archive/'before.cpp.inc').read_text();factor=(archive/'factor.cpp.inc').read_text();entry=(archive/'entry.cpp.inc').read_text()
marker='  PowInteger128 power={((xb&D::Fraction)|D::Hidden)<<11,0,int(xb>>52)-1023,0};'
assert entry.count(marker)==1
entry=entry.replace(marker,'  if(denominator!=1) return factor_pow(xb,numerator,denominator,inverse);\n'+marker)
text=before+factor+entry
rows=[]
for level in ('Os','O2'):
    folder=work/level;folder.mkdir(exist_ok=True)
    cpp=folder/'kernels.cpp';cpp.write_text(text);obj=folder/'kernels.o'
    flags=['/usr/bin/clang++','--target=arm-none-eabi','-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-'+level,
           '-std=c++17','-ffreestanding','-fno-exceptions','-fno-rtti','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-ffunction-sections','-fdata-sections']
    with (folder/'compile.log').open('w') as log:
        subprocess.run(flags+['-c',str(cpp),'-o',str(obj)],cwd=root,stdout=log,stderr=subprocess.STDOUT,check=True)
    undefined=subprocess.check_output([str(nm),'-u',str(obj)],text=True)
    allowed={'pow_integer128_multiply','pow_integer128_square','pow_sqrt64_raw','_ZN7m0_eabi5clz32Em',
             '__aeabi_ddiv','factor_rsqrt_seeds','mk61_m0_math_udiv32'}
    assert {line.split()[-1] for line in undefined.splitlines()}<=allowed,undefined
    link=list(link_base)+[str(obj),'-Wl,--defsym=factor_rsqrt_seeds='+hex(seed_address)]
    elf=folder/'diagnostic.elf';link[link.index('-o')+1]=str(elf)
    for i,s in enumerate(link):
        if s.startswith('-Wl,-Map='):link[i]='-Wl,-Map='+str(folder/'diagnostic.map')
    with (folder/'link.log').open('w') as log:
        subprocess.run(link,cwd=parent/'build',stdout=log,stderr=subprocess.STDOUT,check=True)
    row=dict(level=level,elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),cpp_sha256=hashlib.sha256(cpp.read_bytes()).hexdigest(),
             existing_seed_address=hex(seed_address),link=link,kernel_command=flags)
    (folder/'build.json').write_text(json.dumps(row,indent=2)+'\n');rows.append(row)
    print('Linked diagnostic',level,flush=True)
(work/'builds.json').write_text(json.dumps(dict(status='EXPERIMENTAL_FACTOR_LINK_ONLY',variants=rows,hardware_accessed=False,root_promoted=False),indent=2)+'\n')
