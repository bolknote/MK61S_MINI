"""Private bit-exact reciprocal-root overlay, no firmware/device writes."""
from pathlib import Path
import hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
S=ROOT/'.build/m0-pow-square-ordinary-20261024'
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(S/'candidate.elf')=='6e1cf7ded4ee258b49ddffcd1e893f4ec170700b181265048ad06ce0b9c1b8ae'
resident=ElfImage(P/'firmware/mk61s-picocalc-pico-h.elf')
parent=ElfImage(S/'candidate.elf')
control=(S/'candidate.S').read_text()
assert control.count('ldr r2,=pow_rsqrt')==1
(W/'control.S').write_text(control)
(W/'candidate.S').write_text(control.replace('ldr r2,=pow_rsqrt','ldr r2,=mk61_m0_pow_rsqrt_fast'))
names=['mk61_m0_pow_dispatch','__aeabi_ddiv','mk61_m0_sqrt','pow_rsqrt','factor_rsqrt_seeds']
bindings={n:resident.symbols[n] for n in names}
bindings['mk61_m0_pow_rsqrt_boundary']=resident.symbols['pow_rsqrt_boundary']
bindings.update({n:parent.symbols[n] for n in ['mk61_m0_pow_square_exact','mk61_m0_pow_dispatch_ordinary']})
text=''.join(n+' = '+hex(a)+';\n' for n,a in bindings.items())
text+='''PHDRS { entry PT_LOAD FLAGS(5); rsqrt PT_LOAD FLAGS(5); }
SECTIONS {
 .pow 0x101614cc : { *(.m0_pow_dispatch_extension) } :entry
 .rsqrt 0x10162800 : { *(.m0_pow_rsqrt_fast_only) } :rsqrt
 /DISCARD/ : { *(.ARM*) *(.comment) *(.note*) }
}
'''
(W/'entry.ld').write_text(text)
cc=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
commands=[];meta={}
for source in ('control','candidate','rsqrt'):
 command=[str(cc/'arm-none-eabi-gcc'),'-mcpu=cortex-m0plus','-mthumb','-DMK61_USE_M0_EABI=1','-DMK61_M0_RP2040_EABI=1','-c',str(W/(source+'.S')),'-o',str(W/(source+'.o'))]
 subprocess.run(command,cwd=W,check=True);commands.append(command)
for label in ('control','candidate'):
 command=[str(cc/'arm-none-eabi-ld'),'--gc-sections','-e','mk61_m0_pow_fast','-T',str(W/'entry.ld'),str(W/(label+'.o'))]
 if label=='candidate':command.append(str(W/'rsqrt.o'))
 command+=['-o',str(W/(label+'.elf'))]
 subprocess.run(command,cwd=W,check=True);commands.append(command)
 im=ElfImage(W/(label+'.elf'))
 assert im.symbols['mk61_m0_pow_fast']==parent.symbols['mk61_m0_pow_fast']
 code=im.bytes_at(im.named_sections['.pow'])
 assert len(code)==len(parent.bytes_at(parent.named_sections['.pow']))
 if label=='control':assert code==parent.bytes_at(parent.named_sections['.pow'])
 expected=set()
 for n,s in im.named_sections.items():
  if s[2]&2 and s[5]:
   assert n in ('.pow','.rsqrt');expected.add((s[3],s[5]))
   if n=='.rsqrt':
    for source in (resident,parent):
     assert not any(old[2]&2 and old[5] and max(old[3],s[3])<min(old[3]+old[5],s[3]+s[5]) for old in source.named_sections.values())
 loads=[p for p in im.segments if p[0]==1 and p[4]]
 assert {(p[2],p[4]) for p in loads}==expected
 assert all(p[2]==p[3] and p[4]==p[5] for p in loads)
 assert not subprocess.check_output([str(cc/'arm-none-eabi-nm'),'-u',str(W/(label+'.elf'))],text=True)
 with (W/(label+'.dis')).open('w') as f:subprocess.run([str(cc/'arm-none-eabi-objdump'),'-d',str(W/(label+'.elf'))],stdout=f,check=True)
 meta[label]={'ELF_sha256':sha(W/(label+'.elf')),'sections':{n:s[5] for n,s in im.named_sections.items() if s[2]&2 and s[5]},'symbols':{n:im.symbols[n] for n in ('mk61_m0_pow_fast','mk61_m0_pow_rsqrt_fast','mk61_m0_pow_center_quotient','mk61_m0_pow_rsqrt_point') if n in im.symbols}}
unit_text=''.join(n+' = '+hex(a)+';\n' for n,a in bindings.items())
unit_text+='''PHDRS { unit PT_LOAD FLAGS(5); }
SECTIONS { .quotient 0x10170000 : { *(.m0_pow_center_quotient_unit_only) } :unit
 /DISCARD/ : { *(.ARM*) *(.comment) *(.note*) } }
'''
(W/'unit.ld').write_text(unit_text)
command=[str(cc/'arm-none-eabi-ld'),'--gc-sections','-e','mk61_m0_pow_center_quotient','-T',str(W/'unit.ld'),str(W/'rsqrt.o'),'-o',str(W/'unit.elf')]
subprocess.run(command,cwd=W,check=True);commands.append(command)
unit=ElfImage(W/'unit.elf');assert {n for n,s in unit.named_sections.items() if s[2]&2 and s[5]}=={'.quotient'}
out={'status':'BUILT_UNQUALIFIED_PRIVATE_RSQRT_OVERLAY','parent_ELF_sha256':sha(S/'candidate.elf'),'rsqrt_source_sha256':sha(W/'rsqrt.S'),'images':meta,'unit_ELF_sha256':sha(W/'unit.elf'),'bindings':bindings,'commands':commands,'canonical_or_Git_or_hardware_changed':False}
(W/'build.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='commands'},indent=2))
