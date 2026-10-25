"""Old exact high residual and certified sign are actual isolated ARM code."""
from pathlib import Path
import hashlib,json,subprocess
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-pow-reciprocal-inline-20261025'
source=(P/'candidate-ddiv.S').read_text();start=source.index('.macro mul32_32_64 ');end=source.index('.endm',start)+len('.endm');mul=source[start:end]
header=source[:source.index('#if')]
tc=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin');commands=[];images={}
for label in ['control','candidate']:
 code=header+'.syntax unified\n.cpu cortex-m0plus\n.thumb\n'+mul+'\n#include "remainder-certificate.inc"\n.section .unit,"ax",%progbits\n.p2align 2\n.global unit_remainder_sign\n.type unit_remainder_sign,%function\n.thumb_func\nunit_remainder_sign:\n push {r4-r7,lr}\n mov r4,r0\n mov r0,r2\n mov r2,r1\n.global unit_certificate_begin\nunit_certificate_begin:\n'
 if label=='candidate':code+=' remainder_certificate .Lfull,.Lnegative\n movs r0,#1\n pop {r4-r7,pc}\n.Lfull:\n adds r4,r5\n'
 code+=''' mul32_32_64 r2,r0, r2,r3, r5,r6,r7,r2,r3
 negs r2,r2
 sbcs r4,r3
 cmp r4,#0
 beq .Lzero
 bmi .Lnegative
 movs r0,#1
 pop {r4-r7,pc}
.Lnegative:
 movs r0,#0
 subs r0,#1
 pop {r4-r7,pc}
.Lzero:
 movs r0,#0
 pop {r4-r7,pc}
.size unit_remainder_sign,.-unit_remainder_sign
.section .note.GNU-stack,"",%progbits
'''
 (W/(label+'.S')).write_text(code)
 (W/(label+'.ld')).write_text('PHDRS { code PT_LOAD FLAGS(5); }\nSECTIONS { .unit 0x101e1000 : { KEEP(*(.unit)) } :code\n/DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) *(.ARM.attributes) } }\n')
 for c in [[str(tc/'arm-none-eabi-gcc'),'-mcpu=cortex-m0plus','-mthumb','-c',str(W/(label+'.S')),'-o',str(W/(label+'.o'))],
  [str(tc/'arm-none-eabi-ld'),'--gc-sections','-e','unit_remainder_sign','-T',str(W/(label+'.ld')),str(W/(label+'.o')),'-o',str(W/(label+'.elf'))]]:
  subprocess.run(c,cwd=W,check=True);commands.append(c)
 images[label]=dict(ELF_sha256=hashlib.sha256((W/(label+'.elf')).read_bytes()).hexdigest())
(W/'build.json').write_text(json.dumps(dict(status='BUILT_EXACT_AND_CERTIFIED_SIGN_UNIT',images=images,commands=commands,hardware_accessed=False),indent=2)+'\n')
