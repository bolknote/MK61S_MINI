"""Actual bare Thumb code versus exact integer interval endpoints, no ROM/models."""
from pathlib import Path
from collections import Counter
import json, math, random, struct, sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
sys.path[:0]=[str(ROOT/'.build/m0-float-fma-qualification-20261023/support'),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_SP,UC_ARM_REG_R12,UC_ARM_REG_XPSR

m=Machine(W/'unit.elf',True)
assert not m.rom_models and not m.rom_initializers
section=m.elf.named_sections['.unit'];lo,hi=section[3],section[3]+section[5]
pointerA,pointerB=SP-512,SP-544
active={};minsp={};costs={};calls=0
def hook(uc,pc,size,user):
 assert lo<=pc<hi,hex(pc)
 if pc==active['entry']:
  uc.reg_write(UC_ARM_REG_XPSR,0x01000000|(active['flags']<<28))
  uc.reg_write(UC_ARM_REG_R12,active['r12'])
 minsp[active['name']]=min(minsp.get(active['name'],SP),uc.reg_read(UC_ARM_REG_SP))
m.uc.hook_add(UC_HOOK_CODE,hook)
def write(uc,access,address,size,value,user):
 assert SP-256<=address and address+size<=SP or pointerA<=address and address+size<=pointerA+20,(hex(address),size)
m.uc.hook_add(UC_HOOK_MEM_WRITE,write)
rng=random.Random(0x614080025);M32=(1<<32)-1;M80=(1<<80)-1
def pack(a,e,r):return struct.pack('<IIIiI',(a>>16)&M32,a>>48,a&65535,e,r)
def unpack(data):
 h0,h1,l,e,r=struct.unpack('<IIIiI',data)
 assert l<65536 and h1>>31
 return ((h1<<32)|h0)<<16|l,e,r
def call(name,a,b=0):
 global calls
 active.update(name=name,entry=m.elf.symbols[name]&~1,flags=calls&15,r12=rng.getrandbits(32))
 result,_,cost=m.call(name,a,b,count=True);calls+=1
 costs.setdefault(name,Counter())[cost]+=1
 return result
edges=[0,1,65535,65536,0x7fffffff,0x80000000,M32]
for a in edges:
 for b in edges:
  assert call('mk61_m0_bound80_wide32',a|(b<<32))==a*b
for i in range(1024):
 a,b=rng.getrandbits(32),rng.getrandbits(32)
 assert call('mk61_m0_bound80_wide32',a|(b<<32))==a*b

def random_value(i):
 a=(1<<79)|rng.getrandbits(79)
 if i%7==0:a&=~65535
 return a,rng.randrange(-1024,1025),rng.choice([0,1,2,16,1<<18,rng.randrange(1<<20)])
square_cases=[random_value(i) for i in range(6000)]
threshold=math.isqrt(1<<159)
for a in [1<<79,(1<<79)+1,M80-1,M80,*[threshold+d for d in range(-16,17)]]:
 for r in [0,1,16,(1<<20)-1]:square_cases.append((a,0,r))
for i,(a,e,r) in enumerate(square_cases):
 if i%2048==0:print('b80-square',i,'/',len(square_cases),flush=True)
 m.uc.mem_write(pointerA,pack(a,e,r));call('mk61_m0_bound80_square',pointerA|(rng.getrandbits(32)<<32),rng.getrandbits(64))
 out,oe,er=unpack(bytes(m.uc.mem_read(pointerA,20)));shift=79+oe-2*e
 assert shift in [79,80]
 assert (out-er)<<shift <= (a-r)**2
 assert (out+er)<<shift >= (a+r)**2

multiply_cases=[]
for i in range(6000):
 a,e,r=random_value(i);b,f,s=random_value(i+1)
 if i%3==0:
  b=(1<<159)//a+rng.choice([-1,0,1])
  if not (1<<79)<=b<=M80:b=(1<<79)|rng.getrandbits(79)
 multiply_cases.append((a,e,r,b,f,s))
for i,(a,e,r,b,f,s) in enumerate(multiply_cases):
 if i%2048==0:print('b80-multiply',i,'/',len(multiply_cases),flush=True)
 m.uc.mem_write(pointerA,pack(a,e,r));m.uc.mem_write(pointerB,pack(b,f,s))
 call('mk61_m0_bound80_multiply',pointerA|(pointerB<<32),rng.getrandbits(64))
 out,oe,er=unpack(bytes(m.uc.mem_read(pointerA,20)));shift=79+oe-e-f
 assert shift in [79,80]
 assert (out-er)<<shift <= (a-r)*(b-s)
 assert (out+er)<<shift >= (a+r)*(b+s)
 assert bytes(m.uc.mem_read(pointerB,20))==pack(b,f,s)

decisions=Counter()
for i in range(6000):
 if i%2048==0:print('b80-compare',i,'/6000',flush=True)
 a,e,r=random_value(i);b,f,s=random_value(i+1);f=e+rng.choice([-3,-2,-1,0,0,0,0,1,2,3])
 if i%2==0:
  b=a+rng.choice([0,1,-1,65535,-65535,r+s,r+s+1,-r-s-1])
  if not (1<<79)<=b<=M80:b=a
 dataA,dataB=pack(a,e,r),pack(b,f,s)
 m.uc.mem_write(pointerA,dataA);m.uc.mem_write(pointerB,dataB)
 side=call('mk61_m0_bound80_compare',pointerA|(pointerB<<32),rng.getrandbits(64))&M32
 side=side if side<1<<31 else side-(1<<32)
 assert side in [-1,0,1]
 assert bytes(m.uc.mem_read(pointerA,20))==dataA and bytes(m.uc.mem_read(pointerB,20))==dataB
 base=min(e,f)
 if side>0:assert (a-r)<<(e-base) > (b+s)<<(f-base)
 if side<0:assert (a+r)<<(e-base) < (b-s)<<(f-base)
 decisions[side]+=1

out=dict(status='PASS_EXACT_INTEGER_INTERVAL_ENDPOINTS_BARE_BOUND80_KERNELS',actual_ARM_calls=calls,
 square_cases=len(square_cases),multiply_cases=len(multiply_cases),compare_cases=6000,
 wide32_cases=49+1024,all16_NZCV_and_noisy_volatiles=True,PCS_SP_PC_boundedwrites_checked=True,
 square_and_multiply_enclose_both_exact_real_input_interval_endpoints=True,
 compare_nonzero_sign_always_proved_from_exact_endpoints=True,
 comparison_decisions=dict(decisions),cost_histograms={n:dict(c) for n,c in costs.items()},
 observed_frames={n:SP-s for n,s in minsp.items()},firmware_ROM_or_arithmetic_mocks_mapped=False,
 public_MPFR_or_Qfplib_qualification=False,hardware_accessed=False)
(W/'unit-proof.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
