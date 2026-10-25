"""All flag combinations at both sign boundaries, plus real ARM random cases."""
from pathlib import Path
from collections import Counter
import gzip,hashlib,itertools,json,random,sys,time
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
sys.path[:0]=[str(ROOT/'.build/m0-float-fma-qualification-20261023/support'),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R1,UC_ARM_REG_R12,UC_ARM_REG_XPSR,UC_ARM_REG_SP
machines={n:Machine(W/(n+'.elf'),True)for n in ['control','candidate']};active={};rng=random.Random(0x614CE272);MASK=(1<<32)-1
for label,m in machines.items():
 assert not m.rom_models and not m.rom_initializers
 start=m.elf.symbols['unit_certificate_begin']&~1
 def entry(uc,pc,unused,user):
  uc.reg_write(UC_ARM_REG_XPSR,0x01000000|(active['flags']<<28));uc.reg_write(UC_ARM_REG_R1,active['r1']);uc.reg_write(UC_ARM_REG_R12,active['r12'])
 m.uc.hook_add(UC_HOOK_CODE,entry,begin=start,end=start)
 def write(uc,access,address,size,value,user):assert SP-20<=address<address+size<=SP
 m.uc.hook_add(UC_HOOK_MEM_WRITE,write)
values=[0,1,2,0xffff,0x10000,0x7fffffff,0x80000000,0xffff0000,0xfffffffe,0xffffffff]
boundary=[0,1,131070,131071,131072,131073,0x7fffffff,0x80000000,0x80000001,0x8001fffe,0x8001ffff,0x80020000,MASK]
tests=[]
for u,v in itertools.product(values,repeat=2):
 d=(u>>16)*(v>>16)
 for estimate in boundary:
  for flags in range(16):tests.append(((estimate+d)&MASK,u,v,flags,'sign_boundaries_all16'))
for _ in range(80000):tests.append((rng.getrandbits(32),rng.getrandbits(32),rng.getrandbits(32),rng.randrange(16),'random'))
costs={n:Counter()for n in machines};deltas=Counter();classes=Counter();t=time.monotonic()
with gzip.GzipFile(filename=str(W/'unit-records.jsonl.gz'),mode='wb',mtime=0)as stream:
 for i,(base,u,v,flags,group)in enumerate(tests):
  if i%8192==0:print('remainder-unit',i,'/',len(tests),round(time.monotonic()-t,1),flush=True)
  product=u*v;exact=(base-(product>>32)-bool(product&MASK))&MASK
  expected=MASK if exact&(1<<31)else 1 if exact else 0
  estimate=(base-(u>>16)*(v>>16))&MASK;certified=bool((estimate&0x7fffffff)>>17)
  active.update(flags=flags,r1=rng.getrandbits(32),r12=rng.getrandbits(32));counts={}
  for label,m in machines.items():
   got,_,count=m.call('unit_remainder_sign',base|(u<<32),v|(rng.getrandbits(32)<<32),count=True)
   assert got&MASK==expected,(i,label,hex(base),hex(u),hex(v),hex(got),hex(exact))
   assert m.uc.reg_read(UC_ARM_REG_R12)==active['r12']
   assert m.uc.reg_read(UC_ARM_REG_R1)==active['r1']
   costs[label][count]+=1;counts[label]=count
  deltas[counts['candidate']-counts['control']]+=1;classes['certified'if certified else'fallback']+=1
  stream.write((json.dumps(dict(base=base,u=u,v=v,NZCV=flags,expected=expected,certified=certified,instructions=counts,group=group),separators=(',',':'))+'\n').encode())
out=dict(status='PASS_ACTUAL_ARM_EXACT_REMAINDER_SIGN_ALL_FLAGS_AND_BOUNDARIES',tests=len(tests),actual_ARM_calls=2*len(tests),
 all_signs_equal_exact64bit_product_model=True,all16_NZCV_and_noisy_live_R1_R12_checked=True,PCS_SP_PC_and_only20B_wrapper_stack_writes_checked=True,
 classes=dict(classes),cost_histograms={n:dict(sorted(v.items()))for n,v in costs.items()},delta_histogram=dict(sorted(deltas.items())),
 unit_sign_wrapper_costs_not_public_division_claim=True,elapsed_seconds=time.monotonic()-t,hardware_accessed=False)
(W/'unit-proof.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
