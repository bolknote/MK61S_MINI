"""Audit the exact state join and each actual certificate branch."""
from harness import *
from unicorn.arm_const import UC_ARM_REG_LR,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R12,UC_ARM_REG_SP,UC_ARM_REG_XPSR
MASK=(1<<32)-1
REGS=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R12,UC_ARM_REG_SP,UC_ARM_REG_XPSR]
def state(uc):
 sp=uc.reg_read(UC_ARM_REG_SP);r=[uc.reg_read(n)for n in REGS];r[-1]&=0xf0000000
 return dict(registers=r,frame28=bytes(uc.mem_read(sp,28)).hex())
def certificate_model(base,u,v):
 product=u*v;estimate=(base-(u>>16)*(v>>16))&MASK
 exact=(base-(product>>32)-bool(product&MASK))&MASK
 fast=bool((estimate&0x7fffffff)>>17)
 negative=bool(exact&(1<<31))
 cross=((u>>16)*(v&65535)+(u&65535)*(v>>16))>MASK
 saving=12+3*cross if fast else -7 if negative else -8
 return dict(base=base,u=u,v=v,estimate=estimate,exact=exact,fast=fast,negative=negative,cross_overflow=cross)
def reciprocal_trace(m,label,root=True):
 image=division_images['candidate'if label=='candidate'else'control'];candidate=label=='candidate'
 data=dict(calls=[],seeds=[],first=[],before_second=[],after_second=[],after_y_residual=[],half_normalization=[],pack=[],zero_yL=[],certificates=[],entry_sp=[])
 def entry(uc,pc,unused,user):
  a=uc.reg_read(UC_ARM_REG_R0)|(uc.reg_read(UC_ARM_REG_R1)<<32)
  b=uc.reg_read(UC_ARM_REG_R2)|(uc.reg_read(UC_ARM_REG_R3)<<32)
  assert a==bits(1.)
  if root:assert(uc.reg_read(UC_ARM_REG_LR)&~1)==0x1014e668+linked['root_call_relocation_offset']+4
  data['entry_sp'].append(uc.reg_read(UC_ARM_REG_SP));assert data['entry_sp'][-1]%8==0
  data['calls'].append(dict(numerator=f'{a:016X}',denominator=f'{b:016X}'))
 address=image.symbols['mk61_m0_reciprocal1']&~1;m.uc.hook_add(UC_HOOK_CODE,entry,begin=address,end=address)
 def seed(uc,pc,unused,user):
  assert uc.reg_read(UC_ARM_REG_SP)==data['entry_sp'][-1]-20
  d=uc.reg_read(UC_ARM_REG_R1);assert 65536<=d<131072;data['seeds'].append(d)
 address=image.symbols['mk61_m0_inline_seed_begin']&~1;m.uc.hook_add(UC_HOOK_CODE,seed,begin=address,end=address)
 for tag in ['mk61_m0_reciprocal1','mk61_m0_reciprocal1_sw']:
  def first(uc,pc,unused,user):
   assert uc.reg_read(UC_ARM_REG_R0)==0;data['first'].append(uc.reg_read(UC_ARM_REG_R6))
  def before_second(uc,pc,unused,user):
   assert uc.reg_read(UC_ARM_REG_R0)==0 and uc.reg_read(UC_ARM_REG_R4)==0
   data['before_second'].append(state(uc))
  def second(uc,pc,unused,user):
   if candidate:assert uc.reg_read(UC_ARM_REG_R4)==0
   else:assert uc.reg_read(UC_ARM_REG_R0)==0
   data['after_second'].append(state(uc))
  def after_residual(uc,pc,unused,user):
   assert uc.reg_read(UC_ARM_REG_R4)==0;data['after_y_residual'].append(state(uc))
  def half(uc,pc,unused,user):
   assert uc.reg_read(UC_ARM_REG_R4)==0;data['half_normalization'].append(0)
  def pack(uc,pc,unused,user):data['pack'].append(state(uc))
  def zero(uc,pc,unused,user):
   value=uc.reg_read(UC_ARM_REG_R4);assert value==0;data['zero_yL'].append(value)
  def begin(uc,pc,unused,user):
   assert uc.reg_read(UC_ARM_REG_R6)==0
   values=state(uc);model=certificate_model(uc.reg_read(UC_ARM_REG_R4),uc.reg_read(UC_ARM_REG_R2),uc.reg_read(UC_ARM_REG_R0))
   data['certificates'].append(dict(model,join=values,full=False,decision=None))
  def full(uc,pc,unused,user):
   row=data['certificates'][-1];assert not row['fast'];row['full']=True
  def up(uc,pc,unused,user):
   row=data['certificates'][-1];assert not row['negative'];row['decision']='up'
   if candidate:assert uc.reg_read(UC_ARM_REG_R6)==0
  def down(uc,pc,unused,user):
   row=data['certificates'][-1]
   if row['decision']is None:assert row['negative'];row['decision']='down'
   assert row['full']==(not row['fast'])
  callbacks=[('_first_product',first),('_before_second_product',before_second),('_after_second_product',second),('_after_y_residual',after_residual),('_half_normalization',half),('_pack_begin',pack),('_y_low_shift',zero),('_certificate_begin',begin),('_certificate_up',up),('_certificate_down',down),('_certificate_full',full)]
  for suffix,callback in callbacks:
   address=image.symbols[tag+suffix]&~1;m.uc.hook_add(UC_HOOK_CODE,callback,begin=address,end=address)
 return data
def clear(data):
 for values in data.values():values.clear()
def projection(values,dead):
 return dict(registers=[v for i,v in enumerate(values['registers'])if i not in dead],frame28=values['frame28'])
def equivalent(parent,candidate):
 for name in ['calls','seeds','first','before_second','after_y_residual','half_normalization','zero_yL','entry_sp','certificates']:assert parent[name]==candidate[name],(name,parent[name],candidate[name])
 for name,dead in [('after_second',{0,4}),('pack',{3,6})]:
  assert len(parent[name])==len(candidate[name])
  for p,c in zip(parent[name],candidate[name]):assert projection(p,dead)==projection(c,dead),(name,p,c)
def saving(data):
 return len(data['first'])+len(data['half_normalization'])+sum(r['fast']and r['decision']=='up'for r in data['certificates'])
def public_trace(data):
 return dict(reciprocal_calls=list(data['calls']),software_seed_divisors=list(data['seeds']),first_product_reciprocals=list(data['first']),
             remainder_certificates=[{k:v for k,v in r.items()if k!='join'}for r in data['certificates']],removed_zero_operations=dict(first_product_calls=len(data['first']),half_normalization_calls=len(data['half_normalization']),fast_round_up_calls=sum(r['fast']and r['decision']=='up'for r in data['certificates'])))
