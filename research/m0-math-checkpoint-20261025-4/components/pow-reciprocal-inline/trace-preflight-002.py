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
 for tag in['mk61_m0_reciprocal1','mk61_m0_reciprocal1_sw']:
  address=e.symbols[tag+'_first_product']&~1
  def product(uc,pc,unused,user):products.append(uc.reg_read(UC_ARM_REG_R6))
  m.uc.hook_add(UC_HOOK_CODE,product,begin=address,end=address)
 address=e.symbols[linked['images']['candidate'if label=='candidate'else'control']['seed_symbol']]&~1
 def seed(uc,pc,unused,user):
  assert uc.reg_read(UC_ARM_REG_SP)%8==0 if label!='candidate'else uc.reg_read(UC_ARM_REG_SP)==SP-20
  d=uc.reg_read(UC_ARM_REG_R1);assert 65536<=d<131072
  seeds.append(d)
 m.uc.hook_add(UC_HOOK_CODE,seed,begin=address,end=address)
 return calls,seeds,products
def expected_saving(trace):
 from model import inline_saving
 calls,seeds,products=trace
 # All existing public root reciprocals are guarded normal. No input or
 # reference is filtered; this assertion audits the full actual corpus.
 assert all(1<=((int(r['denominator'],16)>>52)&2047)<=2044 for r in calls)
 return 2*len(products)+sum(inline_saving(D)for D in seeds)
