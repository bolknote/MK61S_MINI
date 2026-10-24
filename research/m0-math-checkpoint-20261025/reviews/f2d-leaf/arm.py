"""Own bounded rebuilt ABI execution and direct MPFR from integer*2^power."""
from pathlib import Path
from collections import Counter
import ctypes as C,ctypes.util,hashlib,json,random,struct,sys
sys.dont_write_bytecode=True
O=Path(__file__).resolve().parent;R=O.parents[1];P=R/'.build/m0-f2d-leaf-20261024';V=R/'.build/m0-asin-scaled-bound-v164-20261023';Q=R/'.build/m0-float-fma-qualification-20261023'
sys.path[:0]=[str(Q/'support'),str(R/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE,UC_MEM_READ
from unicorn.arm_const import UC_ARM_REG_SP
from model import exact,source_model,reference_partition,F23
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
class Number(C.Structure):
 _fields_=[('precision',C.c_long),('sign',C.c_int),('exponent',C.c_long),('limbs',C.POINTER(C.c_ulong))]
class MPFR:
 def __init__(self):
  self.lib=C.CDLL(ctypes.util.find_library('mpfr'));l=self.lib;p=C.POINTER(Number)
  l.mpfr_init2.argtypes=[p,C.c_long];l.mpfr_clear.argtypes=[p]
  l.mpfr_set_ui.argtypes=[p,C.c_ulong,C.c_int];l.mpfr_set_ui.restype=C.c_int
  l.mpfr_mul_2si.argtypes=[p,p,C.c_long,C.c_int];l.mpfr_mul_2si.restype=C.c_int
  l.mpfr_neg.argtypes=[p,p,C.c_int];l.mpfr_neg.restype=C.c_int
  l.mpfr_set_nan.argtypes=[p];l.mpfr_set_inf.argtypes=[p,C.c_int]
  l.mpfr_get_d.argtypes=[p,C.c_int];l.mpfr_get_d.restype=C.c_double
  l.mpfr_get_version.restype=C.c_char_p;self.version=l.mpfr_get_version().decode();self.calls=0
 def convert(self,x):
  e=(x>>23)&255;f=x&F23;s=x>>31;n=Number();self.lib.mpfr_init2(C.byref(n),128)
  try:
   if e==255:
    if f:self.lib.mpfr_set_nan(C.byref(n))
    else:self.lib.mpfr_set_inf(C.byref(n),-1 if s else 1)
   else:
    sig=((1<<23)|f) if e else f;power=e-150 if e else -149
    assert self.lib.mpfr_set_ui(C.byref(n),sig,0)==0
    assert self.lib.mpfr_mul_2si(C.byref(n),C.byref(n),power,0)==0
    if s:assert self.lib.mpfr_neg(C.byref(n),C.byref(n),0)==0
   out=self.lib.mpfr_get_d(C.byref(n),0);self.calls+=1
   return struct.unpack('<Q',struct.pack('<d',out))[0]
  finally:self.lib.mpfr_clear(C.byref(n))
jobs={};groups=Counter();rng=random.Random(0xF2D0ADE)
def add(x,g):
 if 0<=x<1<<32 and x not in jobs:jobs[x]=g;groups[g]+=1
def pair(x,g):
 for s in (0,1<<31):add(x|s,g)
for e in range(1,255):
 for f in (0,F23,rng.getrandbits(23)):pair((e<<23)|f,'every_normal_exponent_both_signs')
for e in (1,2,126,127,128,129,253,254):
 for h in (0,0x7ffff,0xfffff):
  for low in range(8):pair((e<<23)|(h<<3)|low,'normal_high_low_split_and_carry')
for k in range(1,24):
 first=1<<(k-1);last=(1<<k)-1;values={first,last,(first+last)//2}
 for b in range(k-1):values.update([first|(1<<b),last^(1<<b)])
 for f in values:pair(f,'every_subnormal_width_and_lower_bit_controls')
for b in range(23):
 for f in (1<<b,F23^(1<<b),(1<<b)|1):pair(0x7f800000|f,'every_NaN_payload_bit')
for _ in range(64):pair(0x7f800000|rng.getrandbits(23),'mixed_NaN_payload')
pair(0,'both_signed_zero_old_deficits');pair(0x7f800000,'both_infinity_old_deficits')
for _ in range(128):add(rng.getrandbits(32),'independent_uniform_raw')
# Boundary neighbors of every exponent field transition, separate from
# broad random corpus replay. All such values widen exactly.
for e in (0,1,2,126,127,128,129,253,254,255):
 for delta in (-1,0,1):
  if 0<=(e<<23)+delta<1<<31:pair((e<<23)+delta,'exponent_boundary_neighbors')
(O/'own-inputs.bin').write_bytes(b''.join(struct.pack('<I',x) for x in jobs))
rom=R/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
machines={'candidate':Machine(O/'rebuild/candidate.elf',True),'intended_source':Machine(O/'rebuild/whole-source.elf',True),'parent':Machine(V/'firmware/mk61s-picocalc-pico-h.elf',True,bootrom=rom),'Qfplib':Machine(R/'.build/m0-v138-execution-20261023/reference/reference.elf',True)}
for label in ('candidate','intended_source'):
 assert not machines[label].rom_models and not machines[label].rom_initializers
assert not machines['parent'].rom_models
accesses=[];paths={k:Counter() for k in ['candidate','intended_source','Qfplib']};traces={k:[] for k in paths};reads={k:set() for k in ['candidate','intended_source']}
for label,m in machines.items():
 if label in ('candidate','intended_source'):
  def memory(uc,access,address,size,value,user,label=label):
   assert access==UC_MEM_READ and 0x10164094<=address and address+size<=0x101640ac,('nonliteral read or any write',label,access,hex(address),size)
   reads[label].add((address,size))
  m.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,memory)
  m.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,lambda uc,a,p,n,v,u:accesses.append((a,p,n)),begin=0xd0000000,end=0xd0000fff)
 if label in paths:
  def tick(uc,address,size,user,label=label):
   if label=='Qfplib':assert 0x10180f24<=address<0x10180f4a
   else:
    assert 0x10164000<=address<0x10164092 and size==2
    assert uc.reg_read(UC_ARM_REG_SP)==SP
   traces[label].append(address)
  m.uc.hook_add(UC_HOOK_CODE,tick)
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
oracle=MPFR();rows=[];classes=Counter();deltas=Counter();mpfr_nan=0;width_states=Counter();old_deficits=[]
for x,group in jobs.items():
 expected=exact(x);predicted,kind,cost,shift=source_model(x);rk,reference_correct,reference_cost=reference_partition(x)
 assert predicted==expected and rk==kind
 mpfr=oracle.convert(x)
 if kind=='NaN':assert mpfr&0x7fffffffffffffff>0x7ff0000000000000 and mpfr&(1<<51);mpfr_nan+=1
 else:assert mpfr==expected,(f'{x:08X}',f'{mpfr:016X}',f'{expected:016X}')
 for state_name,state in states.items():
  outputs={};counts={};trace_keys={}
  for label,m in machines.items():
   m.uc.mem_write(0xd0000060,state)
   if label in traces:traces[label].clear()
   got,_,observed=m.call('qfp_float2double' if label=='Qfplib' else '__aeabi_f2d',x,width=32,count=True)
   if label=='Qfplib':assert observed==reference_cost and (got==expected)==reference_correct
   else:
    assert got==expected,(label,f'{x:08X}',f'{got:016X}',f'{expected:016X}')
    if label!='parent':assert observed==cost
   if label in traces:
    assert len(traces[label])==observed
    path=tuple(traces[label]);paths[label][path]+=1;trace_keys[label]=hashlib.sha256(struct.pack('<'+'I'*len(path),*path)).hexdigest()
   assert bytes(m.uc.mem_read(0xd0000060,28))==state
   outputs[label]=f'{got:016X}';counts[label]=observed
  assert outputs['candidate']==outputs['intended_source']==outputs['parent']
  assert counts['candidate']==counts['intended_source']<counts['parent']
  if reference_correct:
   assert counts['candidate']<=counts['Qfplib']
   if counts['parent']>counts['Qfplib']:old_deficits.append(f'{x:08X}')
  if kind=='subnormal':width_states[(x>>31,(x&F23).bit_length())]+=1
  classes[kind]+=1;deltas[counts['candidate']-counts['parent']]+=1
  rows.append(dict(x=f'{x:08X}',group=group,SIO=state_name,kind=kind,normalizing_shift=shift,expected=f'{expected:016X}',MPFR=f'{mpfr:016X}',reference_correct=reference_correct,outputs=outputs,instructions=counts,path_sha256=trace_keys))
assert not accesses and max(deltas)<0
assert set(width_states)=={(s,k) for s in (0,1) for k in range(1,24)}
assert set(old_deficits)=={'00000000','80000000','7F800000','FF800000'}
assert [len(paths[k]) for k in ['candidate','intended_source','Qfplib']]==[53,53,3]
for label in ('candidate','intended_source'):assert machines[label].stack_lowest==SP and machines[label].calls==2*len(jobs)
assert oracle.calls==len(jobs) and sum(m.calls for m in machines.values())==8*len(jobs)
(O/'arm-rows.json').write_text(json.dumps(rows,indent=2)+'\n')
(O/'actual-paths.json').write_text(json.dumps({k:[dict(addresses=[f'{p:08X}' for p in path],count=n) for path,n in sorted(v.items())] for k,v in paths.items()},indent=2)+'\n')
d=dict(status='PASS_OWN_F2D_ADVERSARIAL_REBUILT_ARM_AND_INTEGER_POWER_MPFR',unique_inputs=len(jobs),fresh_ARM_calls=8*len(jobs),state_rows=2*len(jobs),machine_calls={k:m.calls for k,m in machines.items()},fresh_direct_MPFR_conversions=oracle.calls,MPFR_version=oracle.version,MPFR_input_finite_built_from_integer_times_power_of_two=True,MPFR_NaN_category_conversions=mpfr_nan,exact_integer_widening_every_input=True,all_parent_raw_bits_exact_including_NaN_payload_sign_quiet=True,groups=dict(groups),classes=dict(classes),actual_path_counts={k:len(v) for k,v in paths.items()},all23_subnormal_widths_each_sign_and_state=True,all_complete_source_costs_match_actual_ARM=True,all_correct_Qfplib_classes_no_slower=True,all_own_states_strictly_faster_parent=True,old_four_deficits_fixed=sorted(set(old_deficits)),parent_cost_delta_distribution=dict(sorted(deltas.items())),stack_bytes_candidate=0,stack_bytes_intended_source=0,SIO_accesses=0,all28_SIO_bytes_READY_DIRTY_preserved=True,leaf_memory_only_six_in_section_literals={k:sorted(v) for k,v in reads.items()},every_leaf_instruction_PC_and_SP_checked=True,no_leaf_external_ROM_mock_firmware_or_veneer=True,parent_real_ROM_initializers_excluded=machines['parent'].rom_initializers,inputs_sha256=sha(O/'own-inputs.bin'),rows_sha256=sha(O/'arm-rows.json'),hardware=False)
(O/'arm-result.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(d,indent=2))
