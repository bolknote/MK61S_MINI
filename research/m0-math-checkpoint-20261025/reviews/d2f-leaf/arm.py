"""Own bounded actual ARM/public ABI and direct MPFR binary32 checks."""
from pathlib import Path
from collections import Counter,defaultdict
import ctypes as C,ctypes.util,hashlib,json,random,struct,sys
sys.dont_write_bytecode=True
O=Path(__file__).resolve().parent;R=O.parents[1];P=R/'.build/m0-d2f-leaf-20261024';V=R/'.build/m0-asin-scaled-bound-v164-20261023'
Q=R/'.build/m0-float-fma-qualification-20261023'
sys.path[:0]=[str(Q/'support'),str(R/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_SP
from model import exact,source_model,reference_partition,F52
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
class Number(C.Structure):
 _fields_=[('precision',C.c_long),('sign',C.c_int),('exponent',C.c_long),('limbs',C.POINTER(C.c_ulong))]
class MPFR:
 def __init__(self):
  self.lib=C.CDLL(ctypes.util.find_library('mpfr'));l=self.lib;p=C.POINTER(Number)
  l.mpfr_init2.argtypes=[p,C.c_long];l.mpfr_clear.argtypes=[p]
  l.mpfr_set_d.argtypes=[p,C.c_double,C.c_int];l.mpfr_set_d.restype=C.c_int
  l.mpfr_get_flt.argtypes=[p,C.c_int];l.mpfr_get_flt.restype=C.c_float
  l.mpfr_get_version.restype=C.c_char_p;self.version=l.mpfr_get_version().decode();self.calls=0
 def convert(self,x):
  n=Number();self.lib.mpfr_init2(C.byref(n),128)
  try:
   value=struct.unpack('<d',struct.pack('<Q',x))[0]
   ternary=self.lib.mpfr_set_d(C.byref(n),value,0)
   assert ternary==0
   out=self.lib.mpfr_get_flt(C.byref(n),0);self.calls+=1
   return struct.unpack('<I',struct.pack('<f',out))[0]
  finally:self.lib.mpfr_clear(C.byref(n))
jobs={};groups=Counter()
def add(x,group):
 if 0<=x<1<<64 and x not in jobs:jobs[x]=group;groups[group]+=1
def pair(x,g):
 for s in (0,1<<63):add(x|s,g)
# Every normal exponent and both signs: four distinct rounding paths,
# alternating high-fraction endpoints, all low retained-head values.
for e in range(897,1151):
 h=0xfffff if e&1 else 0;r=(e//2)&7
 for head,tail in [(r,0),(r,(1<<28)+1),(r&~1,1<<28),(r|1,1<<28)]:
  pair((e<<52)|(h<<32)|(head<<29)|tail,'all_normal_exponents_four_paths')
for e in (897,1023,1024,1150):
 for h in (0,0xfffff):
  for r in (0,7):
   for tail in ((1<<28)-1,1<<28,(1<<28)+1,(1<<29)-1):
    pair((e<<52)|(h<<32)|(r<<29)|tail,'normal_carry_and_half_neighbors')
# Every subnormal shift n=30..53, actual halfway cells and both neighbors.
for e in range(873,897):
 n=926-e;low=(1<<52)>>n;high=((1<<53)-1)>>n
 for q in {low,low+1,high-1,high}:
  if q<0:continue
  mid=(q<<n)+(1<<(n-1))
  for delta in (-1,0,1):
   m=mid+delta
   if (1<<52)<=m<1<<53:pair((e<<52)|(m-(1<<52)),'all_subnormal_actual_ties_neighbors')
# Exercise both shortcut-prefix costs 12 and 15, including high-F == all1
# with L==0 (SBC borrow) and all guard/sticky/parity choices.
for r in range(8):
 for tail in (0,1,(1<<28)-1,1<<28,(1<<28)+1,(1<<29)-1):
  pair((896<<52)|(0xfffff<<32)|(r<<29)|tail,'subnormal_upper_prefix_borrow_guard')
for e in (0,1,2,871,872,873,874,895,896,897,1023,1024,1150,1151,1152,2045,2046,2047):
 for f in (0,1,(1<<52)-1):pair((e<<52)|f,'range_special_endpoints')
for x in [(873<<52),(897<<52),(1151<<52)-(1<<28)]:
 for delta in (-2,-1,0,1,2):pair(x+delta,'minimum_half_minimum_normal_overflow_half')
for b in range(52):
 for f in (1<<b,F52^(1<<b),(1<<b)|1):pair((2047<<52)|f,'NaN_payload_bit_controls')
rng=random.Random(0xD2F0A11)
for _ in range(64):pair((2047<<52)|rng.getrandbits(52),'NaN_mixed_payload')
for _ in range(128):add(rng.getrandbits(64),'independent_uniform_raw')
# Sixteen old deficits are a bounded live check. The complete 512 sample
# is reconciled from sealed rows by proof.py, without rerunning it here.
old=json.loads((Q/'float.json').read_text())['operations']['d2f']['instruction_sample']
adverse=[r for r in old if r['own_instructions']>r['reference_instructions']]
for r in adverse[::max(1,len(adverse)//16)][:16]:add(int(r['arguments'][0],16),'old_deficit_live_subset')
(O/'own-inputs.bin').write_bytes(b''.join(struct.pack('<Q',x) for x in jobs))
rom=R/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
machines={
 'candidate':Machine(O/'rebuild/candidate.elf',True),
 'intended_source':Machine(O/'rebuild/whole-source.elf',True),
 'parent':Machine(V/'firmware/mk61s-picocalc-pico-h.elf',True,bootrom=rom),
 'Qfplib':Machine(R/'.build/m0-v138-execution-20261023/reference/reference.elf',True)}
assert not machines['candidate'].rom_models and not machines['intended_source'].rom_models
assert not machines['candidate'].rom_initializers and not machines['intended_source'].rom_initializers
assert not machines['parent'].rom_models
accesses=[];paths={k:Counter() for k in ('candidate','intended_source','Qfplib')};traces={k:[] for k in paths};memory_reads={k:set() for k in ('candidate','intended_source')}
for label,m in machines.items():
 if label in ('candidate','intended_source'):
  def memory(uc,access,address,size,value,user,label=label):
   if access==16:memory_reads[label].add((address,size))
   assert access==16 and 0x101630e8<=address and address+size<=0x10163100,('nonliteral read or any write',label,access,hex(address),size)
  m.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,memory)
  m.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,lambda uc,a,p,n,v,u:accesses.append((a,p,n)),begin=0xd0000000,end=0xd0000fff)
 if label in paths:
  def tick(uc,address,size,user,label=label):
   if label=='Qfplib':assert 0x10180f4a<=address<0x10180fa2
   else:
    assert 0x10163000<=address<0x101630e8 and size==2
    assert uc.reg_read(UC_ARM_REG_SP)==SP
   traces[label].append(address)
  m.uc.hook_add(UC_HOOK_CODE,tick)
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
oracle=MPFR();rows=[];classes=Counter();regressions=Counter();mpfr_nan=0
for index,(x,group) in enumerate(jobs.items()):
 expected=exact(x);predicted,kind,cost=source_model(x);rk,reference_correct,reference_cost=reference_partition(x)
 assert predicted==expected
 mpfr=oracle.convert(x)
 if (x>>52)&2047==2047 and x&F52:
  assert mpfr&0x7fffffff>0x7f800000 and mpfr&0x400000;mpfr_nan+=1
 else:assert mpfr==expected,(f'{x:016X}',f'{mpfr:08X}',f'{expected:08X}')
 for state_name,state in states.items():
  outputs={};counts={};trace_keys={}
  for label,m in machines.items():
   m.uc.mem_write(0xd0000060,state)
   if label in traces:traces[label].clear()
   got,_,observed=m.call('qfp_double2float' if label=='Qfplib' else '__aeabi_d2f',x,count=True);got&=0xffffffff
   if label=='Qfplib':
    assert observed==reference_cost and (got==expected)==reference_correct
   else:
    assert got==expected,(label,f'{x:016X}',f'{got:08X}',f'{expected:08X}')
    if label!='parent':assert observed==cost
   if label in traces:
    assert len(traces[label])==observed
    path=tuple(traces[label]);paths[label][path]+=1
    trace_keys[label]=hashlib.sha256(struct.pack('<'+'I'*len(path),*path)).hexdigest()
   assert bytes(m.uc.mem_read(0xd0000060,28))==state
   outputs[label]=f'{got:08X}';counts[label]=observed
  assert outputs['candidate']==outputs['intended_source']==outputs['parent']
  assert counts['candidate']==counts['intended_source']
  if reference_correct:assert counts['candidate']<=counts['Qfplib']
  regressions[counts['candidate']-counts['parent']]+=1;classes[kind]+=1
  rows.append(dict(x=f'{x:016X}',group=group,SIO=state_name,expected=f'{expected:08X}',MPFR=f'{mpfr:08X}',reference_correct=reference_correct,kind=kind,outputs=outputs,instructions=counts,path_sha256=trace_keys))
assert not accesses
assert set(reference_partition(x)[0] for x in jobs if reference_partition(x)[1])=={'zero','subnormal_to_normal','overflow','infinity',*(f'normal_{h}_{m}' for h in ('low','high') for m in ('truncate','up','tie_even','tie_odd'))}
assert set(source_model(x)[1] for x in jobs)>={'subnormal_full_down','subnormal_full_up','subnormal_full_tie','NaN'}
for label in ('candidate','intended_source'):assert machines[label].stack_lowest==SP and machines[label].calls==2*len(jobs)
assert oracle.calls==len(jobs)
assert sum(m.calls for m in machines.values())==8*len(jobs)
(O/'arm-rows.json').write_text(json.dumps(rows,indent=2)+'\n')
path_data={label:[dict(addresses=[f'{p:08X}' for p in path],count=n) for path,n in sorted(count.items())] for label,count in paths.items()}
(O/'actual-paths.json').write_text(json.dumps(path_data,indent=2)+'\n')
d=dict(status='PASS_OWN_ADVERSARIAL_REBUILT_ACTUAL_ARM_AND_MPFR',unique_inputs=len(jobs),fresh_ARM_calls=8*len(jobs),state_rows=2*len(jobs),machine_calls={k:m.calls for k,m in machines.items()},fresh_MPFR_conversions=oracle.calls,MPFR_version=oracle.version,MPFR_NaN_category_only_conversions=mpfr_nan,exact_integer_oracle_on_all_inputs=True,raw_parent_bits_exact_including_NaN_payload_sign_quiet=True,groups=dict(groups),classes=dict(classes),observed_actual_path_counts={k:len(v) for k,v in paths.items()},all_correct_reference_costs_no_slower=True,all_modeled_costs_exact_in_actual_ARM=True,stack_bytes_candidate=SP-machines['candidate'].stack_lowest,stack_bytes_intended_source=SP-machines['intended_source'].stack_lowest,SIO_accesses=0,SIO_READY_and_DIRTY_all28bytes_preserved=True,no_leaf_ROM_firmware_mocks_or_veneers=True,leaf_memory_only_six_in_section_literals={k:sorted(v) for k,v in memory_reads.items()},every_leaf_instruction_Thumb16_PC_inside_actual_body=True,leaf_SP_unchanged_on_every_instruction=True,parent_real_BootROM_initializers_excluded=machines['parent'].rom_initializers,parent_regression_distribution=dict(sorted(regressions.items())),inputs_sha256=sha(O/'own-inputs.bin'),rows_sha256=sha(O/'arm-rows.json'),hardware=False)
(O/'arm-result.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(d,indent=2))
