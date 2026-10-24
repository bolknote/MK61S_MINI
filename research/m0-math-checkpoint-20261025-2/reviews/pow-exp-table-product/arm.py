"""Bounded CPU-only Thumb/MPFR review; no physical interfaces or new campaign."""
import hashlib,json,math,random,struct,sys
from collections import Counter
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-exp-table-product-20261025';SUP=R/'.build/m0-float-fma-qualification-20261023/support'
sys.path[:0]=[str(SUP),str(R/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP,bits
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R12,UC_ARM_REG_XPSR,UC_ARM_REG_SP
def ref(p):p=Path(p);d=p.read_bytes();return dict(path=str(p),bytes=len(d),sha256=hashlib.sha256(d).hexdigest())
def save(n,d):
 with (O/n).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
 print(json.dumps(ref(O/n)),flush=True)
def memory(im,a,n):
 s=next(s for s in im.sections if s[1]!=8 and s[3]<=a and a+n<=s[3]+s[5]);return im.bytes_at(s)[a-s[3]:a-s[3]+n]
im=ElfImage(W/'candidate.elf');roots=struct.unpack('<512Q',memory(im,im.symbols['_ZN7m0_eabiL9exp_tableE'],4096));rootset=set(roots)
old=im.symbols['mk61_m0_pow_exp_product']&~1;entry=im.symbols['mk61_m0_pow_exp_table_product']&~1;wrapper=im.symbols['mk61_m0_pow_exp_table_product_flash']&~1
def bare():
 m=Machine(W/'candidate.elf',True);state=dict(pc=0,flags=0);calls=0;hist=Counter();lowest=SP
 def audit(uc,pc,size,_):
  nonlocal lowest
  assert old<=pc<old+154 or entry<=pc<entry+20 or wrapper<=pc<wrapper+16
  if pc==state['pc']:
   uc.reg_write(UC_ARM_REG_XPSR,0x01000000|(state['flags']<<28));uc.reg_write(UC_ARM_REG_R12,0xBAD02500|state['flags'])
  lowest=min(lowest,uc.reg_read(UC_ARM_REG_SP))
 m.uc.hook_add(UC_HOOK_CODE,audit)
 def call(name,a,b):
  nonlocal calls
  state['pc']=m.elf.symbols[name]&~1
  got,_,cost=m.call(name,a,b,count=True);calls+=1
  return got,cost,m.uc.reg_read(UC_ARM_REG_R12)
 def pair(a,b):
  before=call('mk61_m0_pow_exp_product',a,b);after=call('mk61_m0_pow_exp_table_product',a,b)
  assert before[0]==after[0]and before[1]==77 and after[1]==(10 if a==1<<62 else 79)
  if a!=1<<62:assert before[2]==after[2]
  else:assert after[0]==(b>>2)+bool(b&2)
  if b<1<<54:assert abs((after[0]<<64)-a*b)<=((1<<63)+(1<<49))
  hist[after[1]]+=1
 for a in roots:pair(a,(1<<54)-1)
 for b in [0,1,2,3,4,(1<<32)-2,(1<<32)-1,1<<32,(1<<32)+1,(1<<63)-1,(1<<64)-3,(1<<64)-2,(1<<64)-1]:pair(1<<62,b)
 for flags in range(16):
  state['flags']=flags
  for i in [0,1,255,511]:
   for b in [2,(1<<64)-1]:pair(roots[i],b)
 for i in [0,1,511]:
  for b in [0,2,(1<<54)-1,(1<<64)-1]:
   v=call('mk61_m0_pow_exp_table_product_flash',roots[i],b)
   assert v[1]==(15 if i==0 else 84)
   direct=call('mk61_m0_pow_exp_table_product',roots[i],b);assert v[0]==direct[0]
 assert SP-lowest==36 and not m.rom_models and not m.rom_initializers
 save('bare-arm.json',dict(status='PASS_BOUNDED_ACTUAL_TABLE_KERNEL_AND_WRAPPER_ARM',qualified_calls=calls,all512_roots_actual=True,
  all16NZCV_on4roots2Bvalues=True,dyadic_full64_edges=True,gate_instruction_histogram=dict(hist),wrapper5instructions=True,
  generic_extra_R12_matches_original=True,dyadic_R12_not_part_of_ABI=True,observed_frame36=True,PCS_SP_PC_boundedwrites_checked=True,
  active_PC_ranges_restricted=True,device_IO=0,MPFR_inputs=0))
states=dict(READY=struct.pack('<7I',0,0,0,0,0,0,1),DIRTY=struct.pack('<7I',17,3,17,3,5,2,3))
def machine(label):
 if label=='Qfplib':return Machine(R/'.build/m0-v138-execution-20261023/reference/reference.elf',True,instruction_budget=4000000)
 m=Machine(R/'.build/m0-asin-scaled-bound-v164-20261023/firmware/mk61s-picocalc-pico-h.elf',True,instruction_budget=4000000,
           bootrom=R/'research/rp2040-memset-2026-10-21/capture/bootrom.bin')
 for folder in ['m0-exp-cached-product-20261024','m0-pow-square-ordinary-20261024','m0-pow-rsqrt-asm-20261024']:
  e=ElfImage(R/'.build'/folder/'candidate.elf');e.load(m.uc);m.elf.symbols.update({n:a for n,a in e.symbols.items()if n.startswith('mk61_m0_pow_')})
 # Accepted general C77 is loaded before the selected new whole scratch bank.
 e=ElfImage(R/'.build/m0-exp-directed-product-20261024/candidate.elf');s=e.named_sections['.product_ram'];m.uc.mem_write(s[3],e.bytes_at(s))
 if label!='parent':
  e=ElfImage(W/(label+'.elf'));e.load(m.uc);m.elf.symbols.update({n:a for n,a in e.symbols.items()if n.startswith('mk61_m0_pow_')})
 if label=='candidate':assert bytes(m.uc.mem_read(entry,20))==memory(im,entry,20)
 assert not m.rom_models
 return m
def equal(a,b):return bool((a&0x7fffffffffffffff)>0x7ff0000000000000 and a&(1<<51))if (b&0x7fffffffffffffff)>0x7ff0000000000000 else a==b
def public():
 machines={n:machine(n)for n in ['parent','control','candidate','Qfplib']};oracle=Oracle();jobs={};products=[]
 def add(x,y,group):jobs.setdefault((int(x,16)if isinstance(x,str)else x,int(y,16)if isinstance(y,str)else y),group)
 oldmeta=json.loads((W/'old-qualification.json').read_text());fixes={tuple(pair)for pair in oldmeta['fixed_pair_values']}
 original=json.loads((W/'original153.json').read_text())['rows'];original_refs={(r['x'],r['y']):r['reference']for r in original}
 for x,y in sorted(fixes):add(x,y,'all13new_original_fixes')
 for name in ['qfp_composed_pow','qfp_composed_pow_exact','qfp_composed_pow_integer']:
  for row in [r for r in original if r['reference']==name][:3]:add(row['x'],row['y'],'each_original_reference_kind')
 for i in [0,1,2,127,255,256,510,511]:
  for sign in [-1,1]:add(bits(1.5),bits(sign*(i+0.125)/(512*math.log2(1.5))),'selected_table_centers')
 special=[(0,0),(1<<63,bits(3.)),(1,bits(.5)),(0x7fefffffffffffff,bits(-.5)),(bits(-2.),bits(3.)),(bits(-2.),bits(.5)),
  (0x7ff0000000000000,bits(-1.)),(bits(1.),0x7ff0000000000001),(0xfff0000000000001,bits(0.)),(bits(-1.),0x7ff8000012345678)]
 for x,y in special:add(x,y,'IEEE_boundary')
 fresh=json.loads((W/'new-qualification.json').read_text())['rows']
 for row in sorted(fresh,key=lambda r:r['instructions']['parent'],reverse=True)[:6]:add(row['x'],row['y'],'large_refinement_control')
 for row in fresh:
  if row['instructions']['candidate']>row['instructions']['parent']and row['group']!='repeat_pilot_excluded_from_pilot_counts':add(row['x'],row['y'],'retained_plus2_control');break
 def hook(uc,pc,size,_):
  a=uc.reg_read(UC_ARM_REG_R0)|(uc.reg_read(UC_ARM_REG_R1)<<32);b=uc.reg_read(UC_ARM_REG_R2)|(uc.reg_read(UC_ARM_REG_R3)<<32)
  products.append(dict(kind='table'if pc==entry else 'general',a=f'{a:016X}',b=f'{b:016X}'))
 for address in [old,entry]:machines['candidate'].uc.hook_add(UC_HOOK_CODE,hook,begin=address,end=address)
 refs=['qfp_composed_pow','qfp_composed_pow_exact','qfp_composed_pow_integer'];rows=[];calls=snans=0;seen=set()
 for j,((x,y),group)in enumerate(jobs.items()):
  expected=oracle.reference('pow',x,y);snans+=any((v&0x7fffffffffffffff)>0x7ff0000000000000 and not v&(1<<51)for v in [x,y])
  for state_name,state in states.items():
   outputs={};costs={};correct={};products.clear()
   for label in ['parent','control','candidate',*refs]:
    m=machines[label if label in machines else 'Qfplib'];m.uc.mem_write(0xd0000060,state)
    got,_,cost=m.call(label if label in refs else '_ZN12compact_math3powEdd',x,y,count=True);calls+=1
    after=bytes(m.uc.mem_read(0xd0000060,28));assert after==state if state_name=='DIRTY'else not struct.unpack('<7I',after)[6]&2
    outputs[label]=f'{got:016X}';costs[label]=cost;correct[label]=equal(got,expected)
    if label not in refs:assert correct[label],(hex(x),hex(y),label,hex(got),hex(expected))
   assert outputs['parent']==outputs['control']==outputs['candidate']and costs['parent']==costs['control']
   table_calls=[p for p in products if p['kind']=='table'];assert all(int(p['a'],16)in rootset for p in table_calls)
   seen.update(int(p['a'],16)for p in table_calls);d=sum(int(p['a'],16)==1<<62 for p in table_calls);g=len(table_calls)-d
   assert costs['candidate']-costs['control']==2*g-67*d
   pair=f'{x:016X}',f'{y:016X}'
   if pair in fixes:
    q=original_refs[pair];assert correct[q]and costs['candidate']<costs[q]<costs['parent']
   rows.append(dict(x=pair[0],y=pair[1],group=group,SIO=state_name,expected=f'{expected:016X}',outputs=outputs,instructions=costs,correct=correct,products=list(products)))
  if j%32==0:print('bounded-pow',j,'/',len(jobs),flush=True)
 assert len(fixes)==13
 save('public-arm-mpfr.json',dict(status='PASS_BOUNDED_REAL_PUBLIC_POW_ALL3_REFERENCES',unique_pairs=len(jobs),qualified_calls=calls,
  directed_MPFR_inputs=len(jobs)-snans,sNaN_shortcuts=snans,MPFR_version=oracle.version,all13_original_fixes_strict_bothSIO=True,
  all3_real_Qfplib_compositions_retained=True,parent_control_costs_bits_identical=True,candidate_bits_unchanged=True,
  exact_cost_law_verified=True,table_rows_seen=len(seen),PCS_R4_R11_SP_PC_and_SIO28_checked=True,
  observed_stack_bytes={n:SP-m.stack_lowest for n,m in machines.items()},ROM_initializers_excluded_from_calls=True,
  no_new_other_math_qualification=True,device_IO=0,rows=rows))
if __name__=='__main__':
 assert len(sys.argv)==2 and sys.argv[1]in ['bare','public'];globals()[sys.argv[1]]()
