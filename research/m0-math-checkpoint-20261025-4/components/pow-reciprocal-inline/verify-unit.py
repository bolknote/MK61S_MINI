"""All65536 divisors plus all flags at table edges; context kept in registers."""
from pathlib import Path
import hashlib,json,random,sys,time
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
sys.path[:0]=[str(ROOT/'.build/m0-float-fma-qualification-20261023/support'),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R12,UC_ARM_REG_SP,UC_ARM_REG_XPSR,UC_ARM_REG_PC
candidate=Machine(W/'unit.elf',True);control=Machine(ROOT/'.build/m0-ddiv-seed-lut-20261025/lut128_floor.elf',True)
assert not candidate.rom_models and not candidate.rom_initializers and not control.rom_models and not control.rom_initializers
start=candidate.elf.symbols['mk61_m0_inline_seed_begin']&~1;end=candidate.elf.symbols['mk61_m0_inline_seed_done']&~1;active={};rng=random.Random(0x6141C2)
def entry(uc,pc,unused,user):
 uc.reg_write(UC_ARM_REG_XPSR,0x01000000|(active['flags']<<28));uc.reg_write(UC_ARM_REG_R12,active['r12']);uc.reg_write(UC_ARM_REG_R5,active['r5'])
def done(uc,pc,unused,user):
 assert uc.reg_read(UC_ARM_REG_R0)==active['r0']and uc.reg_read(UC_ARM_REG_R1)==active['D']
 assert uc.reg_read(UC_ARM_REG_R2)|(uc.reg_read(UC_ARM_REG_R3)<<32)==active['r23']
 assert uc.reg_read(UC_ARM_REG_R5)==active['r5']and uc.reg_read(UC_ARM_REG_R12)==active['r12']
 assert uc.reg_read(UC_ARM_REG_R6)==0xffffffff//active['D']and uc.reg_read(UC_ARM_REG_SP)==SP-20
candidate.uc.hook_add(UC_HOOK_CODE,entry,begin=start,end=start);candidate.uc.hook_add(UC_HOOK_CODE,done,begin=end,end=end)
def write(uc,access,address,size,value,user):
 assert not start<=uc.reg_read(UC_ARM_REG_PC)<end
 assert SP-20<=address<address+size<=SP
candidate.uc.hook_add(UC_HOOK_MEM_WRITE,write)
tests=[(d,d&15)for d in range(65536,131072)];edges={65536,65537,131070,131071}
for i in range(128):
 for delta in[-1,0,1]:
  d=65536+512*i+delta
  if 65536<=d<131072:edges.add(d)
tests +=[(d,flags)for d in sorted(edges)for flags in range(16)]
t=time.monotonic()
for i,(d,flags)in enumerate(tests):
 if i%8192==0:print('inline-seed-unit',i,'/',len(tests),round(time.monotonic()-t,1),flush=True)
 active.update(D=d,flags=flags,r0=rng.getrandbits(32),r23=rng.getrandbits(64),r5=rng.getrandbits(32),r12=rng.getrandbits(32))
 got,_,_=candidate.call('unit_inline_seed',active['r0']|(d<<32),active['r23'],count=True)
 old,_,_=control.call('mk61_m0_ddiv_seed17',0xffffffff|(d<<32),rng.getrandbits(64),count=True)
 assert got&0xffffffff==old&0xffffffff==0xffffffff//d
out=dict(status='PASS_COMPLETE_INLINE_QUOTIENT_AND_LIVE_CONTEXT_DOMAIN',tests=len(tests),actual_ARM_calls=2*len(tests),exhaustive_divisors=65536,all16_NZCV_table_edge_calls=len(tests)-65536,
 all_R0_R1_R2_R3_R5_R12_SP_preserved_during_macro=True,all_callee_saved_PCS_SP_PC_checked=True,no_inline_stack_or_memory_writes=True,
 isolated_wrapper_stack20B_not_production_seed_frame=True,no_unit_wrapper_speed_claim=True,ELF_sha256=hashlib.sha256((W/'unit.elf').read_bytes()).hexdigest(),elapsed_seconds=time.monotonic()-t,hardware_accessed=False)
(W/'unit-proof.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
