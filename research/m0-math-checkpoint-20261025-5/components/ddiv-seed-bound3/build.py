"""Bounded exact quotient correction under private numerator-one R0=0."""
from pathlib import Path
from collections import Counter
import hashlib,json,subprocess
W=Path(__file__).resolve().parent;ROOT=W.parents[1];P=ROOT/'.build/m0-pow-reciprocal-zero-20261025'
assert not(W/'FROZEN.json').exists()
tc=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
old=(P/'inline-seed.inc').read_text();needle='''.Linline_seed_high:
 subs r6,#1
 adds r7,r1
 bmi .Linline_seed_high
''';assert old.count(needle)==1
new=old.replace(needle,'''.Linline_seed_high:
 subs r6,#1
 adds r7,r1
 bpl .Linline_seed_done
 subs r6,#1
 adds r7,r1
 sbcs r6,r0                   @ private raw R0=0; borrow corrects third step
''')
(W/'control-seed.inc').write_text(old);(W/'candidate-seed.inc').write_text(new)
(W/'inline-seed-table.inc').write_bytes((P/'inline-seed-table.inc').read_bytes())
table=[]
for line in (W/'inline-seed-table.inc').read_text().splitlines():
 if line.startswith(' .hword '):table.extend(int(x,0)for x in line[8:].split(','))
hist=Counter();models=[]
for D in range(65536,131072):
 u=table[(D>>9)-128];e=(((D+1)//2)*u-(1<<31))//65536;q=u-u*e//32768;exact=0xffffffff//D;error=q-exact
 assert -1<=error<=3
 residual=0xffffffff-q*D;corrected=q;new_residual=residual
 if residual<0:
  corrected-=1;new_residual+=D
  if new_residual<0:
   corrected-=1;new_residual+=D
   carry=new_residual>=0
   corrected-=not carry
 elif residual>=D:corrected+=1;new_residual-=D
 assert corrected==exact and new_residual==(0xffffffff-exact*D)-(D if error==3 else 0)
 hist[error]+=1;models.append(dict(D=D,initial=q,exact=exact,error=error,control_residual=0xffffffff-exact*D,candidate_residual=new_residual))
(W/'integer-model.json').write_text(json.dumps(dict(status='PASS_ALL65536_EXACT_QUOTIENT_BOUND_AND_CARRY_MODEL',divisors=65536,estimate_error_histogram=dict(hist),private_R0_zero_required=True,third_step_R7_residual_intentionally_dead=True,actual_ARM_or_MPFR_calls=0,rows=models),indent=2)+'\n')
commands=[];images={}
for label in ['control','candidate']:
 source='''#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
.syntax unified
.cpu cortex-m0plus
.thumb
#include "'''+label+'''-seed.inc"
.section .unit,"ax",%progbits
.p2align 2
.global unit_inline_seed
.type unit_inline_seed,%function
.thumb_func
unit_inline_seed:
 push {r4-r7,lr}
 reciprocal_seed_inline
 mov r0,r6
 pop {r4-r7,pc}
.size unit_inline_seed,.-unit_inline_seed
#include "inline-seed-table.inc"
#endif
.section .note.GNU-stack,"",%progbits
'''
 (W/(label+'.S')).write_text(source)
 (W/(label+'.ld')).write_text('PHDRS { code PT_LOAD FLAGS(5); }\nSECTIONS { .unit 0x101e1000 : { KEEP(*(.unit)) } :code\n/DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) *(.ARM.attributes) } }\n')
 for c in [[str(tc/'arm-none-eabi-gcc'),'-mcpu=cortex-m0plus','-mthumb','-DMK61_M0_RP2040_EABI=1','-c',str(W/(label+'.S')),'-o',str(W/(label+'.o'))],
           [str(tc/'arm-none-eabi-ld'),'--gc-sections','-e','unit_inline_seed','-T',str(W/(label+'.ld')),str(W/(label+'.o')),'-o',str(W/(label+'.elf'))]]:
  subprocess.run(c,cwd=W,check=True);commands.append(c)
 images[label]=dict(ELF_sha256=hashlib.sha256((W/(label+'.elf')).read_bytes()).hexdigest())
(W/'build.json').write_text(json.dumps(dict(status='BUILT_BOUND3_PRIVATE_ZERO_SEED_NOT_ARM_QUALIFIED',commands=commands,images=images,source_parent_FROZEN_sha256=hashlib.sha256((P/'FROZEN.json').read_bytes()).hexdigest(),table_unchanged=True,hardware_accessed=False),indent=2)+'\n')
print(json.dumps(dict(status='MODEL_PASS_AND_UNIT_BUILT',divisors=65536,estimate_error_histogram=dict(hist)),indent=2))
