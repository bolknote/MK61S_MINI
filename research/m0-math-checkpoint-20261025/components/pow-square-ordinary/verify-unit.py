"""Exact integer square oracle and live full106-bit product audit in ARM."""
from pathlib import Path
from collections import Counter
import hashlib,itertools,json,random,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path.insert(0,str(Q));sys.path.insert(0,str(Q/'support'))
from native_eabi_m0_arm_self_test import Machine,SP
from oracles import round_ratio
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R12
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
b=json.loads((W/'unit-build.json').read_text());assert sha(W/'unit.elf')==b['unit_ELF_sha256'];assert sha(W/'square.S')==b['square_source_sha256']
m=Machine(W/'unit.elf',True,stack_bytes=128);reads=[0];current=[None];traces=[];shifts=Counter();costs=[]
def audit(uc,address,size,user):
 raw=current[0];e=(raw>>52)&2047;sig=(raw&((1<<52)-1))|(1<<52)
 product=uc.reg_read(UC_ARM_REG_R12)|(uc.reg_read(UC_ARM_REG_R5)<<32)|(uc.reg_read(UC_ARM_REG_R6)<<64)|(uc.reg_read(UC_ARM_REG_R7)<<96)
 assert product==sig*sig,(hex(raw),hex(product),hex(sig*sig))
 k=(sig*sig).bit_length()-105;E=2*e-1023+k
 expected_shift=52+k if E>0 else 1076-2*e
 expected_bias=((E-1)<<20) if E>0 else 0
 assert 52<=expected_shift<=106
 assert uc.reg_read(UC_ARM_REG_R4)==expected_shift
 assert uc.reg_read(UC_ARM_REG_R3)==expected_bias
 shifts[expected_shift]+=1;traces.append(product)
m.uc.hook_add(UC_HOOK_CODE,audit,begin=int(b['product_audit_address'],16),end=int(b['product_audit_address'],16))
def sio(*unused):reads[0]+=1
m.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,sio,begin=0xd0000060,end=0xd000007b)
inputs=set()
fracs=(0,1,2,3,65535,65536,0xffffffff,0x100000000,(1<<51)-1,1<<51,(1<<52)-2,(1<<52)-1)
for e in range(2048):
 for f in fracs:
  for sign in (0,1<<63):inputs.add(sign|(e<<52)|f)
# Complete selected16-bit limb corner combinations, over every rounding
# word range and the finite normal endpoints.
limbs=(0,1,32767,32768,65534,65535)
for a0,a1,a2,a3 in itertools.product(limbs,limbs,limbs,(16,17,23,24,30,31)):
 sig=a0|(a1<<16)|(a2<<32)|(a3<<48)
 for e in (485,490,491,495,496,500,506,507,510,511,512,1022,1023,1533,1534):
  for sign in (0,1<<63):inputs.add(sign|(e<<52)|(sig-(1<<52)))
# Midpoint squares: odd significands with26 trailing zero bits can make
# an exact normal half cell at shift53. Test both signs and neighbors.
for odd in range((1<<26)+1,(1<<26)+4096,2):
 sig=odd<<26
 for offset in (-1,0,1):
  for e in (485,490,496,506,507,511,512,1023,1534):
   for sign in (0,1<<63):inputs.add(sign|(e<<52)|(sig+offset-(1<<52)))
rng=random.Random(0x5A9AE106)
for _ in range(32768):inputs.add(rng.getrandbits(64))
states=[struct.pack('<7I',0,0,0,0,0,0,1),struct.pack('<7I',17,3,17,3,5,2,3)]
digest=hashlib.sha256();calls=0;full_products=0;ties=0;branches=Counter()
for index,raw in enumerate(sorted(inputs)):
 if index%32768==0:print('progress',index,'/',len(inputs),flush=True)
 e=(raw>>52)&2047;f=raw&((1<<52)-1)
 if e==2047:expected=(raw|(1<<51)) if f else 0x7ff0000000000000
 else:
  sig=f|((1<<52) if e else 0);exponent=(e-1075) if e else -1074
  expected=round_ratio(sig*sig,1,2*exponent,64,False)
 if 485<=e<1535:
  sig=f|(1<<52);norm=(sig*sig).bit_length()-105;E=2*e-1023+norm;s=52+norm if E>0 else 1076-2*e
  ties+=int((sig*sig)&((1<<s)-1)==1<<(s-1))
  branches['product']+=1
 elif e<485:branches['zero']+=1
 else:branches['large']+=1
 current[0]=raw
 for state_index,state in enumerate(states):
  traces.clear();m.uc.mem_write(0xd0000060,state)
  profile=index%1021==0
  got,_,count=m.call('mk61_m0_pow_square_exact',raw,count=profile)
  assert got==expected,(hex(raw),hex(got),hex(expected))
  assert len(traces)==int(485<=e<1535)
  assert bytes(m.uc.mem_read(0xd0000060,28))==state
  if profile:costs.append(count)
  full_products+=len(traces);calls+=1
  digest.update(struct.pack('<QQB',raw,got,state_index))
assert calls==2*len(inputs) and reads[0]==0 and full_products
assert set(shifts)=={52,53,*range(54,107,2)}
out=dict(status='PASS_BARE_EXACT106_BIT_SQUARE_AND_IEEE_RNE_INTEGER_ORACLE',
 square_source_sha256=b['square_source_sha256'],public_ELF_sha256=b['public_ELF_sha256'],unit_ELF_sha256=b['unit_ELF_sha256'],
 unique_inputs=len(inputs),actual_ARM_calls=calls,full_product_trace_calls=full_products,
 every_traced_product_equals_exact_significand_square=True,every_traced_rounding_shift_and_bias_exact=True,
 shift_counts=dict(shifts),input_branches=dict(branches),exact_midpoint_input_count=ties,
 candidate_wrong=0,both_input_signs_all2048_exponents=True,
 SIO_accesses=reads[0],SIO_preserved_both_states=True,PCS_SP_bounded_writes_every_call=True,
 observed_stack_bytes=SP-m.stack_lowest,profiled_instruction_range=[min(costs),max(costs)],transcript_sha256=digest.hexdigest(),
 full_firmware_or_ROM_loaded=False,new_public_pow_calls=0,hardware_accessed=False,
 scope='Full input exponent partition, selected16-bit limb corners, exact normal half cells and neighbors, uniform full bits. Integer/carry/RNE oracle, not exhaustive2^64 input enumeration.')
(W/'unit-proof.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
