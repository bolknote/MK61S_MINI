"""Bounded actual Thumb and MPFR checks, with no physical interfaces."""
import ast,hashlib,json,random,struct,sys
from collections import Counter
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent
W=R/'.build/m0-pow-boundary128-20261025';SQ=R/'.build/m0-pow-square128-r2-20261025'
SUP=R/'.build/m0-float-fma-qualification-20261023/support';sys.path[:0]=[str(SUP),str(R/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP,bits
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R12,UC_ARM_REG_XPSR,UC_ARM_REG_SP,UC_ARM_REG_LR
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def save(n,d):
 with (O/n).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
 print(json.dumps(ref(O/n)),flush=True)
def memory(e,a,n):
 s=next(s for s in e.sections if s[1]!=8 and s[3]<=a and a+n<=s[3]+s[5]);return e.bytes_at(s)[a-s[3]:a-s[3]+n]
def compare_dyadic(a,e,b,f):
 z=min(e,f);aa=a<<(e-z);bb=b<<(f-z);return (aa>bb)-(aa<bb)
def bare():
 helpers=ElfImage(O/'rebuild/unit-helpers.elf');square=ElfImage(SQ/'unit-candidate.elf')
 machines={n:Machine(W/'control.elf'if n=='control'else O/'rebuild/candidate.elf',True)for n in ['control','candidate']}
 active={};events={n:[]for n in machines};low={n:SP for n in machines};pointer=SP-640
 for label,m in machines.items():
  assert not m.rom_models and not m.rom_initializers
  helpers.load(m.uc);square.load(m.uc);m.elf.symbols['boundary']=0x10150001
  start=0x10150000 if label=='control'else m.elf.symbols['mk61_m0_boundary128']&~1
  # Literal pools and GAS padding are readable data, never admitted as code.
  size=520 if label=='control'else 212
  allowed=[(0x100f9268,490),(0x1014f720,372),(0x100f9c9c,232),(0x1014e668,94),(start,size)]
  if label=='candidate':allowed.append((0x10150000,4))
  def code(uc,pc,n,user,label=label,allowed=allowed,start=start,size=size):
   assert any(a<=pc and pc+n<=a+z for a,z in allowed),(label,hex(pc),n)
   if pc==0x10150000:
    uc.reg_write(UC_ARM_REG_XPSR,0x01000000|(active['flags']<<28));uc.reg_write(UC_ARM_REG_R12,active['r12'])
   low[label]=min(low[label],uc.reg_read(UC_ARM_REG_SP))
   if pc in [0x100f9268,0x1014f720]and start<=(uc.reg_read(UC_ARM_REG_LR)&~1)<start+size:
    p,q=uc.reg_read(UC_ARM_REG_R0),uc.reg_read(UC_ARM_REG_R1)
    events[label].append(dict(kind='multiply'if pc==0x100f9268 else'compare',a=bytes(uc.mem_read(p,24)).hex(),b=bytes(uc.mem_read(q,24)).hex()))
  def write(uc,access,a,n,v,user):assert SP-384<=a and a+n<=SP,(hex(a),n)
  m.uc.hook_add(UC_HOOK_CODE,code);m.uc.hook_add(UC_HOOK_MEM_WRITE,write)
 rng=random.Random(0xB1281D25);cases=[];M64=(1<<64)-1
 cells=[0x0010000000000000,0x0010000000000001,0x3fefffffffffffff,0x3ff0000000000000,0x3ff0000000000001,0x7feffffffffffffe]
 for inv in [0,1]:
  for k in range(8):
   for j in range(8):
    cell=cells[j%len(cells)]if j<6 else rng.randrange(0x0010000000000000,0x7fefffffffffffff)
    d=1<<k;coef=2*((cell&((1<<52)-1))|(1<<52))+1;mid=coef**d;scale=((cell>>52)-1023-53)*d
    me=mid.bit_length()-1+scale;rad=[0,1,16,255,65535,1<<20,0,16][j]
    if inv:
     e=-me-1;shift=127-e-scale;center=(1<<shift)//mid
    else:
     e=me;shift=127+scale-e;center=mid<<shift if shift>=0 else mid>>(-shift)
    offset=[-rad-1,-1,0,1,rad+1,-(1<<30),1<<30,0][j]
    center=max(1<<127,min((1<<128)-1,center+offset))
    if j==7:center=(1<<127)|rng.getrandbits(127);e=rng.choice([-2048,-2,-1,0,1,2048])
    cases.append(dict(center=center,exponent=e,radius=rad,denominator=d,inverse=inv,cell=cell,mid=mid,scale=scale,valid=True))
 for i in range(16):
  # Full NZCV crossing is repeated at a deep exact square path.
  c=dict(cases[7*8+(i%8)]);c['flags']=i;cases.append(c)
 for cell in [0,1,0x000fffffffffffff,0x7fefffffffffffff,0x7ff0000000000000,0x7ff0000000000001,0x8000000000000000,0xffffffffffffffff]:
  for inv in [0,1]:cases.append(dict(center=(1<<127)+123,exponent=0,radius=0,denominator=128,inverse=inv,cell=cell,valid=False))
 rows=[];hist=Counter();decisions=Counter();nonzero=0;allflags=set()
 for i,c in enumerate(cases):
  flags=c.get('flags',i&15);allflags.add(flags);active.update(flags=flags,r12=rng.getrandbits(32))
  data=struct.pack('<QQiI',c['center']>>64,c['center']&M64,c['exponent'],c['radius']);outputs={};costs={}
  r3=rng.getrandbits(32)
  for label,m in machines.items():
   events[label].clear();m.uc.mem_write(pointer,data);m.uc.mem_write(SP,struct.pack('<Q',c['cell']))
   got,_,cost=m.call('boundary',pointer|(c['denominator']<<32),c['inverse']|(r3<<32),count=True)
   s=got&0xffffffff;s=s if s<1<<31 else s-(1<<32);assert s in [-1,0,1]
   assert bytes(m.uc.mem_read(pointer,24))==data and bytes(m.uc.mem_read(SP,8))==struct.pack('<Q',c['cell'])
   outputs[label]=s;costs[label]=cost
  assert outputs['control']==outputs['candidate']and events['control']==events['candidate']
  assert costs['candidate']<=costs['control'];side=outputs['candidate'];decisions[side]+=1
  if not c['valid']:assert side==0 and not events['candidate']
  else:
   assert len(events['candidate'])==1
   if side:
    nonzero+=1;lo,hi=c['center']-c['radius'],c['center']+c['radius'];e=c['exponent']-127
    if not c['inverse']:
     assert compare_dyadic(lo,e,c['mid'],c['scale'])>0 if side>0 else compare_dyadic(hi,e,c['mid'],c['scale'])<0
    else:
     assert compare_dyadic(hi*c['mid'],e+c['scale'],1,0)<0 if side>0 else compare_dyadic(lo*c['mid'],e+c['scale'],1,0)>0
  hist[costs['candidate']-costs['control']]+=1
  rows.append(dict(index=i,flags=flags,input=data.hex(),cell=f"{c['cell']:016X}",denominator=c['denominator'],inverse=c['inverse'],valid=c['valid'],returned_side=side,instructions=costs,midpoint_operands=list(events['candidate'])))
 assert allflags==set(range(16))and min(decisions)<0<max(decisions)
 save('bare-arm.json',dict(status='PASS_BOUNDED_BARE_BOUNDARY_ABI_AND_EXACT_DYADIC_ENDPOINTS',cases=len(cases),actual_ARM_calls=2*len(cases),
  all24bytes_and_returned_sides_identical=True,all_nonzero_sides_exact_integer_endpoint_proved=nonzero,decisions=dict(decisions),
  denominator_set=[1<<i for i in range(8)],both_inverse_modes=True,normal_cell_extremes_and_invalid_guards=True,
  all16NZCV_noisy_R3_R12_PCS_SP_PC_boundedwrites_input_and_cell_preserved=True,
  actual_helpers490_372_square232_helper94=True,multiply_alignment_and_all_literal_pools_excluded_from_PC=True,
  no_firmware_ROM_or_arithmetic_models=True,observed_stack_bytes={n:SP-p for n,p in low.items()},cost_delta_histogram=dict(hist),rows=rows,
  MPFR_inputs=0,device_IO=0))
def equal(a,b):return bool((a&0x7fffffffffffffff)>0x7ff0000000000000 and a&(1<<51))if (b&0x7fffffffffffffff)>0x7ff0000000000000 else a==b
states=dict(READY=struct.pack('<7I',0,0,0,0,0,0,1),DIRTY=struct.pack('<7I',17,3,17,3,5,2,3))
def public():
 # Reuse only the reviewed loader function, not producer harness imports.
 table=R/'.build/m0-pow-exp-table-product-20261025';im=ElfImage(table/'candidate.elf');entry=im.symbols['mk61_m0_pow_exp_table_product']&~1
 p=R/'.build/m0-pow-exp-table-product-independent-20261025/arm.py';tree=ast.parse(p.read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='machine')
 env=dict(R=R,W=table,im=im,entry=entry,Machine=Machine,ElfImage=ElfImage,memory=memory)
 exec(compile(ast.Module(body=[fn],type_ignores=[]),'<accepted-table-loader>','exec'),env)
 def machine(label):
  m=env['machine']('Qfplib'if label=='Qfplib'else'candidate')
  if label!='Qfplib':
   ElfImage(SQ/'candidate.elf').load(m.uc)
   if label in ['control','candidate']:
    e=ElfImage(W/'control.elf'if label=='control'else O/'rebuild/candidate.elf');e.load(m.uc);m.elf.symbols.update({n:a for n,a in e.symbols.items()if n.startswith('mk61_m0_boundary128')})
   assert bytes(m.uc.mem_read(entry,20))==memory(im,entry,20)
  return m
 machines={n:machine(n)for n in ['parent','control','candidate','Qfplib']};traces={}
 for label in ['parent','control','candidate']:
  m=machines[label];entries=[];operands=[];traces[label]=entries,operands
  start=0x101e0000 if label=='candidate'else 0x10150000;size=212 if label=='candidate'else 520
  def call(uc,pc,n,user,entries=entries):
   p=uc.reg_read(UC_ARM_REG_R0);sp=uc.reg_read(UC_ARM_REG_SP)
   entries.append(dict(power=bytes(uc.mem_read(p,24)).hex(),denominator=uc.reg_read(UC_ARM_REG_R1),inverse=uc.reg_read(UC_ARM_REG_R2),cell=f'{struct.unpack("<Q",uc.mem_read(sp,8))[0]:016X}'))
  m.uc.hook_add(UC_HOOK_CODE,call,begin=start,end=start)
  def operands_hook(uc,pc,n,user,operands=operands,start=start,size=size):
   if start<=(uc.reg_read(UC_ARM_REG_LR)&~1)<start+size:
    a,b=uc.reg_read(UC_ARM_REG_R0),uc.reg_read(UC_ARM_REG_R1)
    operands.append(dict(kind='multiply'if pc==0x100f9268 else'compare',a=bytes(uc.mem_read(a,24)).hex(),b=bytes(uc.mem_read(b,24)).hex()))
  for address in [0x100f9268,0x1014f720]:m.uc.hook_add(UC_HOOK_CODE,operands_hook,begin=address,end=address)
 jobs={}
 for r in json.loads((O/'selected-public-jobs.json').read_text())['jobs']:jobs[int(r['x'],16),int(r['y'],16)]=r['group']
 for x,y in [(0,0),(1,bits(.5)),(bits(-2.),bits(.5)),(0x7fefffffffffffff,bits(-.5)),(bits(1.),0x7ff0000000000001),(0xfff0000000000001,bits(0.))]:jobs[x,y]='IEEE_and_sNaN_controls'
 oracle=Oracle();refs=['qfp_composed_pow','qfp_composed_pow_exact','qfp_composed_pow_integer'];rows=[];snans=0;calls=0
 saved=json.loads((W/'new-qualification.json').read_text());saved={(r['x'],r['y'],r['SIO']):r for r in saved['rows']}
 for (x,y),group in jobs.items():
  expected=oracle.reference('pow',x,y);snans+=any((v&0x7fffffffffffffff)>0x7ff0000000000000 and not v&(1<<51)for v in [x,y])
  for state_name,state in states.items():
   outputs={};costs={};correct={}
   for label in ['parent','control','candidate',*refs]:
    m=machines[label if label in machines else'Qfplib']
    if label in traces:traces[label][0].clear();traces[label][1].clear()
    m.uc.mem_write(0xd0000060,state);got,_,cost=m.call(label if label in refs else'_ZN12compact_math3powEdd',x,y,count=True);calls+=1
    after=bytes(m.uc.mem_read(0xd0000060,28));assert after==state if state_name=='DIRTY'else not struct.unpack('<7I',after)[6]&2
    outputs[label]=f'{got:016X}';costs[label]=cost;correct[label]=equal(got,expected)
    if label not in refs:assert correct[label],(hex(x),hex(y),label,hex(got),hex(expected))
   assert outputs['parent']==outputs['control']==outputs['candidate']and costs['parent']==costs['control']and costs['candidate']<=costs['parent']
   assert traces['parent']==traces['control']==traces['candidate']
   key=f'{x:016X}',f'{y:016X}',state_name
   if key in saved:
    s=saved[key];assert s['outputs']==outputs and s['instructions']==costs and s['boundary_calls']==traces['candidate'][0]and s['midpoint_operands']==traces['candidate'][1]
   rows.append(dict(x=key[0],y=key[1],SIO=state_name,group=group,expected=f'{expected:016X}',outputs=outputs,instructions=costs,correct=correct,boundary_calls=list(traces['candidate'][0]),midpoint_operands=list(traces['candidate'][1])))
 witness=[r for r in rows if r['x']=='37F31678F40ED67B'and r['y']=='3FAC000000000000'];assert len(witness)==2 and all(r['instructions']['parent']==3728 and r['instructions']['candidate']==3548 for r in witness)
 save('public-arm-mpfr.json',dict(status='PASS_BOUNDED_ACTUAL_PUBLIC_BOUNDARY_CALLER_ALL3_QFPLIB',unique_pairs=len(jobs),state_rows=len(rows),actual_ARM_calls=calls,
  directed_MPFR_inputs=len(jobs)-snans,sNaN_policy_shortcuts=snans,MPFR_version=oracle.version,
  bothSIO_PCS_SP_PC_and_SIO28_preserved=True,all_actual_entry_and_midpoint_operand_sequences_identical=True,
  all3_real_Qfplib_correct_and_wrong_outputs_costs_retained=True,strict_quietNaN=True,
  parent_control_exact_cost_and_outputs=True,candidate_no_new_loss_or_cost_increase=True,
  actual180instruction_witness_confirmed_bothSIO=True,accepted_table_entry_not_overwritten=True,
  near_one_overlay_not_loaded=True,no_other_math_qualification=True,
  observed_stack_bytes={n:SP-m.stack_lowest for n,m in machines.items()},rows=rows,device_IO=0))
if __name__=='__main__':
 assert len(sys.argv)==2 and sys.argv[1]in ['bare','public'];globals()[sys.argv[1]]()
