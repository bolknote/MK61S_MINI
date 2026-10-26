from pathlib import Path
from collections import Counter
import hashlib,json,random,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
sys.path[:0]=[str(ROOT/'.build/m0-float-fma-qualification-20261023/support'),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_XPSR,UC_ARM_REG_R12,UC_ARM_REG_SP
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
bare=ElfImage(W/'small-products-unit.elf');public=ElfImage(W/'candidate.elf')
names=['mk61_m0_exp_small_product64','mk61_m0_exp_small_product48','mk61_m0_exp_small_square48']
def code(im,name):
 a=im.symbols[name]&~1
 s=next(s for s in im.named_sections.values() if s[3]<=a<s[3]+s[5])
 return im.bytes_at(s)[a-s[3]:a-s[3]+im.sizes[name]]
for name in names:assert code(bare,name)==code(public,name),name
m=Machine(W/'small-products-unit.elf',True)
state={'entry':0,'end':0,'flags':0};lowest=SP;costs={n:Counter() for n in names}
def audit(uc,pc,size,user):
 global lowest
 assert state['entry']<=pc<state['end']
 if pc==state['entry']:
  uc.reg_write(UC_ARM_REG_XPSR,0x01000000|(state['flags']<<28))
  uc.reg_write(UC_ARM_REG_R12,0xBAD0F00D^state['flags'])
 sp=uc.reg_read(UC_ARM_REG_SP);assert not sp&3
 lowest=min(lowest,sp)
m.uc.hook_add(UC_HOOK_CODE,audit)
calls=0
def call(name,a,b):
 global calls
 state['entry']=bare.symbols[name]&~1;state['end']=state['entry']+bare.sizes[name]
 got,_,cost=m.call(name,a,b,count=True);calls+=1;costs[name][cost]+=1
 return got
def retained(a,b,minimum):
 return sum(((a>>(16*i))&65535)*((b>>(16*j))&65535)<<(16*(i+j)) for i in range(3) for j in range(4) if i+j>=minimum)
def products(a,b):
 p=retained(a,b,3);full=a*b
 q=call(names[0],a,b);assert q==(p+(1<<63))>>64
 assert abs((q<<64)-full)<(7<<63)+(1<<49)
 p=retained(a,b,2)
 q=call(names[1],a,b);assert q==p>>48
 assert 0<=full-(q<<48)<3*(1<<48)
acorners={0,(1<<48)-1};bcorners={0,(1<<58)-1}
for bit in range(49):
 for step in (-1,0,1):
  a=(1<<bit)+step
  if 0<=a<1<<48:acorners.add(a)
for bit in range(59):
 for step in (-1,0,1):
  b=(1<<bit)+step
  if 0<=b<1<<58:bcorners.add(b)
pairs={(a,b) for a in acorners for b in bcorners}
rng=random.Random(0x48E64A79)
for _ in range(16384):pairs.add((rng.getrandbits(48),rng.getrandbits(58)))
for i,(a,b) in enumerate(sorted(pairs)):
 if i%16384==0:print('product-pairs',i,'/',len(pairs),flush=True)
 products(a,b)
squarejobs={(a,shift) for a in acorners for shift in range(38,59)}
for _ in range(16384):squarejobs.add((rng.getrandbits(48),rng.randrange(38,59)))
for a,shift in sorted(squarejobs):assert call(names[2],a,shift)==(a*a)>>shift
chosen=sorted(pairs)
for flags in range(16):
 state['flags']=flags
 for i in range(64):
  a,b=chosen[(i*1069)%len(chosen)];products(a,b)
  shift=38+i%21;assert call(names[2],a,shift)==(a*a)>>shift
assert SP-lowest==36
assert all(len(c)==1 for c in costs.values())
out=dict(status='PASS_LITERAL6TERM_HIGH_9TERM_MIDDLE_PRODUCTS_AND6MUL_SQUARE_INTEGER_ORACLES',
 bare_ELF_sha256=sha(W/'small-products-unit.elf'),candidate_ELF_sha256=sha(W/'candidate.elf'),
 product_pairs=len(pairs),square_shift_pairs=len(squarejobs),all16NZCV_extra_ARM_calls=16*64*3,
 qualified_fresh_ARM_calls=calls,instruction_counts={n:dict(c) for n,c in costs.items()},
 scalar_return_integer_oracles_wrong=0,all_Callee_saved_SP_PC_bounded_writes_checked=True,
 stack_frame_bytes=36,actual_public_function_bytes_identical_to_units=True,
 function_bytes_sha256={n:hashlib.sha256(code(public,n)).hexdigest() for n in names},
 product64_domain_a48_b58=True,product48_domain_a48_b58=True,square_domain_a48_shift38to58=True,
 no_ROM_firmware_external_calls_mocks_or_SIO=True,actual_MPFR_calls=0,hardware_accessed=False)
(W/'small-unit-proof.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
