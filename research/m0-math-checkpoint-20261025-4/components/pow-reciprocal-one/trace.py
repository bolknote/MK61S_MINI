"""Trace the proven root-only call and the exact operations being simplified."""
from harness import *
from unicorn.arm_const import UC_ARM_REG_LR,UC_ARM_REG_SP,UC_ARM_REG_R6
def reciprocal_trace(m,label):
 calls=[];seeds=[];products=[]
 e=division_images['candidate']if label=='candidate'else division_images['control']
 entry=e.symbols[linked['images']['candidate'if label=='candidate'else'control']['entry_symbol']]&~1
 ret=0x1014e668+linked['root_call_relocation_offset']+4
 def capture(uc,pc,unused,user):
  assert(uc.reg_read(UC_ARM_REG_LR)&~1)==ret
  a=uc.reg_read(UC_ARM_REG_R0)|(uc.reg_read(UC_ARM_REG_R1)<<32)
  b=uc.reg_read(UC_ARM_REG_R2)|(uc.reg_read(UC_ARM_REG_R3)<<32)
  assert a==bits(1.)
  calls.append(dict(numerator=f'{a:016X}',denominator=f'{b:016X}'))
 m.uc.hook_add(UC_HOOK_CODE,capture,begin=entry,end=entry)
 for tag in(['mk61_m0_reciprocal1','mk61_m0_reciprocal1_sw']if label=='candidate'else['mk61_m0_hint','mk61_m0_sw']):
  address=e.symbols[tag+'_first_product']&~1
  def product(uc,pc,unused,user):products.append(uc.reg_read(UC_ARM_REG_R6))
  m.uc.hook_add(UC_HOOK_CODE,product,begin=address,end=address)
 address=e.symbols['mk61_m0_ddiv_seed17']&~1
 def seed(uc,pc,unused,user):
  assert uc.reg_read(UC_ARM_REG_SP)%8==0
  d=uc.reg_read(UC_ARM_REG_R1);assert 65536<=d<131072
  seeds.append(d)
 m.uc.hook_add(UC_HOOK_CODE,seed,begin=address,end=address)
 return calls,seeds,products
def expected_saving(trace):
 calls,seeds,products=trace
 guard=0
 for r in calls:
  exponent=(int(r['denominator'],16)>>52)&2047
  guard+=11 if 1<=exponent<=2044 else 12 if exponent in[2045,2046]else 5
 return guard+15*len(products)+8*len(seeds)
