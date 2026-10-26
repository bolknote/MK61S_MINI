"""Every seed divisor under every incoming flag combination on actual Thumb."""
from pathlib import Path
from collections import Counter
import gzip,hashlib,json,random,sys,time
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
sys.path[:0]=[str(ROOT/'.build/m0-float-fma-qualification-20261023/support'),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R12,UC_ARM_REG_SP,UC_ARM_REG_XPSR,UC_ARM_REG_PC
assert not(W/'unit-proof.json').exists()
machines={label:Machine(W/(label+'.elf'),True)for label in ['control','candidate']};active={};rng=random.Random(0x6141B3)
models=json.loads((W/'integer-model.json').read_bytes())['rows']
for label,m in machines.items():
 assert not m.rom_models and not m.rom_initializers
 start=m.elf.symbols['mk61_m0_inline_seed_begin']&~1;end=m.elf.symbols['mk61_m0_inline_seed_done']&~1
 def entry(uc,pc,unused,user):
  assert uc.reg_read(UC_ARM_REG_R0)==0
  uc.reg_write(UC_ARM_REG_XPSR,0x01000000|(active['flags']<<28));uc.reg_write(UC_ARM_REG_R12,active['r12']);uc.reg_write(UC_ARM_REG_R5,active['r5'])
 def done(uc,pc,unused,user,label=label):
  assert uc.reg_read(UC_ARM_REG_R0)==0 and uc.reg_read(UC_ARM_REG_R1)==active['D']
  assert uc.reg_read(UC_ARM_REG_R2)|(uc.reg_read(UC_ARM_REG_R3)<<32)==active['r23']
  assert uc.reg_read(UC_ARM_REG_R5)==active['r5']and uc.reg_read(UC_ARM_REG_R12)==active['r12']
  assert uc.reg_read(UC_ARM_REG_R6)==0xffffffff//active['D']and uc.reg_read(UC_ARM_REG_SP)==SP-20
  assert uc.reg_read(UC_ARM_REG_R7)==active['model'][label+'_residual']&0xffffffff
 m.uc.hook_add(UC_HOOK_CODE,entry,begin=start,end=start);m.uc.hook_add(UC_HOOK_CODE,done,begin=end,end=end)
 def write(uc,access,address,size,value,user,start=start,end=end):
  assert not start<=uc.reg_read(UC_ARM_REG_PC)<end
  assert SP-20<=address<address+size<=SP
 m.uc.hook_add(UC_HOOK_MEM_WRITE,write)
hist=Counter();costs={label:Counter()for label in machines};tests=0;t=time.monotonic()
with gzip.GzipFile(filename=str(W/'unit-records.jsonl.gz'),mode='wb',mtime=0)as output:
 for model in models:
  D=model['D'];counts={label:[]for label in machines}
  for flags in range(16):
   active.update(D=D,flags=flags,r23=rng.getrandbits(64),r5=rng.getrandbits(32),r12=rng.getrandbits(32),model=model);tests+=1
   for label,m in machines.items():
    got,_,cost=m.call('unit_inline_seed',D<<32,active['r23'],count=True)
    assert got&0xffffffff==0xffffffff//D;counts[label].append(cost);costs[label][cost]+=1
   delta=counts['candidate'][-1]-counts['control'][-1];assert delta==(-3 if model['error']==3 else 0),(D,flags,delta);hist[delta]+=1
  output.write((json.dumps(dict(model,NZCV=list(range(16)),instructions=counts),separators=(',',':'))+'\n').encode())
  if D%2048==0:print('bound3-seed-unit',D-65535,'/65536',round(time.monotonic()-t,1),flush=True)
assert tests==1048576
out=dict(status='PASS_ALL65536_SEEDS_ALL16_NZCV_AND_LIVE_CONTEXT',tests=tests,actual_ARM_calls=2*tests,exhaustive_divisors=65536,all16_flags_for_every_divisor=True,
 private_R0_zero_required_and_preserved=True,all_R1_R2_R3_R5_R12_SP_preserved=True,exact_floor_quotient_identical=True,
 third_step_R7_residual_difference_matches_dead_value_model=True,PCS_SP_PC_and_only20B_wrapper_writes_checked=True,no_inline_memory_writes=True,
 instruction_delta_histogram=dict(sorted(hist.items())),cost_histograms={label:dict(sorted(v.items()))for label,v in costs.items()},
 no_parent_cost_increases=True,unit_wrapper_costs_not_production_division_claim=True,actual_MPFR_calls=0,records_sha256=hashlib.sha256((W/'unit-records.jsonl.gz').read_bytes()).hexdigest(),elapsed_seconds=time.monotonic()-t,hardware_accessed=False)
(W/'unit-proof.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
