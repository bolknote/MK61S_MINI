"""Exhaustively execute the bare old/new seeds, every divisor and flag edges."""
from pathlib import Path
from collections import Counter
import gzip,hashlib,json,random,sys,time
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
sys.path[:0]=[str(ROOT/'.build/m0-float-fma-qualification-20261023/support'),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R12,UC_ARM_REG_XPSR,UC_ARM_REG_SP,UC_ARM_REG_R1
build=json.loads((W/'build.json').read_bytes())
machines={'control':Machine(ROOT/'.build/m0-ddiv-soft-seed17-20261025/seed17.elf',True)}
machines.update({n:Machine(W/(n+'.elf'),True)for n in build['variants']})
active={};rng=random.Random(0x614DD125);costs={n:Counter()for n in machines};deltas={n:Counter()for n in build['variants']}
for name,m in machines.items():
 assert not m.rom_models and not m.rom_initializers
 start=m.elf.symbols['mk61_m0_ddiv_seed17']&~1;size=m.elf.sizes['mk61_m0_ddiv_seed17']
 def code(uc,pc,unused,user,start=start,size=size):
  assert start<=pc<start+size and uc.reg_read(UC_ARM_REG_SP)==SP
  if pc==start:
   uc.reg_write(UC_ARM_REG_XPSR,0x01000000|(active['flags']<<28));uc.reg_write(UC_ARM_REG_R12,active['r12'])
 def write(*args):raise AssertionError('Seed must not write memory')
 m.uc.hook_add(UC_HOOK_CODE,code);m.uc.hook_add(UC_HOOK_MEM_WRITE,write)
tests=[(d,d&15)for d in range(65536,131072)]
edges={65536,65537,131070,131071}
for shift in [8,9,10,11]:
 for i in range(1<<(16-shift)):
  for delta in [-1,0,1]:
   d=65536+(i<<shift)+delta
   if 65536<=d<131072:edges.add(d)
tests +=[(d,flags)for d in sorted(edges)for flags in range(16)]
t=time.monotonic();calls=0
with gzip.GzipFile(filename=str(W/'unit-records.jsonl.gz'),mode='wb',mtime=0)as stream:
 for i,(d,flags)in enumerate(tests):
  if i%8192==0:print('seed-LUT',i,'/',len(tests),round(time.monotonic()-t,1),flush=True)
  active.update(flags=flags,r12=rng.getrandbits(32));values={}
  for name,m in machines.items():
   got,_,cost=m.call('mk61_m0_ddiv_seed17',0xffffffff|(d<<32),rng.getrandbits(64),count=True);calls+=1
   assert got&0xffffffff==0xffffffff//d,(name,d,got)
   assert m.uc.reg_read(UC_ARM_REG_R12)==active['r12']and m.uc.reg_read(UC_ARM_REG_R1)==d
   costs[name][cost]+=1;values[name]=cost
  for name in deltas:
   delta=values[name]-values['control'];deltas[name][delta]+=1
  stream.write((json.dumps(dict(D=d,NZCV=flags,quotient=0xffffffff//d,instructions=values),separators=(',',':'))+'\n').encode())
out=dict(status='PASS_ALL_EXACT_INTEGER_QUOTIENTS_R12_PCS_NZCV_AND_NO_WRITES',tests=len(tests),actual_ARM_calls=calls,
 exhaustive_divisors=65536,additional_all16_NZCV_edge_calls_per_variant=len(tests)-65536,
 cost_histograms={n:dict(sorted(c.items()))for n,c in costs.items()},parent_delta_histograms={n:dict(sorted(c.items()))for n,c in deltas.items()},
 code_and_allocated_sizes={n:dict(function_bytes=m.elf.sizes['mk61_m0_ddiv_seed17'],allocated_bytes=sum(s[5]for s in m.elf.sections if s[2]&2))for n,m in machines.items()},
 all_R1_R12_and_callee_saved_preserved=True,no_stack_or_memory_writes=True,
 original_control_exhaustive_reexecution_not_double_counted_with_old_seed66288=True,
 firmware_ROM_or_arithmetic_mocks_mapped=False,elapsed_seconds=time.monotonic()-t,hardware_accessed=False)
(W/'unit-proof.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
