"""Bounded actual Thumb/MPFR square128 review; no physical interfaces."""
import ast,hashlib,json,math,random,struct,sys
from collections import Counter
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-square128-r2-20261025';SUP=R/'.build/m0-float-fma-qualification-20261023/support'
sys.path[:0]=[str(SUP),str(R/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP,bits
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R12,UC_ARM_REG_XPSR,UC_ARM_REG_SP
binding=json.loads((O/'binding.json').read_text());entry=binding['entry'];helper=binding['helper'];M64=(1<<64)-1;M32=(1<<32)-1
def ref(p):p=Path(p);d=p.read_bytes();return dict(path=str(p),bytes=len(d),sha256=hashlib.sha256(d).hexdigest())
def save(n,d):
 with (O/n).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
 print(json.dumps(ref(O/n)),flush=True)
def high32(a,b):return (a>>16)*(b>>16)+((a&65535)*(b>>16)>>16)+((a>>16)*(b&65535)>>16)
def approx(a,b):return ((a>>32)*(b>>32)+high32(a&M32,b>>32)+high32(a>>32,b&M32))&M64
def model(h,l,e,r):
 p=(h*h+(2*approx(l,h)if l else 0))&((1<<128)-1);upper=bool(p>>127);radius=(2*r+(16 if l else bool(r)))&M32;exponent=e*2&M32
 if upper:exponent=(exponent+1)&M32
 else:p=p*2&((1<<128)-1);radius=radius*2&M32
 return struct.pack('<QQII',p>>64,p&M64,exponent,radius),upper
costs={(False,False):(129,94),(False,True):(116,89),(True,False):(195,154),(True,True):(182,149)}
def bare():
 machines={n:Machine(W/('unit-'+n+'.elf'),True)for n in ['control','candidate']};active={};minsp={n:SP for n in machines};pointer=SP-512;calls=0;hist=Counter()
 for label,m in machines.items():
  assert not m.rom_models and not m.rom_initializers
  def code(uc,pc,size,_,label=label):
   if pc==entry:uc.reg_write(UC_ARM_REG_XPSR,0x01000000|(active['flags']<<28));uc.reg_write(UC_ARM_REG_R12,active['r12'])
   minsp[label]=min(minsp[label],uc.reg_read(UC_ARM_REG_SP))
   size=machines[label].elf.sizes['pow_integer128_square'];assert entry<=pc<entry+size or helper<=pc<helper+94
  def write(uc,access,address,size,value,_):assert SP-80<=address and address+size<=SP or pointer<=address and address+size<=pointer+24
  m.uc.hook_add(UC_HOOK_CODE,code);m.uc.hook_add(UC_HOOK_MEM_WRITE,write)
 t=math.isqrt(1<<127);rng=random.Random(0x2510128);jobs=[]
 for h in [0,1,(1<<32)-1,1<<32,(1<<32)+1,1<<63,t-1,t,t+1,M64]:
  for l in [0,1,M64]:
   for radius in [0,1,0x80000000,M32]:jobs.append((h,l,rng.choice([0,1,0x7fffffff,0x80000000,M32]),radius,0))
 for flags in range(16):
  for h in [1<<63,t-1,t,M64]:
   for l in [0,M64]:jobs.append((h,l,M32,M32,flags))
 for _ in range(32):jobs.append((rng.getrandbits(64),rng.getrandbits(64),rng.getrandbits(32),rng.getrandbits(32),rng.randrange(16)))
 for h,l,e,r,flags in jobs:
  expected,upper=model(h,l,e,r);data=struct.pack('<QQII',h,l,e,r);measured={}
  for label,m in machines.items():
   active.update(flags=flags,r12=rng.getrandbits(32));m.uc.mem_write(pointer,data)
   _,_,count=m.call('pow_integer128_square',pointer|(rng.getrandbits(32)<<32),rng.getrandbits(64),count=True);calls+=1
   assert bytes(m.uc.mem_read(pointer,24))==expected;measured[label]=count
  assert (measured['control'],measured['candidate'])==costs[bool(l),upper]
  hist[str((bool(l),upper))]+=1
 assert len(hist)==4 and {n:SP-v for n,v in minsp.items()}==dict(control=68,candidate=60)
 save('bare-arm.json',dict(status='PASS_BOUNDED_ACTUAL_24BYTE_TRANSFORM_AND_PCS',tests=len(jobs),qualified_calls=calls,
  exact_all24_output_bytes_match_old_and_integer_model=True,radius16_boolean_wrap_and_normalization_checked=True,
  all16NZCV_noisy_R1_R2_R3_R12_checked=True,PCS_R4_R11_SP_PC_and_bounded_struct_stack_writes=True,
  actual_four_class_costs={str(k):v for k,v in costs.items()},class_counts=dict(hist),peak_with_helper=dict(control=68,candidate=60),
  no_firmware_ROM_or_arithmetic_models=True,MPFR_inputs=0,device_IO=0))
def equal(a,b):return bool((a&0x7fffffffffffffff)>0x7ff0000000000000 and a&(1<<51))if (b&0x7fffffffffffffff)>0x7ff0000000000000 else a==b
def public():
 # Reuse only the reviewed table-parent loader definition, by exact AST.
 parent_script=R/'.build/m0-pow-exp-table-product-independent-20261025/arm.py'
 tree=ast.parse(parent_script.read_text());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='machine')
 tablebase=R/'.build/m0-pow-exp-table-product-20261025';tableim=ElfImage(tablebase/'candidate.elf')
 def memory(im,a,n):
  s=next(s for s in im.sections if s[1]!=8 and s[3]<=a and a+n<=s[3]+s[5]);return im.bytes_at(s)[a-s[3]:a-s[3]+n]
 env=dict(R=R,W=tablebase,Machine=Machine,ElfImage=ElfImage,entry=tableim.symbols['mk61_m0_pow_exp_table_product']&~1,im=tableim,memory=memory)
 exec(compile(ast.Module(body=[node],type_ignores=[]),'<accepted-table-parent-loader-only>','exec'),env)
 machines={}
 for label in ['parent','control','candidate']:
  m=env['machine']('candidate')
  if label!='parent':ElfImage(W/(label+'.elf')).load(m.uc)
  machines[label]=m
 machines['Qfplib']=env['machine']('Qfplib');traces={n:[]for n in ['parent','control','candidate']}
 for label,m in machines.items():
  if label=='Qfplib':continue
  def trace(uc,pc,size,_,label=label):
   ptr=uc.reg_read(UC_ARM_REG_R0);h,l,e,r=struct.unpack('<QQII',uc.mem_read(ptr,24));_,upper=model(h,l,e,r)
   old,new=costs[bool(l),upper];traces[label].append(dict(high=f'{h:016X}',low=f'{l:016X}',exponent=e,radius=r,old_cost=old,new_cost=new))
  m.uc.hook_add(UC_HOOK_CODE,trace,begin=entry,end=entry)
 jobs={}
 def add(x,y,group):jobs.setdefault((int(x,16)if isinstance(x,str)else x,int(y,16)if isinstance(y,str)else y),group)
 for x,y in json.loads((W/'qualification.json').read_text())['fixed_pair_values']:add(x,y,'all3old_corpus_fixes')
 original=json.loads((W/'original153.json').read_text())['rows'];original_fixes={}
 for row in original:
  if any(s['parent']>s['Qfplib']for s in row['states'])and all(s['candidate']<s['Qfplib']for s in row['states']):
   add(row['x'],row['y'],'original153newfix');original_fixes[row['x'],row['y']]=row['reference']
 fresh=json.loads((W/'new-qualification.json').read_text())['rows'];classes=set()
 for row in fresh:
  for c in row['square_calls']:
   key=c['old_cost'],c['new_cost']
   if key not in classes:add(row['x'],row['y'],'each_kernel_cost_class');classes.add(key)
 for row in sorted(fresh,key=lambda r:r['instructions']['parent'],reverse=True)[:4]:add(row['x'],row['y'],'deep_refinement_control')
 for row in original[:5]:add(row['x'],row['y'],'unchanged_original_control')
 for x,y in [(bits(1.),0x7ff0000000000001),(0xfff0000000000001,bits(0.)),(bits(-2.),bits(.5)),(bits(-2.),bits(3.)),(1,bits(.5)),(0,0),(bits(1.5),bits(.125))]:add(x,y,'IEEE_or_nonroute_control')
 refs=['qfp_composed_pow','qfp_composed_pow_exact','qfp_composed_pow_integer'];states=dict(READY=struct.pack('<7I',0,0,0,0,0,0,1),DIRTY=struct.pack('<7I',17,3,17,3,5,2,3));oracle=Oracle();rows=[];calls=shortcuts=0;class_seen=set()
 for j,((x,y),group)in enumerate(jobs.items()):
  expected=oracle.reference('pow',x,y);shortcuts+=any((v&0x7fffffffffffffff)>0x7ff0000000000000 and not v&(1<<51)for v in [x,y])
  for state_name,state in states.items():
   outputs={};counts={};correct={}
   for t in traces.values():t.clear()
   for label in ['parent','control','candidate',*refs]:
    m=machines[label if label in machines else 'Qfplib'];m.uc.mem_write(0xd0000060,state)
    got,_,count=m.call(label if label in refs else '_ZN12compact_math3powEdd',x,y,count=True);calls+=1
    after=bytes(m.uc.mem_read(0xd0000060,28));assert after==state if state_name=='DIRTY'else not struct.unpack('<7I',after)[6]&2
    outputs[label]=f'{got:016X}';counts[label]=count;correct[label]=equal(got,expected)
    if label not in refs:assert correct[label],(x,y,label,hex(got),hex(expected))
   assert outputs['parent']==outputs['control']==outputs['candidate']and counts['parent']==counts['control']
   assert traces['parent']==traces['control']==traces['candidate']
   delta=sum(t['new_cost']-t['old_cost']for t in traces['candidate']);assert counts['candidate']==counts['parent']+delta and delta<=0
   class_seen.update((t['old_cost'],t['new_cost'])for t in traces['candidate'])
   pair=f'{x:016X}',f'{y:016X}'
   if pair in original_fixes:
    q=original_fixes[pair];assert correct[q]and counts['candidate']<counts[q]<counts['parent']
   rows.append(dict(x=pair[0],y=pair[1],group=group,SIO=state_name,expected=f'{expected:016X}',outputs=outputs,instructions=counts,correct=correct,square_calls=list(traces['candidate'])))
  if j%16==0:print('bounded-square-public',j,'/',len(jobs),flush=True)
 assert len(class_seen)==4 and len(original_fixes)==1
 save('public-arm-mpfr.json',dict(status='PASS_BOUNDED_PUBLIC_EXACT_KERNEL_COST_AND_BITS',unique_pairs=len(jobs),qualified_calls=calls,
  directed_MPFR_inputs=len(jobs)-shortcuts,sNaN_shortcuts=shortcuts,strict_quietNaN_policy=True,MPFR_version=oracle.version,
  all3_Qfplib_compositions_and_wrong_outputs_retained=True,exact_parent_control_candidate_bits=True,all_actual_kernel_input_sequences_equal=True,
  all_four_cost_classes_actual=True,cost_delta_is_sum_of_kernel_deltas=True,original_newfix_strict_bothSIO=True,
  observed_stack_bytes={n:SP-m.stack_lowest for n,m in machines.items()},parent_loader=ref(parent_script),
  ROM_initializer_calls_excluded=True,no_general_pow_totality_or_other_math_qualification=True,device_IO=0,rows=rows))
if __name__=='__main__':
 assert len(sys.argv)==2 and sys.argv[1]in ['bare','public'];globals()[sys.argv[1]]()
