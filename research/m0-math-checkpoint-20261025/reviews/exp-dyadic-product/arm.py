"""Bounded own exact-integer units, NZCV/SP validation, and actual public dyadic branch."""
from pathlib import Path
from collections import Counter
import json,math,random,struct,sys
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;P=R/'.build/m0-exp-dyadic-product-20261024';B=R/'.build/m0-exp-adaptive-enclosure-20261024';V=R/'.build/m0-asin-scaled-bound-v164-20261023';Q=R/'.build/m0-float-fma-qualification-20261023'
sys.path[:0]=[str(Q/'support'),str(R/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle,bits
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_SP,UC_ARM_REG_PC,UC_ARM_REG_XPSR
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
def equal(x,y):return bool(x&0x7fffffffffffffff>0x7ff0000000000000 and x&(1<<51)) if y&0x7fffffffffffffff>0x7ff0000000000000 else x==y
values=[v for v, in struct.iter_unpack('<Q',(O/'own-dyadic-inputs.bin').read_bytes())];unit=Machine(O/'rebuild/dyadic-unit.elf',True);assert not unit.rom_initializers and not unit.rom_models;unitbase=unit.elf.symbols['audit_dyadic_product']&~1;flag=[None]
def upc(uc,pc,size,user):
 assert unitbase<=pc<unitbase+18 and uc.reg_read(UC_ARM_REG_SP)==SP
 if pc==unitbase and flag[0] is not None:uc.reg_write(UC_ARM_REG_XPSR,0x01000000|(flag[0]<<28))
def umem(*args):raise AssertionError('literal dyadic unit must not access any data memory')
unit.uc.hook_add(UC_HOOK_CODE,upc);unit.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,umem)
for b in values:
 expected=(((1<<62)*b)+(1<<63))>>64
 for state in states.values():
  unit.uc.mem_write(0xd0000060,state);got,_,cost=unit.call('audit_dyadic_product',b,count=True);assert got==expected and cost==9 and bytes(unit.uc.mem_read(0xd0000060,28))==state
for b in [0,1,2,3,0xfffffffd,0xfffffffe,0xffffffff,(1<<54)-1]:
 for nzcv in range(16):
  flag[0]=nzcv;got,_,cost=unit.call('audit_dyadic_product',b,count=True);assert got==(b+2)>>2 and cost==9
assert unit.calls==2*len(values)+128
pairs={};MASK=(1<<64)-1
for b in values:pairs[1<<62,b]=None
edges=[0,1,0xffff,0x10000,0xffffffff,1<<32,(1<<54)-1,1<<62,(1<<63)-1,MASK]
for a in edges:
 for b in edges:pairs[a,b]=None
rng=random.Random(0xD7AD79)
for i in range(384):
 a,b=rng.getrandbits(64),rng.getrandbits(64)
 if i&1:a&=(1<<63)-1;b&=(1<<54)-1
 pairs[a,b]=None
prod={n:Machine(O/('rebuild/product-'+n+'.elf'),True) for n in ['old','new']};meta={n:dict(flag=None,low=SP,residues=set(),entrySP=SP) for n in prod};base=0x20038ee4
for name,m in prod.items():
 assert not m.rom_initializers and not m.rom_models
 def pc(uc,pc,size,user,name=name):
  t=meta[name];body=162 if name=='old' else 158;frame=40 if name=='old' else 36
  assert base<=pc<base+body and size==2;s=uc.reg_read(UC_ARM_REG_SP);assert s%4==0 and SP-frame<=s<=SP;t['low']=min(t['low'],s);t['residues'].add(s%8)
  if pc==base:
   assert s%8==0
   if t['flag'] is not None:uc.reg_write(UC_ARM_REG_XPSR,0x01000000|(t['flag']<<28))
 def mem(uc,access,address,size,value,user):assert SP-36<=address and address+size<=SP
 m.uc.hook_add(UC_HOOK_CODE,pc);m.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,mem)
valid=0;prodrows=[]
for a,b in pairs:
 out={}
 for state in states.values():
  for name,m in prod.items():
   m.uc.mem_write(0xd0000060,state);got,_,cost=m.call('mk61_m0_pow_exp_product',a,b,count=True);assert cost==(81 if name=='old' else 79) and bytes(m.uc.mem_read(0xd0000060,28))==state;out[name]=got
  assert out['old']==out['new']
 if a<1<<63 and b<1<<54:
  retained=sum(((a>>(16*i))&65535)*((b>>(16*j))&65535)<<(16*(i+j)) for i in range(4) for j in range(4) if i+j>=2);expected=(retained+(1<<63))>>64;assert out['new']==expected and abs(expected*(1<<64)-a*b)<=(1<<63)+(1<<49);valid+=1
 prodrows.append(dict(a=f'{a:016X}',b=f'{b:016X}',returned=f'{out["new"]:016X}'))
for a,b in list(pairs)[-16:]:
 for nzcv in range(16):
  out={}
  for name,m in prod.items():meta[name]['flag']=nzcv;got,_,cost=m.call('mk61_m0_pow_exp_product',a,b,count=True);assert cost==(81 if name=='old' else 79);out[name]=got
  assert out['old']==out['new']
assert [SP-meta[n]['low'] for n in ['old','new']]==[40,36] and all(SP-m.stack_lowest==36 for m in prod.values())
print('units complete',len(values),len(pairs),flush=True)
jobs={}
def add(x,g):jobs.setdefault(x,g)
# All fixed same-corpus cells are cheap exact-dyadic targets, not a broad old sweep.
fixed=json.loads((P/'same-corpus-fixed547.json').read_text())['rows']
for r in fixed:add(int(r['x'],16),'all547_fixed_dyadic_targets')
reg=json.loads((P/'retained-parent-regressions.json').read_text());uniq={int(r['x'],16):r for r in reg}
for i,(x,r) in enumerate(uniq.items()):
 if i%127==0:add(x,'stratified_parent_regressions')
for r in json.loads((B/'old-margin-controls.json').read_text()):add(int(r['x'],16),'prior_hot_margin_controls')
for r in json.loads((V/'slower-inputs.json').read_text())['rows']:
 if r['operation']=='exp':add(int(r['x'],16),'original_exp16')
for k in [-1023,-768,-16,-2,-1,0,1,2,16,768,1023]:
 for n in [-1,0,1]:
  center=bits((k*512+n)*math.log(2)/512)
  for step in [-1,0,1]:
   if 0<=center+step<1<<64:add(center+step,'own_index0_and_neighbor_table_segments')
for _ in range(64):add(bits(rng.uniform(-745.2,710.0)),'own_normal_controls')
for x in [0,1,(1<<52)-1,1<<52,0x3c90000000000000,0x3df0000000000000,0x3ff0000000000000,0x7fefffffffffffff,0x7ff0000000000000,0x7ff0000000000001,0x7ff8000000000001]:
 for sign in [0,1<<63]:add(x|sign,'IEEE_tiny_domain_boundaries')
rom=R/'research/rp2040-memset-2026-10-21/capture/bootrom.bin';machines={}
for name,path in [('candidate',O/'rebuild/candidate.elf'),('rebuilt_control',O/'rebuild/control.elf'),('accepted_parent',B/'candidate.elf')]:
 m=Machine(V/'firmware/mk61s-picocalc-pico-h.elf',True,bootrom=rom);im=ElfImage(path);im.load(m.uc);m.elf.symbols['entry']=im.symbols['mk61_m0_exp'];assert not m.rom_models;machines[name]=m
machines['Qfplib']=Machine(R/'.build/m0-v138-execution-20261023/reference/reference.elf',True)
child=machines['candidate'];cur=dict(decisions=[],dyadic=[],product_calls=0,leafSP=SP);events=[]
def decision(uc,pc,size,user):
 d=uc.reg_read(UC_ARM_REG_R2)|(uc.reg_read(UC_ARM_REG_R3)<<32);A=uc.reg_read(UC_ARM_REG_R6)|(uc.reg_read(UC_ARM_REG_R7)<<32);index=uc.reg_read(UC_ARM_REG_R5);assert 0<=index<512 and d+2<1<<54
 if index==0:assert A==1<<62
 cur['decisions'].append(dict(index=index,A=A,displacement=d))
def shift_done(uc,pc,size,user):
 assert cur['decisions'] and cur['decisions'][-1]['index']==0;d=cur['decisions'][-1]['displacement'];correction=uc.reg_read(UC_ARM_REG_R0)|(uc.reg_read(UC_ARM_REG_R3)<<32);assert correction==(d+2)>>2;cur['dyadic'].append(correction)
def leafpc(uc,pc,size,user):
 s=uc.reg_read(UC_ARM_REG_SP)
 if pc==base:cur['leafSP']=s;cur['product_calls']+=1;assert s%8==0
 assert base<=pc<base+158 and s%4==0 and cur['leafSP']-36<=s<=cur['leafSP']
def leafmem(uc,access,address,size,value,user):
 if base<=uc.reg_read(UC_ARM_REG_PC)<base+158:assert cur['leafSP']-36<=address and address+size<=cur['leafSP']
child.uc.hook_add(UC_HOOK_CODE,decision,begin=0x101a14e6,end=0x101a14e6);child.uc.hook_add(UC_HOOK_CODE,shift_done,begin=0x101a15cc,end=0x101a15cc);child.uc.hook_add(UC_HOOK_CODE,leafpc,begin=base,end=base+167);child.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,leafmem)
oracle=Oracle();rows=[];mpfr=snan=0;peaks=Counter()
for i,(x,g) in enumerate(jobs.items()):
 if i%128==0:print('public',i,'/',len(jobs),flush=True)
 expected=oracle.reference('exp',x);shortcut=x&0x7fffffffffffffff>0x7ff0000000000000 and not x&(1<<51);snan+=shortcut;mpfr+=not shortcut
 for state_name,state in states.items():
  out={};costs={}
  for name,m in machines.items():
   m.uc.mem_write(0xd0000060,state);m.stack_lowest=SP
   if name=='candidate':cur.update(decisions=[],dyadic=[],product_calls=0)
   got,_,cost=m.call('qfp_dexp' if name=='Qfplib' else 'entry',x,count=True);out[name]=f'{got:016X}';costs[name]=cost;peaks[name]=max(peaks[name],SP-m.stack_lowest)
   if name!='Qfplib':assert equal(got,expected),(name,f'{x:016X}',f'{got:016X}',f'{expected:016X}')
   after=bytes(m.uc.mem_read(0xd0000060,28));assert after==state if state_name=='DIRTY' else not(struct.unpack('<7I',after)[6]&2)
  assert out['candidate']==out['rebuilt_control']==out['accepted_parent'] and costs['rebuilt_control']==costs['accepted_parent']
  assert len(cur['decisions'])<=1
  if cur['decisions']:
   z=cur['decisions'][0];assert len(cur['dyadic'])==int(z['index']==0) and cur['product_calls']==int(z['index']!=0);events.append(dict(x=f'{x:016X}',SIO=state_name,**z,correction=cur['dyadic'][0] if cur['dyadic'] else None))
  rows.append(dict(x=f'{x:016X}',group=g,SIO=state_name,expected=f'{expected:016X}',outputs=out,instructions=costs,Qfplib_correct=equal(int(out['Qfplib'],16),expected)))
for x,childcost,parentcost,qcost in [('4085F424184F6DC5',2266,2264,649),('C041265824E2113C',596,599,622),('3DF0000000000000',439,520,471),('BDF0000000000000',461,542,520)]:
 rr=[r for r in rows if r['x']==x];assert len(rr)==2
 for r in rr:assert r['instructions']['candidate']==childcost and r['instructions']['accepted_parent']==parentcost and r['instructions']['Qfplib']==qcost
fixedkeys={r['x'] for r in fixed};assert len(fixedkeys)==547
for r in rows:
 if r['x'] in fixedkeys:assert r['Qfplib_correct'] and r['instructions']['candidate']<=r['instructions']['Qfplib']<r['instructions']['accepted_parent']
assert any(e['index']==0 for e in events) and any(e['index']!=0 for e in events)
(O/'public-results.json').write_text(json.dumps(rows,indent=2)+'\n');(O/'actual-product-selection-events.json').write_text(json.dumps(events,indent=2)+'\n');(O/'product-results.json').write_text(json.dumps(prodrows,indent=2)+'\n')
out=dict(status='PASS_OWN_DYADIC_PRODUCT_PCS_NZCV_AND_PUBLIC_BRANCH',literal_dyadic_values=len(values),literal_dyadic_ARM=unit.calls,literal_NZCV16_variant_calls128_included=True,literal9instructions_stack0_no_data_memory_or_ROM=True,raw_product_pairs=len(pairs),valid63x54_integer_product_oracles=valid,raw_product_ARM=sum(m.calls for m in prod.values()),raw_product_NZCV16_variant_calls512_included=True,all_raw_parent_returns_bit_exact=True,product81to79_fixed=True,frame_old40_new36_and_writes_both36=True,SP_word_aligned_always_public8_at_entry_return=True,no_external_leaf_calls_or_memory_or_SIO_or_padding_execution=True,public_exp_inputs=len(jobs),public_exp_ARM=sum(m.calls for m in machines.values()),public_actual_MPFR=mpfr,sNaN_shortcuts=snan,MPFR_version=oracle.version,all547_fixed_original16_prior_margin_and_stratified_increases_checked=True,actual_selection_events=len(events),actual_index0_events=sum(e['index']==0 for e in events),all_actual_displacements_and_shift_corrections_exact=True,source_index0_skips_shared_kernel_other_index_calls_once=True,all_public_raw_parent_bits_and_control_costs_exact=True,positive_hard_exp_regression2264to2266_retained=True,negative_hard_exp599to596_still_fasterQ622=True,all_DIRTY28bytes_preserved_READY_not_DIRTY=True,observed_public_stacks=dict(peaks),peaks_not_universal=True,own_qualified_ARM=unit.calls+sum(m.calls for m in prod.values())+sum(m.calls for m in machines.values()),real_ROM_initializers_excluded=True,hardware=False,canonical=False)
(O/'arm-result.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
