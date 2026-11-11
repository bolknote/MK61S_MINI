#!/usr/bin/env python3
"""Package the separate DWT/native-kernel/512-byte-output module."""
from pathlib import Path
import binascii,hashlib,json,struct,subprocess,sys
R=Path(__file__).resolve().parents[1];ROOT=R.parents[1]
B=ROOT/'.build/stm32-module-runtime-20261107/southbridge-runtime/module-bench'
sys.path.insert(0,str(R/'tools'));from build import tool,run
from elf32 import ELF
B.mkdir(exist_ok=True)
elf=B/'q4_m3_bench.elf';binary=B/'q4_m3_bench.bin';package=B/'q4_m3_bench.s3m'
flags=['-mcpu=cortex-m3','-mthumb','-mfloat-abi=soft','-std=c11','-Os','-g','-mword-relocations','-ffreestanding','-fno-builtin','-fno-common','-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-fdata-sections','-ffunction-sections','-Wall','-Wextra','-Werror','-I'+str(R/'include')]
run([tool('gcc'),*flags,'-nostdlib',R/'modules/q4_m3_bench.c','-Wl,-T,'+str(R/'modules/module.ld'),'-Wl,--emit-relocs,--gc-sections','-o',elf],B/'build.log')
subprocess.run([tool('objcopy'),'-O','binary','-j','.image',str(elf),str(binary)],check=True)
e=ELF(elf);image=binary.read_bytes();memory=e.symbols['__memory_end']['value']-0x20000000
relocs=[]
for at,typ in e.relocations():
 if typ==2:relocs.append(at-0x20000000)
 elif typ not in [3,10,30,42]:raise ValueError('Unsupported relocation '+str(typ))
relocs=sorted(set(relocs));assert 0<len(relocs)<=64 and memory<=6144
for at in relocs:assert at%4==0 and at+4<=len(image)and 0x20000000<=struct.unpack_from('<I',image,at)[0]<=0x20000000+memory
for name,s in e.symbols.items():assert s['index']!=0,'Undefined '+name
payload=image+b''.join(struct.pack('<I',v)for v in relocs)
words=[0x314d3353,1,64,64+len(payload),len(image),memory-len(image),e.entry-0x20000000,len(relocs),512,512,256,2000,binascii.crc32(payload),0,0x70301]
header=struct.pack('<15I',*words);package.write_bytes(header+struct.pack('<I',binascii.crc32(header))+payload)
disassembly=subprocess.check_output([tool('objdump'),'-d',str(elf)],text=True);(B/'disassembly.txt').write_text(disassembly)
assert disassembly.count('ubfx')>=8 and disassembly.count('sbfx')>=8
m=dict(status='COMPILED',package=str(package),package_bytes=package.stat().st_size,
       sha256=hashlib.sha256(package.read_bytes()).hexdigest(),memory_bytes=memory,bss_bytes=memory-len(image),
       relocations=relocs,kernels=['word-loop','unrolled-UBFX','XOR8-unrolled-SBFX'],
       physical_io=False,hardware_timing_measured=False)
(B/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');print(json.dumps(m,indent=2))
