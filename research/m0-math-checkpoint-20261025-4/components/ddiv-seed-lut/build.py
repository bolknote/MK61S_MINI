"""Build own small-table exact integer seeds as isolated ARM components."""
from pathlib import Path
import hashlib,json,subprocess
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
assert not (W/'FROZEN.json').exists()
tc=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
variants={'lut128_ceil_inner':(128,True,False),'lut128_floor':(128,False,False),'lut64_ceil_outer':(64,False,True),'lut32_ceil_outer':(32,False,True)}
commands=[];meta={};sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for name,(bins,ceil_inner,ceil_outer)in variants.items():
 shift=16-(bins.bit_length()-1);width=1<<shift
 table=[(1<<32)//(65536+i*width+width//2)for i in range(bins)]
 inner='negs r2,r2\n asrs r2,#17\n negs r2,r2'if ceil_inner else'asrs r2,#17'
 outer='negs r2,r2\n asrs r2,#15\n negs r2,r2'if ceil_outer else'asrs r2,#15'
 source=f'''#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
.syntax unified
.cpu cortex-m0plus
.thumb
// Own exact floor((2^32-1)/D), 65536<=D<=131071, R1=D.
// R12 and all callee-saved registers preserved; R0,R2,R3,NZCV clobbered.
.section .m0_ddiv_seed17,"ax",%progbits
.p2align 2
.global mk61_m0_ddiv_seed17
.hidden mk61_m0_ddiv_seed17
.type mk61_m0_ddiv_seed17,%function
.thumb_func
mk61_m0_ddiv_seed17:
 lsrs r0,r1,#{shift}
 subs r0,#{bins}
 lsls r0,#1
 adr r2,.Lseed_table
 ldrh r0,[r2,r0]
 // x=ceil(D/2). Signed folded product represents (x*u-2^31)*2.
 adds r2,r1,#1
 lsrs r2,#1
 muls r2,r0
 lsls r2,#1
 {inner}
 muls r2,r0
 {outer}
 subs r0,r2
 // Signed exact residual N-q*D; low32 product suffices by the bound.
 movs r3,r0
 muls r3,r1
 mvns r3,r3
 bpl .Lseed_low
.Lseed_high_loop:
 subs r0,#1
 adds r3,r1
 bmi .Lseed_high_loop
 bx lr
.Lseed_low:
 cmp r3,r1
 bcc .Lseed_done
.Lseed_low_loop:
 adds r0,#1
 subs r3,r1
 cmp r3,r1
 bcs .Lseed_low_loop
.Lseed_done:
 bx lr
.size mk61_m0_ddiv_seed17,.-mk61_m0_ddiv_seed17
.p2align 2
.Lseed_table:
'''+''.join(' .hword '+','.join(str(v)for v in table[i:i+8])+'\n'for i in range(0,bins,8))+'''#endif
.section .note.GNU-stack,"",%progbits
'''
 (W/(name+'.S')).write_text(source)
 script='PHDRS { code PT_LOAD FLAGS(5); }\nSECTIONS { .seed 0x101e1000 : { KEEP(*(.m0_ddiv_seed17)) } :code\n/DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) *(.ARM.attributes) } }\n'
 (W/(name+'.ld')).write_text(script)
 for command in [[str(tc/'arm-none-eabi-gcc'),'-mcpu=cortex-m0plus','-mthumb','-DMK61_M0_RP2040_EABI=1','-c',str(W/(name+'.S')),'-o',str(W/(name+'.o'))],
                 [str(tc/'arm-none-eabi-ld'),'--gc-sections','-e','mk61_m0_ddiv_seed17','-T',str(W/(name+'.ld')),str(W/(name+'.o')),'-o',str(W/(name+'.elf'))]]:
  subprocess.run(command,check=True);commands.append(command)
 meta[name]=dict(bins=bins,table_bytes=2*bins,input_round='ceil',inner_round='ceil'if ceil_inner else'floor',outer_round='ceil'if ceil_outer else'floor',ELF_sha256=sha(W/(name+'.elf')),source_sha256=sha(W/(name+'.S')))
(W/'build.json').write_text(json.dumps(dict(status='BUILT_OWN_EXACT_CORRECTED_SEED_VARIANTS_NOT_QUALIFIED',variants=meta,commands=commands,hardware_accessed=False),indent=2)+'\n')
print(json.dumps(meta,indent=2))
