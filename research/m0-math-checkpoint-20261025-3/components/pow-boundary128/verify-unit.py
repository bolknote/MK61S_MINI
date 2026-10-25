"""Bare old/new boundary decisions and exact mathematical interval endpoints."""
from pathlib import Path
from collections import Counter
import hashlib,json,random,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];BASE=ROOT/'.build/m0-pow-square128-r2-20261025'
sys.path[:0]=[str(ROOT/'.build/m0-float-fma-qualification-20261023/support'),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_SP,UC_ARM_REG_R12,UC_ARM_REG_XPSR,UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_LR

machines={name:Machine(W/(name+'.elf'),True)for name in ['control','candidate']}
helpers=ElfImage(W/'unit-helpers.elf');square=ElfImage(BASE/'unit-candidate.elf')
pointer=SP-640;active={};frames={name:SP for name in machines};events={name:[]for name in machines}
for label,m in machines.items():
 assert not m.rom_models and not m.rom_initializers
 helpers.load(m.uc);square.load(m.uc);m.elf.symbols['unit_boundary']=0x10150001
 allowed=[(0x100f9268,490),(0x1014f720,372),(0x100f9c9c,232),(0x1014e668,94),(0x10150000,532 if label=='control' else 8)]
 start=0x10150000;length=532
 if label=='candidate':
  start=m.elf.symbols['mk61_m0_boundary128']&~1;length=m.elf.sizes['mk61_m0_boundary128'];allowed.append((start,length))
 def hook(uc,pc,size,user,label=label,allowed=allowed,start=start,length=length):
  assert any(a<=pc<a+n for a,n in allowed),hex(pc)
  if pc==0x10150000:
   uc.reg_write(UC_ARM_REG_XPSR,0x01000000|(active['flags']<<28));uc.reg_write(UC_ARM_REG_R12,active['r12'])
  frames[label]=min(frames[label],uc.reg_read(UC_ARM_REG_SP))
  if pc in [0x100f9268,0x1014f720] and start<=(uc.reg_read(UC_ARM_REG_LR)&~1)<start+length:
   a=uc.reg_read(UC_ARM_REG_R0);b=uc.reg_read(UC_ARM_REG_R1)
   events[label].append((pc,bytes(uc.mem_read(a,24)).hex(),bytes(uc.mem_read(b,24)).hex()))
 m.uc.hook_add(UC_HOOK_CODE,hook)
 def write(uc,access,address,size,value,user):
  assert SP-384<=address and address+size<=SP,(hex(address),size)
 m.uc.hook_add(UC_HOOK_MEM_WRITE,write)

def compare_dyadic(a,e,b,f):
 base=min(e,f);a<<=e-base;b<<=f-base
 return (a>b)-(a<b)
rng=random.Random(0x614128B025);M64=(1<<64)-1;cases=[]
for i in range(3000):
 ce=rng.choice([-1022,-1000,-20,-1,0,1,20,1000,1023]);fraction=rng.getrandbits(52)
 cell=((ce+1023)<<52)|fraction
 if cell>=0x7fefffffffffffff:cell=0x7feffffffffffffe
 d=1<<rng.randrange(8);inverse=i&1
 coefficient=(((cell&((1<<52)-1))|(1<<52))<<1)+1
 mid=coefficient**d;scale=((cell>>52)-1023-53)*d;me=mid.bit_length()-1+scale
 radius=rng.choice([0,1,16,255,65535,1<<20])
 if i%3:
  if inverse:
   e=-me-1;shift=127-e-scale;center=(1<<shift)//mid
  else:
   e=me;shift=127+scale-e;center=mid<<shift if shift>=0 else mid>>(-shift)
  center+=rng.choice([-(1<<30),-radius-1,-1,0,1,radius+1,1<<30])
 else:center=(1<<127)|rng.getrandbits(127);e=rng.randrange(-2048,2049)
 assert (1<<127)<=center<(1<<128)
 cases.append((center,e,radius,d,inverse,cell,mid,scale))
hist=Counter();decisions=Counter();increases=0
for i,(center,e,radius,d,inverse,cell,mid,scale)in enumerate(cases):
 if i%512==0:print('exact-boundary-unit',i,'/',len(cases),flush=True)
 data=struct.pack('<QQiI',center>>64,center&M64,e,radius);counts={};values={}
 for label,m in machines.items():
  active.update(flags=i&15,r12=rng.getrandbits(32));events[label].clear()
  m.uc.mem_write(pointer,data);m.uc.mem_write(SP,struct.pack('<Q',cell))
  value,_,cost=m.call('unit_boundary',pointer|(d<<32),inverse|(rng.getrandbits(32)<<32),count=True)
  value&=0xffffffff;value=value if value<1<<31 else value-(1<<32)
  assert value in [-1,0,1]
  assert bytes(m.uc.mem_read(pointer,24))==data
  assert bytes(m.uc.mem_read(SP,8))==struct.pack('<Q',cell)
  values[label]=value;counts[label]=cost
 assert values['control']==values['candidate'],(i,values)
 assert events['control']==events['candidate'],(i,events)
 side=values['candidate'];decisions[side]+=1
 if side:
  low,high=center-radius,center+radius
  if not inverse:
   assert compare_dyadic(low,e-127,mid,scale)>0 if side>0 else compare_dyadic(high,e-127,mid,scale)<0
  else:
   assert compare_dyadic(high*mid,e-127+scale,1,0)<0 if side>0 else compare_dyadic(low*mid,e-127+scale,1,0)>0
 delta=counts['candidate']-counts['control'];hist[delta]+=1;increases+=delta>0
out=dict(status='PASS_BARE_EXACT_BOUNDARY128_OLD_NEW_AND_MATHEMATICAL_ENDPOINTS',cases=len(cases),actual_ARM_calls=2*len(cases),
 all24_midpoint_operand_bytes_identical=True,all_returned_sides_identical=True,
 all_nonzero_sides_proved_against_exact_dyadic_midpoint_and_power_interval=True,
 all16_NZCV_noisy_R3_R12_PCS_SP_PC_and_boundedwrites=True,
 preserved_input_P128_and_stack_cell_every_call=True,denominators=[1,2,4,8,16,32,64,128],
 decisions=dict(decisions),cost_delta_histogram=dict(sorted(hist.items())),parent_cost_increase_cases=increases,
 observed_frames={n:SP-f for n,f in frames.items()},firmware_ROM_or_arithmetic_mocks_mapped=False,hardware_accessed=False)
(W/'unit-proof.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
