"""Own bounded actual ARM witnesses: private leaf, predicate, public/caller seam."""
from collections import Counter
from fractions import Fraction as F
from pathlib import Path
import hashlib,json,math,random,struct,sys
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-exp-directed-product-20261024'
V=R/'.build/m0-asin-scaled-bound-v164-20261023';Q=R/'.build/m0-float-fma-qualification-20261023'
sys.path[:0]=[str(Q/'support'),str(R/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle,bits
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R12,UC_ARM_REG_SP,UC_ARM_REG_XPSR
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
def equal(x,y):return bool(x&0x7fffffffffffffff>0x7ff0000000000000 and x&(1<<51))if y&0x7fffffffffffffff>0x7ff0000000000000 else x==y
def sio(m,state_name,state):
 after=bytes(m.uc.mem_read(0xd0000060,28))
 assert after==state if state_name=='DIRTY' else not(struct.unpack('<7I',after)[6]&2)
def save(name,d):
 with(O/name).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
rng=random.Random(0xE7D177);MASK=(1<<64)-1
edges=[0,1,2,65535,65536,0xffffffff,1<<32,(1<<54)-1,1<<62,(1<<63)-1,MASK]
pairs={(a,b):None for a in edges for b in edges}
for i in range(64):
 a,b=rng.getrandbits(64),rng.getrandbits(64)
 if i&1:a&=(1<<63)-1;b&=(1<<54)-1
 pairs[a,b]=None
leaf={name:Machine(W/('product-'+name+'.elf'),True)for name in('old','new')}
flags=[0];lows={name:SP for name in leaf};base=0x20038ee4
for name,m in leaf.items():
 assert not m.rom_models and not m.rom_initializers
 def pc(uc,address,size,user,name=name,m=m):
  assert base<=address<base+(158 if name=='old'else 154)and size==2
  sp=uc.reg_read(UC_ARM_REG_SP);assert SP-36<=sp<=SP and sp%4==0;lows[name]=min(lows[name],sp)
  if address==base:
   uc.reg_write(UC_ARM_REG_XPSR,0x01000000|(flags[0]<<28));uc.reg_write(UC_ARM_REG_R12,0xDEADBEEF^flags[0])
 def mem(uc,access,address,size,value,user):assert SP-36<=address and address+size<=SP
 m.uc.hook_add(UC_HOOK_CODE,pc);m.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,mem)
def rawcall(a,b,state):
 outputs=[]
 for name,m in leaf.items():
  m.uc.mem_write(0xd0000060,state);v,_,cost=m.call('mk61_m0_pow_exp_product',a,b,count=True)
  assert cost==(79 if name=='old'else 77)and bytes(m.uc.mem_read(0xd0000060,28))==state
  outputs.append(v)
 assert outputs[0]==outputs[1]
 retained=sum(((a>>(16*i))&65535)*((b>>(16*j))&65535)<<(16*(i+j))for i in range(4)for j in range(4)if i+j>=2)
 assert leaf['new'].uc.reg_read(UC_ARM_REG_R12)==(retained>>32)&0xffffffff
 if a<1<<63 and b<1<<54:
  assert outputs[1]==((retained+(1<<63))>>64)
  rho=F((retained>>63)&1)-F((retained>>32)&0xffffffff,1<<32)
  assert F(outputs[1])-F(a*b,1<<64)<=rho
for a,b in pairs:
 for state in states.values():rawcall(a,b,state)
for a,b in list(pairs)[-8:]:
 for flag in range(16):flags[0]=flag;rawcall(a,b,states['DIRTY'])
assert all(SP-low==36 for low in lows.values());print('own leaf PASS',len(pairs),flush=True)
# Independent generation around integer admission boundaries, including F MSB,
# signed bias extremes and the maximal g/head products. No author corpus rerun.
proof=json.loads((O/'proof.json').read_bytes());rh=F(1,1400);rem=F(proof['Taylor_and_step']);cross=F(proof['table_cross']);low=proof['step_low']
jobs={}
for head in(16384,24576,32767):
 for g in(1,2,1024,2939):
  for n in(1,518922,756388):
   for bias in(-(1<<31)+1,-1,0,(1<<31)-1):
    delta8=257+((3*g*g+65535)>>16)-max((((n*low)&0xffffffff)>>24)-1,0)
    effect=(delta8*(head+24)+65535)>>16;target=256-effect-(bias>>24)-2
    buckets={0,127,128,255,-target,256-target}
    for bucket in sorted(buckets):
     if 0<=bucket<256:
      for residue in(0,(1<<24)-1):
       frac=(bucket<<24)|residue;H=max(2,(g-1)*1024+1)
       row=((head<<48)|511,(n<<32)|(bias&0xffffffff),(((1-H)&0xffffffff)<<32)|frac)
       jobs[row]=(head,g,n,bias,frac)
alljobs=list(jobs.items());selected={alljobs[i*len(alljobs)//240][0]:alljobs[i*len(alljobs)//240][1]for i in range(240)}
direction=Machine(W/'direction-unit.elf',True);accept=reject=0;uppercounts=Counter()
assert not direction.rom_models and not direction.rom_initializers
for(q,args,params),(head,g,n,bias,frac)in selected.items():
 unrounded=(1+F(3*g*g,1<<24)+rem-F((n*low)&0xffffffff,1<<32)*(1-rh))*F(head+24,65536)+F(bias,1<<32)+cross
 got,_,cost=direction.call('audit_exp_direction',q,args,c=params,count=True)
 upper=got>>32;upper=upper if upper<1<<31 else upper-(1<<32);safe=got&0xffffffff
 assert safe in(0,1)and safe==int(upper<=256)
 rho=F(frac>>31)-F(frac,1<<32)
 assert unrounded+rho<F(upper,256)
 if safe:assert unrounded+rho<1;accept+=1
 else:reject+=1
 uppercounts[upper]+=1
assert accept and reject;print('own direction PASS',accept,reject,flush=True)
rom=R/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
machines={}
for name,file in(('candidate',O/'rebuild/candidate.elf'),('parent',W/'control.elf')):
 m=Machine(V/'firmware/mk61s-picocalc-pico-h.elf',True,bootrom=rom);image=ElfImage(file);image.load(m.uc)
 m.elf.symbols['entry']=image.symbols['mk61_m0_exp'];assert not m.rom_models;machines[name]=m
machines['Qfplib']=Machine(R/'.build/m0-v138-execution-20261023/reference/reference.elf',True)
cur={};events=[];child=machines['candidate'];trace=[]
def leafentry(uc,address,size,user):
 a=uc.reg_read(UC_ARM_REG_R0)|(uc.reg_read(UC_ARM_REG_R1)<<32);b=uc.reg_read(UC_ARM_REG_R2)|(uc.reg_read(UC_ARM_REG_R3)<<32)
 assert a<1<<63 and b<1<<54
 T=sum(((a>>(16*i))&65535)*((b>>(16*j))&65535)<<(16*(i+j))for i in range(4)for j in range(4)if i+j>=2)
 cur.update(F=(T>>32)&0xffffffff,leaf=True,A=a,displacement=b,leafSP=uc.reg_read(UC_ARM_REG_SP))
 assert cur['leafSP']%8==0
def marker(uc,address,size,user):
 if cur.get('leaf'):assert uc.reg_read(UC_ARM_REG_R12)==cur['F'];cur['marker']=True
def consumer(uc,address,size,user):
 assert cur.get('leaf')and cur.get('marker')and uc.reg_read(UC_ARM_REG_R12)==cur['F']
 q=uc.reg_read(UC_ARM_REG_R6)|(uc.reg_read(UC_ARM_REG_R7)<<32);assert(q&1023)==511
 cur.update(consumer=True,q=q)
def refinement(uc,address,size,user):cur['refine']=True
child.uc.hook_add(UC_HOOK_CODE,leafentry,begin=base,end=base)
child.uc.hook_add(UC_HOOK_CODE,marker,begin=0x101a14f0,end=0x101a14f0)
child.uc.hook_add(UC_HOOK_CODE,consumer,begin=0x101a164c,end=0x101a164c)
child.uc.hook_add(UC_HOOK_CODE,refinement,begin=0x101a0280,end=0x101a0280)
inputs={}
def add(x,group):
 if 0<=x<1<<64:inputs.setdefault(x,group)
for r in json.loads((W/'same-corpus-fixed11.json').read_bytes())['rows']:
 for offset in(-1,0,1):add(int(r['x'],16)+offset,'all11_fixed_plus_adjacent')
for r in json.loads((W/'original-exp16.json').read_bytes())['rows']:add(int(r['x'],16),'original_exp16')
reg=json.loads((W/'retained-parent-regressions.json').read_bytes())
for delta in(1,2,4,5,7,50):
 rr=[r for r in reg if r['candidate_instructions']-r['parent_instructions']==delta]
 for r in rr[:2]+rr[-2:]:add(int(r['x'],16),'retained_cost_increase_'+str(delta))
for n in(0,1,511,512,513,756387):
 center=bits(n*math.log(2)/512)
 for offset in(-1,0,1):
  for sign in(0,1<<63):add((center+offset)^sign,'segment_index0_boundaries')
for x in(0,1,(1<<52)-1,1<<52,0x3c90000000000000,0x3df0000000000000,0x3ff0000000000000,0x40862e42fefa39ef,0x40874910d52d3051,0x7fefffffffffffff,0x7ff0000000000000,0x7ff0000000000001,0x7ff8000000000001):
 for sign in(0,1<<63):add(x|sign,'IEEE_tiny_overflow_underflow')
for i in range(24):add(bits(rng.uniform(-745,710)),'own_random_normal')
oracle=Oracle();mpfr=snan=0;rows=[];peaks=Counter();originalkeys={r['x']for r in json.loads((W/'original-exp16.json').read_bytes())['rows']}
for i,(x,group)in enumerate(inputs.items()):
 if i%64==0:print('own public',i,'/',len(inputs),flush=True)
 expected=oracle.reference('exp',x);shortcut=x&0x7fffffffffffffff>0x7ff0000000000000 and not x&(1<<51)
 snan+=bool(shortcut);mpfr+=not shortcut
 for state_name,state in states.items():
  output={};costs={};cur.clear()
  for name,m in machines.items():
   m.uc.mem_write(0xd0000060,state);m.stack_lowest=SP
   got,_,cost=m.call('qfp_dexp'if name=='Qfplib'else'entry',x,count=True)
   if name!='Qfplib':assert equal(got,expected),(name,hex(x),hex(got),hex(expected))
   output[name]=f'{got:016X}';costs[name]=cost;sio(m,state_name,state);peaks[name]=max(peaks[name],SP-m.stack_lowest)
  assert output['candidate']==output['parent']
  if f'{x:016X}'in originalkeys:assert equal(int(output['Qfplib'],16),expected)and costs['candidate']<costs['Qfplib']
  rows.append(dict(x=f'{x:016X}',group=group,SIO=state_name,expected=f'{expected:016X}',outputs=output,instructions=costs,Qfplib_correct=equal(int(output['Qfplib'],16),expected),events=dict(cur)))
  if cur.get('consumer'):events.append(dict(x=f'{x:016X}',SIO=state_name,**cur))
assert events and any(not e.get('refine')for e in events)and any(r['events'].get('refine')for r in rows)
save('public-results.json',rows);save('actual-private-F-events.json',events)
print('own public PASS',len(inputs),'new consumer events',len(events),flush=True)
# Bounded actual shared caller seam: 3 former pow ties plus unchanged sin/cos controls (these fixtures make no product calls).
C=R/'.build/m0-exp-cached-product-20261024';S=R/'.build/m0-pow-square-ordinary-20261024';RS=R/'.build/m0-pow-rsqrt-asm-20261024'
def caller_machine(op,new):
 m=Machine(V/'firmware/mk61s-picocalc-pico-h.elf',True,bootrom=rom);ElfImage(C/'candidate.elf').load(m.uc)
 if op=='pow':
  ElfImage(S/'candidate.elf').load(m.uc);image=ElfImage(RS/'candidate.elf');image.load(m.uc)
  m.elf.symbols.update({n:a for n,a in image.symbols.items()if n.startswith('mk61_m0_pow_')})
 image=ElfImage(W/('candidate.elf'if new else'control.elf'));m.uc.mem_write(base,image.bytes_at(image.named_sections['.product_ram']))
 assert not m.rom_models;return m
cm={op:{name:caller_machine(op,name=='candidate')for name in('parent','candidate')}for op in('pow','sin','cos')}
for op in cm:cm[op]['Qfplib']=Machine(R/'.build/m0-v138-execution-20261023/reference/reference.elf',True)
calltraces={}
for op,group in cm.items():
 for name,m in group.items():
  if name=='Qfplib':continue
  calltraces[op,name]=[]
  def called(uc,address,size,user,op=op,name=name):
   a=uc.reg_read(UC_ARM_REG_R0)|(uc.reg_read(UC_ARM_REG_R1)<<32);b=uc.reg_read(UC_ARM_REG_R2)|(uc.reg_read(UC_ARM_REG_R3)<<32)
   calltraces[op,name].append((a,b))
  m.uc.hook_add(UC_HOOK_CODE,called,begin=base,end=base)
cr=json.loads((W/'caller-proof.json').read_bytes())['rows'];chosen={}
ties={'3FEFFFFFFFFFFF2B','3FF000000000004F','3FF000000000017C'}
for r in cr:
 if r['x']in ties or(r['operation']in('sin','cos')and r['operation']not in chosen):chosen[r['operation']if r['operation']in('sin','cos')else r['x']]=r
assert len(chosen)==5;callerrows=[]
for row in chosen.values():
 op=row['operation'];x=int(row['x'],16);y=int(row['y'],16)if row['y']else 0
 expected=oracle.reference(op,x,y)if op=='pow'else oracle.reference(op,x);mpfr+=1
 for state_name,state in states.items():
  outputs={};costs={};traces={}
  for name,m in cm[op].items():
   m.uc.mem_write(0xd0000060,state)
   if name!='Qfplib':calltraces[op,name].clear()
   got,_,cost=m.call(row['reference_symbol']if name=='Qfplib'else'_ZN12compact_math3'+op+('Edd'if op=='pow'else'Ed'),x,y,count=True)
   if name!='Qfplib':assert equal(got,expected);traces[name]=list(calltraces[op,name])
   outputs[name]=f'{got:016X}';costs[name]=cost;sio(m,state_name,state)
  assert outputs['candidate']==outputs['parent']and traces['candidate']==traces['parent']
  assert costs['candidate']==costs['parent']-2*len(traces['candidate'])
  if x in{int(v,16)for v in ties}:assert costs['candidate']<costs['Qfplib']and equal(int(outputs['Qfplib'],16),expected)
  callerrows.append(dict(operation=op,x=row['x'],y=row['y'],SIO=state_name,expected=f'{expected:016X}',outputs=outputs,instructions=costs,product_calls=len(traces['candidate'])))
save('caller-results.json',callerrows)
out=dict(status='PASS_OWN_BOUNDED_ACTUAL_ARM_AND_FRESH_MPFR',leaf_pairs=len(pairs),leaf_ARM=sum(m.calls for m in leaf.values()),NZCV16_pairs=8,leaf79to77=True,privateF_exact_every_leaf_call=True,leaf_frame36_bytes_each=True,
 direction_ARM=direction.calls,direction_accepted=accept,direction_rejected=reject,direction_against_unrounded_Fraction_enclosure=True,
 public_exp_inputs=len(inputs),public_exp_ARM=sum(m.calls for m in machines.values()),public_new_gate_events=len(events),all16_original_exp_inputs_strict_correct_Qfplib=True,
 all11_fixed_inputs_and_adjacent_checked=True,retained_plus1_2_4_5_7_50_cost_regressions_checked=True,othercaller_inputs=len(chosen),othercaller_ARM=sum(m.calls for group in cm.values()for m in group.values()),
 own_actual_directed_MPFR_inputs=mpfr,sNaN_shortcuts=snan,MPFR_version=oracle.version,
 public_28byte_DIRTY_preservation_and_READY_not_DIRTY=True,R4_R11_SP_everycall=True,actual_Flash_veneer_and_R12_definition_to_consumer_verified=True,
 observed_public_stack=dict(peaks),observed_stacks_not_universal=True,
 total_own_ARM=sum(m.calls for m in leaf.values())+direction.calls+sum(m.calls for m in machines.values())+sum(m.calls for group in cm.values()for m in group.values()),
 real_ROM_initialization_excluded_from_counts=True,no_ROM_arithmetic_models=True,physical_cycles=False,hardware=False)
save('arm.json',out);print(json.dumps(out,indent=2))
