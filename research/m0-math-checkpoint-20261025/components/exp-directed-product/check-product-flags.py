from pathlib import Path
import hashlib,json,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
sys.path[:0]=[str(ROOT/'.build/m0-float-fma-qualification-20261023/support'),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_XPSR,UC_ARM_REG_R12,UC_ARM_REG_SP
from check_stm32_vectors import ElfImage
raw=list(struct.iter_unpack('<QQ',(W/'product-unit-inputs.bin').read_bytes()))
jobs=[raw[(i*1069)%len(raw)] for i in range(64)]
machines={label:Machine(W/('product-'+label+'.elf'),True) for label in ('old','new')}
state={'flags':0};minimum={label:SP for label in machines}
for label,m in machines.items():
 entry=m.elf.symbols['mk61_m0_pow_exp_product']&~1
 def initialize(uc,pc,size,user):
  uc.reg_write(UC_ARM_REG_XPSR,0x01000000|(state['flags']<<28))
  uc.reg_write(UC_ARM_REG_R12,0xBAD0F00D^state['flags'])
 m.uc.hook_add(UC_HOOK_CODE,initialize,begin=entry,end=entry)
 def bounds(uc,pc,size,user,label=label,m=m,entry=entry):
  assert entry<=pc<entry+m.elf.sizes['mk61_m0_pow_exp_product']
  sp=uc.reg_read(UC_ARM_REG_SP);assert not sp&3
  minimum[label]=min(minimum[label],sp)
 m.uc.hook_add(UC_HOOK_CODE,bounds)
for flags in range(16):
 state['flags']=flags
 for a,b in jobs:
  values={}
  for label,m in machines.items():
   got,_,cost=m.call('mk61_m0_pow_exp_product',a,b,count=True);values[label]=got
   assert cost==(79 if label=='old' else 77)
  assert values['old']==values['new']
  retained=sum(((a>>(16*i))&65535)*((b>>(16*j))&65535)<<(16*(i+j)) for i in range(4) for j in range(4) if i+j>=2)
  assert machines['new'].uc.reg_read(UC_ARM_REG_R12)==((retained>>32)&0xffffffff)
assert {k:SP-v for k,v in minimum.items()}=={'old':36,'new':36}
out=dict(status='PASS_ALL16_INCOMING_NZCV_VARIANTS_AND_PRIVATE_FRACTION',
 raw_pairs=64,initial_NZCV_variants=16,fresh_ARM_calls=2048,new_exact_retained_fraction_checks=1024,
 all_return_bits_ABI_SP_word_alignment_active_PC_and_bounded_writes_checked=True,
 stack_frame_bytes={'old':36,'new':36},instruction_counts={'old':79,'new':77},
 bare_ELF_sha256={k:hashlib.sha256((W/('product-'+k+'.elf')).read_bytes()).hexdigest() for k in machines},
 no_ROM_firmware_arithmetic_mocks_or_SIO=True,hardware_accessed=False)
(W/'product-flags-proof.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
