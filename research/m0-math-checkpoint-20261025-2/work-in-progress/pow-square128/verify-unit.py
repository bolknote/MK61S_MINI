"""Compare actual kernels with old transform and exact integer model."""
from pathlib import Path
from collections import Counter
import json,math,random,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path[:0]=[str(Q/'support'),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_SP,UC_ARM_REG_XPSR,UC_ARM_REG_R12

MASK=(1<<64)-1;word=(1<<32)-1;pointer=SP-512
machines={n:Machine(W/('unit-'+n+'.elf'),True) for n in ['control','candidate']}
assert all(not m.rom_models and not m.rom_initializers for m in machines.values())
entry=machines['candidate'].elf.symbols['pow_integer128_square']&~1
helper=machines['candidate'].elf.symbols['pow_integer128_approx_high64']&~1
active={};minsp={n:SP for n in machines}
for label,m in machines.items():
 def init(uc,pc,size,user,label=label):
  if pc==entry:
   uc.reg_write(UC_ARM_REG_XPSR,0x01000000|(active['flags']<<28))
   uc.reg_write(UC_ARM_REG_R12,active['r12'])
  minsp[label]=min(minsp[label],uc.reg_read(UC_ARM_REG_SP))
  limit=machines[label].elf.sizes['pow_integer128_square']
  assert entry<=pc<entry+limit or helper<=pc<helper+94,hex(pc)
 m.uc.hook_add(UC_HOOK_CODE,init)
 def write(uc,access,address,size,value,user):
  assert SP-80<=address and address+size<=SP or pointer<=address and address+size<=pointer+24,(hex(address),size)
 m.uc.hook_add(UC_HOOK_MEM_WRITE,write)

def high32(a,b):return (a>>16)*(b>>16)+((a&65535)*(b>>16)>>16)+((a>>16)*(b&65535)>>16)
def approx(a,b):return ((a>>32)*(b>>32)+high32(a&word,b>>32)+high32(a>>32,b&word))&MASK
def model(h,l,e,r):
 p=h*h
 if l:p+=2*approx(l,h)
 p&=(1<<128)-1
 radius=(2*r+(16 if l else bool(r)))&word
 exponent=(2*e)&word
 upper=bool(p>>127)
 if upper:exponent=(exponent+1)&word
 else:p=(p<<1)&((1<<128)-1);radius=(radius<<1)&word
 return struct.pack('<QQII',p>>64,p&MASK,exponent,radius),upper

edges={0,1,MASK,1<<63,(1<<63)+1}
for k in range(65):
 edges.update(v for v in [(1<<k)-1,1<<k,(1<<k)+1] if 0<=v<=MASK)
threshold=math.isqrt(1<<127)
edges.update(threshold+d for d in range(-4,5))
rng=random.Random(0x614128025)
tests=[]
for h in sorted(edges):
 for l in [0,1,(1<<32)-1,1<<63,MASK]:
  for r in [0,1,2,0x7fffffff,0x80000000,word]:tests.append((h,l,rng.getrandbits(32),r,0))
for i in range(12000):
 h=rng.getrandbits(64)
 if i%3==0:h=((rng.getrandbits(52)|(1<<52))<<11)
 if i%5==0:h=((rng.getrandbits(52)|(1<<52))*2+1)<<10
 tests.append((h,0 if i&1 else rng.getrandbits(64),rng.getrandbits(32),rng.getrandbits(32),i&15))
for flags in range(16):
 for h in [1<<63,threshold-1,threshold,threshold+1,MASK]:
  for l in [0,1,MASK]:tests.append((h,l,word,word,flags))
hist=Counter();classes=Counter();class_costs={}
for i,(h,l,e,r,flags) in enumerate(tests):
 if i%2048==0:print('square128-unit',i,'/',len(tests),flush=True)
 expected,upper=model(h,l,e,r);data=struct.pack('<QQII',h,l,e,r);counts={}
 for label,m in machines.items():
  active.update(flags=flags,r12=rng.getrandbits(32));m.uc.mem_write(pointer,data)
  _,_,cost=m.call('pow_integer128_square',pointer|(rng.getrandbits(32)<<32),rng.getrandbits(64),count=True)
  got=bytes(m.uc.mem_read(pointer,24));assert got==expected,(i,label,(h,l,e,r),got.hex(),expected.hex())
  counts[label]=cost
 assert counts['candidate']<=counts['control'],(i,counts)
 cost_class=(bool(l),upper)
 if cost_class in class_costs:assert class_costs[cost_class]==counts,(i,class_costs,counts)
 class_costs[cost_class]=counts
 hist[counts['candidate']-counts['control']]+=1
 classes[bool(l),upper]+=1
out=dict(status='PASS_EXACT_INTEGER_MODEL_AND_OLD_KERNEL',tests=len(tests),actual_ARM_calls=2*len(tests),
 class_counts={str(k):v for k,v in classes.items()},class_costs={str(k):v for k,v in class_costs.items()},
 cost_delta_histogram=dict(hist),min_SP_frames={n:SP-v for n,v in minsp.items()},
 old_and_new_all24_output_bytes_identical=True,all16_NZCV_and_arbitrary_volatile_registers=True,
 PCS_SP_PC_and_bounded_struct_stack_writes_every_call=True,firmware_ROM_or_arithmetic_mocks_not_mapped=True,
 hardware_accessed=False)
(W/'unit-proof.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
