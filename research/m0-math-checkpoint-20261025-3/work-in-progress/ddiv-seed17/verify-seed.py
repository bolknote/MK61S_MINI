from pathlib import Path
from collections import Counter
import hashlib,json,random,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
sys.path[:0]=[str(ROOT/'.build/m0-float-fma-qualification-20261023/support'),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R12,UC_ARM_REG_XPSR,UC_ARM_REG_SP
m=Machine(W/'seed17.elf',True);assert not m.rom_models and not m.rom_initializers
start=m.elf.symbols['mk61_m0_ddiv_seed17']&~1;size=m.elf.sizes['mk61_m0_ddiv_seed17'];active={}
def hook(uc,pc,size_,user):
 assert start<=pc<start+size and uc.reg_read(UC_ARM_REG_SP)==SP
 if pc==start:
  uc.reg_write(UC_ARM_REG_XPSR,0x01000000|(active['NZCV']<<28));uc.reg_write(UC_ARM_REG_R12,active['r12'])
m.uc.hook_add(UC_HOOK_CODE,hook)
def writes(*args):raise AssertionError('Seed must not write any memory')
m.uc.hook_add(UC_HOOK_MEM_WRITE,writes)
rng=random.Random(0x614D17025);tests=[(d,d&15)for d in range(1<<16,1<<17)]
edges={1<<16,(1<<16)+1,(1<<17)-2,(1<<17)-1}
for k in range(16):
 for delta in [-1,0,1]:
  d=(1<<16)+(1<<k)+delta
  if (1<<16)<=d<(1<<17):edges.add(d)
tests +=[(d,flags)for d in sorted(edges)for flags in range(16)]
costs=Counter()
for i,(d,flags)in enumerate(tests):
 if i%8192==0:print('seed17',i,'/',len(tests),flush=True)
 active.update(NZCV=flags,r12=rng.getrandbits(32))
 got,_,cost=m.call('mk61_m0_ddiv_seed17',0xffffffff|(d<<32),rng.getrandbits(64),count=True)
 assert got&0xffffffff==0xffffffff//d,(d,hex(got))
 assert m.uc.reg_read(UC_ARM_REG_R12)==active['r12']
 costs[cost]+=1
out=dict(status='PASS_ALL65536_DIVISORS_EXACT_INTEGER_QUOTIENT_R12_PCS_NZCV',actual_ARM_calls=len(tests),
 exhaustive_divisors=65536,extra_all16_NZCV_edge_calls=len(tests)-65536,code_bytes=size,
 cost_histogram=dict(sorted(costs.items())),R12_preserved_every_call=True,
 PCS_SP_PC_checked=True,no_stack_or_memory_writes=True,firmware_ROM_or_arithmetic_mocks_mapped=False,
 ELF_sha256=hashlib.sha256((W/'seed17.elf').read_bytes()).hexdigest(),hardware_accessed=False)
(W/'seed-proof.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
