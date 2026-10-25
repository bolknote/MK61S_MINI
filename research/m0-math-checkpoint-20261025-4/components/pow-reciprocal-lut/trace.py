"""Trace only the actual root reciprocal call and its software seed."""
import struct
from harness import *
from unicorn.arm_const import UC_ARM_REG_LR,UC_ARM_REG_SP
def reciprocal_trace(m,label):
 calls=[];seeds=[]
 image=division_images['candidate']if label=='candidate'else division_images['control']
 entry=m.elf.symbols['mk61_m0_hint_ddiv']&~1
 return_address=0x1014e668+linked['root_call_relocation_offset']+4
 def capture(uc,pc,unused,user):
  if (uc.reg_read(UC_ARM_REG_LR)&~1)!=return_address:return
  a=uc.reg_read(UC_ARM_REG_R0)|(uc.reg_read(UC_ARM_REG_R1)<<32)
  b=uc.reg_read(UC_ARM_REG_R2)|(uc.reg_read(UC_ARM_REG_R3)<<32)
  assert a==bits(1.)
  calls.append(dict(numerator=f'{a:016X}',denominator=f'{b:016X}'))
 m.uc.hook_add(UC_HOOK_CODE,capture,begin=entry,end=entry)
 if label=='candidate':
  address=image.symbols['mk61_m0_ddiv_seed17']&~1
  def seed(uc,pc,unused,user):
   assert uc.reg_read(UC_ARM_REG_SP)%8==0
   d=uc.reg_read(UC_ARM_REG_R1);assert 65536<=d<131072
   seeds.append(d)
  m.uc.hook_add(UC_HOOK_CODE,seed,begin=address,end=address)
 return calls,seeds
