"""Bounded independent literal gate, raw ABI product, and full public risks."""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter
import ctypes as C,json,random,struct,sys
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;P=R/'.build/m0-exp-adaptive-enclosure-20261024';B=R/'.build/m0-exp-tiny-log-midpoint-20261024';V=R/'.build/m0-asin-scaled-bound-v164-20261023';Q=R/'.build/m0-float-fma-qualification-20261023'
sys.path[:0]=[str(Q/'support'),str(R/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle,_Number,bits
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE,UC_MEM_READ
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R7,UC_ARM_REG_SP,UC_ARM_REG_XPSR
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
def equal(x,y):return bool(x&0x7fffffffffffffff>0x7ff0000000000000 and x&(1<<51)) if y&0x7fffffffffffffff>0x7ff0000000000000 else x==y
proof=json.loads((O/'proof.json').read_text());E=F(proof['recomputed_delta']);Cres=F(proof['recomputed_residual'])
gate=Machine(O/'rebuild/unit.elf',True);assert not gate.rom_initializers and not gate.rom_models
gbase=gate.elf.symbols['audit_exp_gate']&~1;gate_access=[];gate_paths=Counter();gp=[]
def gpc(uc,pc,size,user):assert gbase<=pc<gbase+0x42;assert SP-16<=uc.reg_read(UC_ARM_REG_SP)<=SP;gp.append(pc)
def gmem(uc,access,address,size,value,user):assert SP-16<=address and address+size<=SP or(access==UC_MEM_READ and gbase+0x44<=address and address+size<=gbase+0x4c)
gate.uc.hook_add(UC_HOOK_CODE,gpc);gate.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,gmem)
gaccepted=0;gcost=Counter()
for q,d in struct.iter_unpack('<QQ',(O/'own-gate-inputs.bin').read_bytes()):
 signed=d if d<1<<31 else d-(1<<32);tail=q&1023;dist=abs(tail-512);bound=(275*((q>>48)+24)+16383)//16384+129;margin=dist*256+((signed>>24) if tail>512 else -(signed>>24)-1);expected=(bound<<32)|int(margin>bound)
 for name,state in states.items():
  gp.clear();gate.uc.mem_write(0xd0000060,state);got,_,cost=gate.call('audit_exp_gate',q,d,count=True);assert got==expected and bytes(gate.uc.mem_read(0xd0000060,28))==state
  gate_paths[tuple(gp)]+=1;gcost[cost]+=1
  if got&1:assert F(dist)+(F(signed,1<<32) if tail>512 else -F(signed,1<<32))>E*F((q>>48)+24,65536)+Cres;gaccepted+=1
print('gate complete',gate.calls,flush=True)
# Independent raw/carry samples and all16 incoming NZCV combinations.
rng=random.Random(0xADEC014);pairs={};MASK=(1<<64)-1
edges=[0,1,0xffff,0x10000,0xffffffff,1<<32,(1<<54)-1,1<<62,(1<<63)-1,MASK]
def add(a,b):pairs.setdefault((a&MASK,b&MASK),None)
for a in edges:
 for b in edges:add(a,b)
for i in range(4):
 for j in range(4):
  for v in [0xffff,0xfffe,0x8000]:
   for delta in [-1,0,1]:add((v<<(16*i))+delta,(v<<(16*j))-delta)
for i in range(384):
 a,b=rng.getrandbits(64),rng.getrandbits(64)
 if i&1:a&=(1<<63)-1;b&=(1<<54)-1
 add(a,b)
prod={n:Machine(O/('rebuild/product-'+n+'.elf'),True) for n in ['old','new']};prodmeta={n:dict(low=SP,flag=None,paths=Counter(),trace=[]) for n in prod};product_base=0x20038ee4
for name,m in prod.items():
 assert not m.rom_initializers and not m.rom_models
 def pc(uc,pc,size,user,name=name):
  meta=prodmeta[name];sizebody=168 if name=='old' else 162;assert product_base<=pc<product_base+sizebody
  if pc==product_base and meta['flag'] is not None:uc.reg_write(UC_ARM_REG_XPSR,0x01000000|(meta['flag']<<28))
  meta['low']=min(meta['low'],uc.reg_read(UC_ARM_REG_SP));assert SP-40<=uc.reg_read(UC_ARM_REG_SP)<=SP;meta['trace'].append(pc)
 def mem(uc,access,address,size,value,user):assert SP-40<=address and address+size<=SP
 m.uc.hook_add(UC_HOOK_CODE,pc);m.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,mem)
product_rows=[];valid=0;flagcalls=0
for a,b in pairs:
 values={}
 for state_name,state in states.items():
  for name,m in prod.items():
   prodmeta[name]['trace'].clear();m.uc.mem_write(0xd0000060,state);got,_,cost=m.call('mk61_m0_pow_exp_product',a,b,count=True);assert cost==(84 if name=='old' else 81);assert bytes(m.uc.mem_read(0xd0000060,28))==state;values[name]=got
   prodmeta[name]['paths'][tuple(prodmeta[name]['trace'])]+=1
  assert values['old']==values['new']
 if a<1<<63 and b<1<<54:
  retained=sum(((a>>(16*i))&65535)*((b>>(16*j))&65535)<<(16*(i+j)) for i in range(4) for j in range(4) if i+j>=2);expected=(retained+(1<<63))>>64
  assert values['new']==expected and abs(expected*(1<<64)-a*b)<=(1<<63)+(1<<49);valid+=1
 product_rows.append(dict(a=f'{a:016X}',b=f'{b:016X}',returned=f'{values["new"]:016X}',valid63x54=a<1<<63 and b<1<<54))
for a,b in list(pairs)[-16:]:
 for flags in range(16):
  values={}
  for name,m in prod.items():
   prodmeta[name]['flag']=flags;m.uc.mem_write(0xd0000060,states['DIRTY']);got,_,cost=m.call('mk61_m0_pow_exp_product',a,b,count=True);values[name]=got;assert cost==(84 if name=='old' else 81);flagcalls+=1
  assert values['old']==values['new']
for name,m in prod.items():assert SP-prodmeta[name]['low']==40 and SP-m.stack_lowest==(40 if name=='old' else 36)
print('product complete',len(pairs),'pairs, flags',flagcalls,flush=True)
# Independent directed log preimages generate hard full-function controls;
# generation is counted separately from fresh validation exp references.
oracle=Oracle();lib=oracle.lib;pointer=C.POINTER(_Number);lib.mpfr_set_ui.argtypes=[pointer,C.c_ulong,C.c_int];lib.mpfr_mul_2si.argtypes=[pointer,pointer,C.c_long,C.c_int]
logs=0
def log_dyadic(n,shift):
 global logs
 x=_Number();lib.mpfr_init2(C.byref(x),64);lib.mpfr_set_ui(C.byref(x),n,0);lib.mpfr_mul_2si(C.byref(x),C.byref(x),shift,0)
 try:
  for precision in [128,256,512,1024,2048]:
   out=[]
   for direction in [3,2]:
    y=_Number();lib.mpfr_init2(C.byref(y),precision)
    try:lib.mpfr_log(C.byref(y),C.byref(x),direction);out.append(bits(lib.mpfr_get_d(C.byref(y),0)))
    finally:lib.mpfr_clear(C.byref(y))
   if out[0]==out[1]:logs+=1;return out[0]
  raise AssertionError('log undecided')
 finally:lib.mpfr_clear(C.byref(x))
jobs={}
def job(x,group):jobs.setdefault(x,group)
for r in json.loads((P/'same-corpus-fixed29.json').read_text())['rows']:job(int(r['x'],16),'all29_fixed')
for r in json.loads((P/'old-margin-controls.json').read_text()):job(int(r['x'],16),'all56_prior_hot_margin_controls')
for r in json.loads((P/'retained-parent-regressions.json').read_text()):job(int(r['x'],16),'all100_known_parent_cost_increase_inputs')
for r in json.loads((V/'slower-inputs.json').read_text())['rows']:
 if r['operation']=='exp':job(int(r['x'],16),'original_exp16')
for r in json.loads((P/'stack-deep-diagnostic.json').read_text())['rows'][:12]:job(int(r['x'],16),'same_input_deep_stack_control')
for n in range(64):
 d=rng.getrandbits(40);num=(1<<54)-(2*d+1) if n&1 else (1<<53)+(2*d+1);center=log_dyadic(num,-54 if n&1 else -53)
 for delta in [-2,-1,0,1,2]:job(center+delta,'own_small_true_midpoint_preimages')
for n in range(64):
 M=(1<<52)|rng.getrandbits(52);k=[-1074,-1022,-512,-1,0,1,512,1023,1024][n%9];center=log_dyadic(2*M+1,k-53)
 for delta in [-2,-1,0,1,2]:job(center+delta,'own_normal_endpoint_true_midpoint_preimages')
for _ in range(128):job(bits(rng.uniform(-745.2,710.0)),'own_uniform_normal')
for x in [0,1,(1<<52)-1,1<<52,0x3c90000000000000,0x3df0000000000000,0x3ff0000000000000,0x7fefffffffffffff,0x7ff0000000000000,0x7ff0000000000001,0x7ff8000000000001]:
 for sign in [0,1<<63]:job(sign|x,'IEEE_and_tiny_boundary')
rom=R/'research/rp2040-memset-2026-10-21/capture/bootrom.bin';machines={};images={}
for name,path in [('candidate',O/'rebuild/candidate.elf'),('rebuilt_control',O/'rebuild/control.elf'),('accepted_parent',B/'candidate.elf')]:
 m=Machine(V/'firmware/mk61s-picocalc-pico-h.elf',True,bootrom=rom);im=ElfImage(path);im.load(m.uc);m.elf.symbols['entry']=im.symbols['mk61_m0_exp'];assert not m.rom_models;machines[name]=m;images[name]=im
machines['Qfplib']=Machine(R/'.build/m0-v138-execution-20261023/reference/reference.elf',True)
# Bind the actual inlined source gate and its comparison on full public calls.
current=dict(product=None,gate=None,events=[]);table={r['A']:r['delta32'] for r in json.loads((O/'table-rows.json').read_text())};public_gate_events=[]
child=machines['candidate']
def regs(uc):return [uc.reg_read(r) for r in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]]
def pstart(uc,pc,size,user):
 r=regs(uc);current['product']=dict(A=r[0]|r[1]<<32,D=r[2]|r[3]<<32)
def pend(uc,pc,size,user):
 r=regs(uc);current['product']['P']=r[0]|r[1]<<32
child.uc.hook_add(UC_HOOK_CODE,pstart,begin=product_base,end=product_base);child.uc.hook_add(UC_HOOK_CODE,pend,begin=product_base+160,end=product_base+160)
def gate_start(uc,pc,size,user):
 r=regs(uc);q=r[0]|r[1]<<32;d=uc.reg_read(UC_ARM_REG_R4);tail=uc.reg_read(UC_ARM_REG_R7);bias=r[3] if r[3]<1<<31 else r[3]-(1<<32);p=current['product'];assert p and p['A'] in table and bias==table[p['A']] and q in [p['A']-p['P'],p['A']+p['P']]
 assert d in [2,3] and tail==q&1023 and (1<<62)<=q<(1<<63)+(1<<53)+1
 bound=(275*((q>>48)+24)+16383)//16384+129;margin=d*256+((bias>>24) if tail>512 else -(bias>>24)-1)
 current['gate']=dict(q=q,A=p['A'],delta32=bias,distance=d,tail=tail,bound=bound,margin=margin,admit=margin>bound)
def gate_compare(uc,pc,size,user):
 g=current['gate'];r=regs(uc);assert g and r[2]==g['bound'] and r[3]==g['margin']&0xffffffff
 if g['admit']:
  gap=F(g['distance'])+(F(g['delta32'],1<<32) if g['tail']>512 else -F(g['delta32'],1<<32));assert gap>E*F(g['A'],1<<64)+Cres
 current['events'].append(dict(g));current['gate']=None
child.uc.hook_add(UC_HOOK_CODE,gate_start,begin=0x101a157e,end=0x101a157e);child.uc.hook_add(UC_HOOK_CODE,gate_compare,begin=0x101a15a4,end=0x101a15a4)
rows=[];mpfr=shortcuts=0;peaks=Counter()
for i,(x,group) in enumerate(jobs.items()):
 if i%128==0:print('public',i,'/',len(jobs),flush=True)
 expected=oracle.reference('exp',x);snan=x&0x7fffffffffffffff>0x7ff0000000000000 and not x&(1<<51);mpfr+=not snan;shortcuts+=snan
 for state_name,state in states.items():
  outputs={};costs={};stacks={}
  for name,m in machines.items():
   m.uc.mem_write(0xd0000060,state);m.stack_lowest=SP
   if name=='candidate':current.update(product=None,gate=None,events=[])
   got,_,cost=m.call('qfp_dexp' if name=='Qfplib' else 'entry',x,count=True);outputs[name]=f'{got:016X}';costs[name]=cost;stacks[name]=SP-m.stack_lowest;peaks[name]=max(peaks[name],stacks[name])
   if name!='Qfplib':assert equal(got,expected),(name,f'{x:016X}',f'{got:016X}',f'{expected:016X}')
   after=bytes(m.uc.mem_read(0xd0000060,28));assert after==state if state_name=='DIRTY' else not(struct.unpack('<7I',after)[6]&2)
  assert outputs['candidate']==outputs['rebuilt_control']==outputs['accepted_parent'] and costs['rebuilt_control']==costs['accepted_parent']
  for event in current['events']:public_gate_events.append(dict(x=f'{x:016X}',SIO=state_name,**event))
  rows.append(dict(x=f'{x:016X}',group=group,SIO=state_name,expected=f'{expected:016X}',outputs=outputs,instructions=costs,stack_bytes=stacks,Qfplib_correct=equal(int(outputs['Qfplib'],16),expected)))
assert public_gate_events and any(r['admit'] for r in public_gate_events) and any(not r['admit'] for r in public_gate_events)
for x,cc,qc in [('C041265824E2113C',599,622),('4085F424184F6DC5',2264,649)]:
 for r in [r for r in rows if r['x']==x]:assert r['instructions']['candidate']==cc and r['instructions']['Qfplib']==qc
fixed={r['x'] for r in json.loads((P/'same-corpus-fixed29.json').read_text())['rows']};assert len(fixed)==29
for r in rows:
 if r['x'] in fixed:assert r['Qfplib_correct'] and r['instructions']['candidate']<=r['instructions']['Qfplib']<r['instructions']['accepted_parent']
assert all(m.calls==2*len(jobs) for m in machines.values())
(O/'public-results.json').write_text(json.dumps(rows,indent=2)+'\n');(O/'actual-public-gate-events.json').write_text(json.dumps(public_gate_events,indent=2)+'\n');(O/'product-results.json').write_text(json.dumps(product_rows,indent=2)+'\n')
out=dict(status='PASS_OWN_BOUNDED_ADAPTIVE_GATE_PRODUCT_ABI_AND_PUBLIC_EXP',gate_cases=proof['own_bounded_gate_inputs'],gate_ARM_calls=gate.calls,gate_admitted_state_cases=gaccepted,gate_instruction_histogram=dict(gcost),gate_paths=len(gate_paths),gate_stack16=True,gate_PC_SP_memory_no_ROM_firmware_mock_SIO=True,raw_product_pairs=len(pairs),valid_product_integer_oracles=valid,product_ARM_calls=sum(m.calls for m in prod.values()),product_initial_NZCV16_variant_ARM_calls=flagcalls,all_raw_returns_parent_bit_exact=True,product_instructions_old84_new81=True,product_frame40_written_old40_new36=True,product_PC_excludes_padding_and_no_external_memory_SIO=True,public_exp_inputs=len(jobs),public_exp_ARM_calls=sum(m.calls for m in machines.values()),public_machine_calls={k:m.calls for k,m in machines.items()},public_exp_actual_directed_MPFR_inputs=mpfr,sNaN_shortcuts=shortcuts,MPFR_version=oracle.version,independent_log_preimage_generations_excluded_from_validation=logs,all29_fixed_and_prior56_margin_inputs_fresh_checked=True,public_actual_new_gate_events=len(public_gate_events),public_actual_gate_admissions=sum(r['admit'] for r in public_gate_events),all_actual_gate_q_bias_bound_margin_and_interval_source_exact=True,original_exp_hard_negative599_Q622_and_positive2264_Q649=True,raw_parent_bits_and_control_costs_exact=True,all_DIRTY28bytes_preserved_READY_not_left_DIRTY=True,observed_public_stack_peaks=dict(peaks),observed_peaks_not_universal=True,own_total_qualified_ARM=gate.calls+sum(m.calls for m in prod.values())+sum(m.calls for m in machines.values()),real_ROM_initializers_excluded=True,hardware=False,canonical=False)
(O/'arm-result.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
