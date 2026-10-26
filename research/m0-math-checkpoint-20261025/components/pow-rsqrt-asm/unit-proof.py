"""Execute the same quotient macro on all512 seeds and broad uint32 numerators."""
import json,random,struct,sys
from collections import Counter
sys.dont_write_bytecode=True
from common import *
from unicorn import UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
assert sha(W/'unit.elf')==build['unit_ELF_sha256']
m=Machine(W/'unit.elf',True);accesses=[]
m.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,lambda uc,access,address,size,value,user:accesses.append((access,address,size)),begin=0xd0000000,end=0xd0000fff)
rng=random.Random(0xC004D1A7);records=bytearray();counts=Counter();under=Counter();unique=0
for index,b in enumerate(seeds):
 p,i=divmod(index,256);d=513+2*i;limit=(1<<32)//d
 nums={0,1,2,d-1,d,d+1,(1<<32)-1,(1<<32)-2,(1<<32)-d}
 quotients={0,1,2,limit-1,limit,*[rng.randrange(limit+1) for _ in range(32)]}
 for q in quotients:
  nums.update(n for delta in (-1,0,1) if 0<=(n:=q*d+delta)<(1<<32))
 nums.update(rng.getrandbits(32) for _ in range(32))
 r=((b>>16)**2+(((b&65535)*(b>>16))>>15))>>(9-p)
 for n in sorted(nums):
  q=n//d;unique+=1;under[q-(n*r>>32)]+=1
  records.extend(struct.pack('<5I',n,d,b,p,q))
  for state in states.values():
   m.uc.mem_write(0xd0000060,state)
   got,_,cost=m.call('mk61_m0_pow_center_quotient',n|(d<<32),b|(p<<32),count=True)
   assert got&0xffffffff==q,(n,d,b,p,hex(got),q)
   assert bytes(m.uc.mem_read(0xd0000060,28))==state
   counts[cost]+=1
 assert not accesses
 if index%128==0:print('seed progress',index,'/',len(seeds),'cases',unique,flush=True)
assert set(under)=={0,1,2}
(W/'unit-vectors.bin').write_bytes(records)
out={'status':'PASS_QUOTIENT_ARM_ALL512_SEEDS_AND_UINT32_BOUNDARIES','unit_ELF_sha256':sha(W/'unit.elf'),'rsqrt_source_sha256':sha(W/'rsqrt.S'),'certificate_sha256':sha(W/'certificate.json'),'seed_rows':512,'distinct_numerator_seed_pairs':unique,'fresh_ARM_calls':unique*2,'exact_integer_oracle_every_case':True,'instruction_counts':dict(sorted(counts.items())),'initial_quotient_underestimates':dict(sorted(under.items())),'SIO_reads_or_writes':len(accesses),'stack_bytes':SP-m.stack_lowest,'PCS_SP_boundedwrites_each_call':True,'vectors_sha256':sha(W/'unit-vectors.bin'),'no_firmware_ROM_or_mock':True,'hardware_accessed':False}
(W/'unit-proof.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
