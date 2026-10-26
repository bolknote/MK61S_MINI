"""Bounded inline-unit, real live-context and IEEE overflow CPU checks."""
import ast,hashlib,json,random,struct,sys
from collections import Counter
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-reciprocal-inline-20261025';P=R/'.build/m0-pow-reciprocal-one-20261025'
SUP=R/'.build/m0-float-fma-qualification-20261023/support';sys.path[:0]=[str(SUP),str(R/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP,STOP,bits
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R12,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_XPSR
RAW=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3];LIVE=[*RAW,UC_ARM_REG_R5,UC_ARM_REG_R12,UC_ARM_REG_SP]
AFTER=[*RAW,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R12,UC_ARM_REG_SP,UC_ARM_REG_XPSR]
states=dict(READY=struct.pack('<7I',0,0,0,0,0,0,1),DIRTY=struct.pack('<7I',17,3,17,3,5,2,3))
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def save(n,d):
 with (O/n).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
 print(json.dumps(ref(O/n)),flush=True)
def memory(e,a,n):
 s=next(s for s in e.sections if s[1]!=8 and s[3]<=a and a+n<=s[3]+s[5]);return e.bytes_at(s)[a-s[3]:a-s[3]+n]
def equal(a,b):return bool((a&0x7fffffffffffffff)>0x7ff0000000000000 and a&(1<<51))if (b&0x7fffffffffffffff)>0x7ff0000000000000 else a==b
for name in ['inline_saved','expected']:
 fn=next(n for n in ast.parse((O/'accounting.py').read_text()).body if isinstance(n,ast.FunctionDef)and n.name==name)
 exec(compile(ast.Module(body=[fn],type_ignores=[]),'<independent-pure-cost-law>','exec'),globals())
def unit():
 m=Machine(O/'rebuild/unit.elf',True);old=Machine(R/'.build/m0-ddiv-seed-lut-20261025/lut128_floor.elf',True)
 assert not m.rom_models and not m.rom_initializers and not old.rom_models and not old.rom_initializers
 pe=ElfImage(P/'candidate.elf');assert memory(old.elf,old.elf.symbols['mk61_m0_ddiv_seed17']&~1,312)==memory(pe,pe.symbols['mk61_m0_ddiv_seed17']&~1,312)
 begin=m.elf.symbols['mk61_m0_inline_seed_begin']&~1;done=m.elf.symbols['mk61_m0_inline_seed_done']&~1;table=int(json.loads((O/'proof.json').read_text())['mapping']['unit']['table'],16)
 active={};readcount=0;rng=random.Random(0x1A11E025);rows=[]
 def code(uc,pc,n,user):
  if pc==begin:
   uc.reg_write(UC_ARM_REG_XPSR,0x01000000|(active['flags']<<28));uc.reg_write(UC_ARM_REG_R5,active['r5']);uc.reg_write(UC_ARM_REG_R12,active['r12'])
   active['before']=[uc.reg_read(r)for r in LIVE];active['frame']=bytes(uc.mem_read(SP-20,20))
  if pc==done:
   assert [uc.reg_read(r)for r in LIVE]==active['before']and uc.reg_read(UC_ARM_REG_SP)==SP-20
   assert bytes(uc.mem_read(SP-20,20))==active['frame']and uc.reg_read(UC_ARM_REG_R6)==0xffffffff//active['D']and uc.reg_read(UC_ARM_REG_R7)==0xffffffff%active['D']
 def write(uc,access,a,n,v,user):
  pc=uc.reg_read(UC_ARM_REG_PC);assert not begin<=pc<done and SP-20<=a and a+n<=SP
 def read(uc,access,a,n,v,user):
  nonlocal readcount
  if begin<=uc.reg_read(UC_ARM_REG_PC)<done:
   assert a==table+2*((active['D']>>9)-128)and n==2;readcount+=1
 m.uc.hook_add(UC_HOOK_CODE,code);m.uc.hook_add(UC_HOOK_MEM_WRITE,write);m.uc.hook_add(UC_HOOK_MEM_READ,read)
 jobs=[]
 for i in [0,1,63,64,126,127]:
  for off in [0,1,510,511]:
   for f in range(16):jobs.append((65536+512*i+off,f))
 jobs +=[(D,i&15)for i,D in enumerate(json.loads((O/'adversarial-D.json').read_text())['values'].values())]
 for D,flags in jobs:
  active.update(D=D,flags=flags,r5=rng.getrandbits(32),r12=rng.getrandbits(32));readcount=0;a=rng.getrandbits(32)|(D<<32);b=rng.getrandbits(64)
  got,_,_=m.call('unit_inline_seed',a,b,count=True);prior,_,_=old.call('mk61_m0_ddiv_seed17',a,b,count=True)
  assert got&0xffffffff==prior&0xffffffff==0xffffffff//D and readcount==1
  rows.append(dict(D=D,flags=flags,quotient=got&0xffffffff,preserved_context=active['before']))
 save('unit-arm.json',dict(status='PASS_BOUNDED_SHARED_INLINE_MACRO_LIVE_CONTEXT',tests=len(jobs),actual_ARM_calls=2*len(jobs),
  all16NZCV_each24_table_edges_plus5_error_classes=True,R0_R1_R2_R3_R5_R12_SP_preserved=True,quotient_R6_and_residual_R7_exact=True,
  no_inline_stack_or_memory_writes=True,one_aligned_table_LDRH=True,unit20B_wrapper_not_production_stack_or_speed_claim=True,
  no_firmware_ROM_or_models=True,rows=rows,device_IO=0))
def loader():
 t=R/'.build/m0-pow-exp-table-product-20261025';im=ElfImage(t/'candidate.elf');te=im.symbols['mk61_m0_pow_exp_table_product']&~1
 fn=next(n for n in ast.parse((R/'.build/m0-pow-exp-table-product-independent-20261025/arm.py').read_text()).body if isinstance(n,ast.FunctionDef)and n.name=='machine');env=dict(R=R,W=t,im=im,entry=te,Machine=Machine,ElfImage=ElfImage,memory=memory)
 exec(compile(ast.Module(body=[fn],type_ignores=[]),'<accepted-table-loader>','exec'),env);machines={}
 for label in ['parent','control','candidate','Qfplib']:
  m=env['machine']('Qfplib'if label=='Qfplib'else'candidate')
  if label!='Qfplib':
   for folder in ['m0-pow-square128-r2-20261025','m0-pow-boundary128-20261025']:ElfImage(R/'.build'/folder/'candidate.elf').load(m.uc)
   e=ElfImage(P/'candidate.elf'if label=='parent'else O/'rebuild'/(label+'.elf'));e.load(m.uc)
   m.elf.symbols.update({n:a for n,a in e.symbols.items()if n.startswith(('mk61_m0_reciprocal1','mk61_m0_ddiv_seed','mk61_m0_inline'))})
   assert bytes(m.uc.mem_read(te,20))==memory(im,te,20)
  machines[label]=m
 return machines
def audit(m,label,active):
 e=ElfImage(O/'rebuild'/(label+'.elf'));candidate=label=='candidate';entry=e.symbols['mk61_m0_reciprocal1']&~1;sw=e.symbols['mk61_m0_reciprocal1_sw_from_guard']&~1
 tags=['mk61_m0_reciprocal1','mk61_m0_reciprocal1_sw'];firsts={e.symbols[t+'_first_product']&~1 for t in tags};afters={e.symbols[t+'_after_second_product']&~1 for t in tags}
 begin=e.symbols['mk61_m0_inline_seed_begin'if candidate else'mk61_m0_ddiv_seed17']&~1;done=e.symbols['mk61_m0_inline_seed_done']&~1 if candidate else 0
 table=int(json.loads((O/'proof.json').read_text())['mapping']['production']['table'],16)if candidate else 0
 out={};cur={};tick=0
 def clear():out.update(calls=[],first=[],after=[],seeds=[],inline=[],pops=[],returns=[],latency9=[]);cur.clear()
 def code(uc,pc,n,user):
  nonlocal tick
  tick+=1
  if cur and pc==cur['return']:
   assert uc.reg_read(UC_ARM_REG_SP)==cur['sp'];out['returns'].append(pc);cur['returned']=True
  if pc==entry:
   raw=[uc.reg_read(r)for r in RAW];assert raw[:2]==[0,0x3ff00000];sp=uc.reg_read(UC_ARM_REG_SP);assert sp%8==0
   ret=uc.reg_read(UC_ARM_REG_LR)&~1;assert ret==(0x1014e668+2732+4 if active['public']else STOP)
   cur.clear();cur.update(raw=raw,sp=sp,saved=[uc.reg_read(r)for r in [UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_LR]],return_=ret);cur['return']=ret
   out['calls'].append(dict(numerator='3FF0000000000000',denominator=f'{raw[2]|(raw[3]<<32):016X}',entry_SP=sp,return_site=hex(ret)))
   if not active['public']:uc.reg_write(UC_ARM_REG_XPSR,0x01000000|(active['flags']<<28));uc.reg_write(UC_ARM_REG_R12,0xc0251020|active['flags'])
  if pc==sw:
   raw=cur['raw'];E=(raw[3]>>20)&2047;assert 1<=E<=2044 and uc.reg_read(UC_ARM_REG_R6)==2044-E and [uc.reg_read(r)for r in RAW]==raw
   assert uc.reg_read(UC_ARM_REG_SP)==cur['sp']-20
  if pc==begin:
   raw=cur['raw'];E=(raw[3]>>20)&2047;sp=uc.reg_read(UC_ARM_REG_SP);D=uc.reg_read(UC_ARM_REG_R1)
   assert D==((raw[3]&0xfffff)|0x100000)>>4 and 65536<=D<131072 and uc.reg_read(UC_ARM_REG_R12)==4*(2044-E)+(raw[3]>>31)
   out['seeds'].append(D)
   if candidate:
    assert sp==cur['sp']-20 and bytes(uc.mem_read(sp,20))==struct.pack('<5I',*cur['saved'])
    assert uc.reg_read(UC_ARM_REG_R0)==0 and uc.reg_read(UC_ARM_REG_R2)==raw[2]and uc.reg_read(UC_ARM_REG_R3)==((raw[3]&0xfffff)|0x100000)
    cur['inline_live']=[uc.reg_read(r)for r in LIVE];cur['inline_D']=D;cur['reads']=0
   else:
    assert sp==cur['sp']-40 and sp%8==0
    assert bytes(uc.mem_read(sp,20))==struct.pack('<5I',0,0x3ff00000,raw[2],(raw[3]&0xfffff)|0x100000,raw[3]>>31)
  if candidate and pc==done:
   assert [uc.reg_read(r)for r in LIVE]==cur['inline_live']and cur['reads']==1
   assert uc.reg_read(UC_ARM_REG_R6)==0xffffffff//cur['inline_D']and uc.reg_read(UC_ARM_REG_R7)==0xffffffff%cur['inline_D']
   assert bytes(uc.mem_read(cur['sp']-20,20))==struct.pack('<5I',*cur['saved'])
   out['inline'].append(dict(entry_SP=cur['sp'],inline_SP=uc.reg_read(UC_ARM_REG_SP),D=cur['inline_D'],live=cur['inline_live'],quotient=uc.reg_read(UC_ARM_REG_R6)))
  if pc in firsts:assert uc.reg_read(UC_ARM_REG_R0)==0;out['first'].append(uc.reg_read(UC_ARM_REG_R6))
  if pc in afters:
   sp=uc.reg_read(UC_ARM_REG_SP);assert sp==cur['sp']-28;v=[uc.reg_read(r)for r in AFTER];v[-1]&=0xf0000000;out['after'].append(dict(registers=v,frame=bytes(uc.mem_read(sp,28)).hex()))
  if cur and 0x101e1000<=pc<e.named_sections['.ddiv'][3]+e.named_sections['.ddiv'][5]and bytes(uc.mem_read(pc,2))==bytes.fromhex('f0bd'):
   sp=uc.reg_read(UC_ARM_REG_SP);assert sp==cur['sp']-20 and bytes(uc.mem_read(sp,20))==struct.pack('<5I',*cur['saved']);out['pops'].append(hex(cur['return']))
 def write(uc,access,a,n,v,user):
  pc=uc.reg_read(UC_ARM_REG_PC)
  if candidate:assert not begin<=pc<done
  if cur and not cur.get('returned')and 0xd0000060<=a<0xd000007c:
   assert active['state']!='DIRTY'
   if a==0xd0000064:cur['issue']=tick
 def read(uc,access,a,n,v,user):
  pc=uc.reg_read(UC_ARM_REG_PC)
  if candidate and begin<=pc<done:assert a==table+2*((cur['inline_D']>>9)-128)and n==2;cur['reads']+=1
  if cur and not cur.get('returned')and 0xd0000060<=a<0xd000007c:
   if active['state']=='DIRTY':assert a==0xd0000078
   if a==0xd0000070:assert tick-cur['issue']-1==9;out['latency9'].append(9)
 m.uc.hook_add(UC_HOOK_CODE,code);m.uc.hook_add(UC_HOOK_MEM_READ,read);m.uc.hook_add(UC_HOOK_MEM_WRITE,write);clear();return out,clear
def scalar():
 machines=loader();active=dict(public=False);traces={n:audit(machines[n],n,active)for n in ['control','candidate']};selection=json.loads((O/'scalar-selection.json').read_text());jobs={}
 def add(b,f,g):jobs.setdefault((b,f),g)
 T=1<<50
 for mag in [0,1,T-2,T-1,T,T+1,T+2,(1<<52)-1]:
  for sign in [0,1]:
   for f in range(16):add(mag|(sign<<63),f,'signed_threshold_edges_all16flags')
 for s in selection['remaining_denominators']:
  for f in range(16):add(int(s,16),f,'all_remaining13loss_states_unique9denominators')
 for E in [1,2044,2045,2046,2047]:
  for sign in [0,1]:add((E<<52)|123|(sign<<63),E&15,'normal_special_guard_classes')
 for b in [0x7ff0000000000000,0xfff0000000000000,0x7ff0000000000001,0xfff0000000000001,0x7ff8000000000000,0xfff8000000000000,bits(1.),bits(1.125),bits(1.5),bits(2.)]:add(b,0,'IEEE_and_dyadic')
 for delta,r in selection['increase_examples'].items():add(int(r['denominator'],16),r['NZCV'],'retained_parent_slowdown'+delta)
 oracle=Oracle();cache={};shortcuts=calls=0;rows=[];increases=Counter();newdeficits=[]
 for (b,flags),group in jobs.items():
  if b not in cache:cache[b]=oracle.reference('ddiv',bits(1.),b);shortcuts+=bool((b&0x7fffffffffffffff)>0x7ff0000000000000 and not b&(1<<51))
  exp=cache[b]
  for state_name,state in states.items():
   active.update(state=state_name,flags=flags);results={};captures={}
   for label,m in machines.items():
    if label in traces:traces[label][1]()
    m.uc.mem_write(0xd0000060,state);got,_,cost=m.call('qfp_ddiv'if label=='Qfplib'else'mk61_m0_reciprocal1',bits(1.),b,count=True);calls+=1
    after=bytes(m.uc.mem_read(0xd0000060,28));assert after==state if state_name=='DIRTY'else not struct.unpack('<7I',after)[6]&2
    results[label]=dict(output=f'{got:016X}',instructions=cost,correct=equal(got,exp))
    if label in traces:captures[label]=json.loads(json.dumps(traces[label][0]));assert len(captures[label]['calls'])==len(captures[label]['pops'])==1
   assert results['parent']==results['control']and results['candidate']['output']==results['parent']['output']and all(results[n]['correct']for n in ['parent','control','candidate'])
   co,ca=captures['control'],captures['candidate'];assert co['first']==ca['first']and co['after']==ca['after']and co['seeds']==ca['seeds']
   pc,c=results['parent']['instructions'],results['candidate']['instructions'];assert c==expected(b,pc,len(ca['first']),ca['seeds'])
   if c>pc:increases[c-pc]+=1
   if results['Qfplib']['correct']and c>results['Qfplib']['instructions']and pc<=results['Qfplib']['instructions']:newdeficits.append(dict(b=f'{b:016X}',SIO=state_name))
   rows.append(dict(denominator=f'{b:016X}',flags=flags,group=group,SIO=state_name,expected=f'{exp:016X}',results=results,captures=captures))
 assert set(increases)=={2,8,11}
 save('scalar-arm-mpfr.json',dict(status='PASS_BOUNDED_SIGNED_OVERFLOW_INLINE_LIVE_CONTEXT_AND_RETAINED_SLOWDOWNS',flag_jobs=len(jobs),distinct_denominators=len(cache),actual_ARM_calls=calls,
  directed_MPFR_inputs=len(cache)-shortcuts,sNaN_shortcuts=shortcuts,oracle_cache_per_denominator=True,MPFR_version=oracle.version,
  threshold_Tplusminus2_zero_min_maxsubnormal_bothsign16NZCV=True,all_remaining_denominators_included=True,
  production_inline_preserves_live_R0_R1_R2_R3_R5_R12_and_SP_ownentryminus20=True,old_seedBL8aligned=True,no_inline_stackwrites_or_calls=True,
  after_second_full_state_and_frame28_equal=True,READY9ALU_SIO_and_return_original20B_frame_checked=True,
  observed_parent_cost_increases=dict(increases),all_parent_increases_and_wrong_Qfplib_raws_retained=True,new_correct_Qfp_deficits_in_bounded_set=newdeficits,
  no_universal_parent_or_Qfp_speed_claim=True,observed_stack_bytes={n:SP-m.stack_lowest for n,m in machines.items()},rows=rows,device_IO=0))
def public():
 machines=loader();active=dict(public=True);traces={n:audit(machines[n],n,active)for n in ['control','candidate']};jobs={}
 for r in json.loads((O/'selected-public-jobs.json').read_text())['jobs']:jobs[int(r['x'],16),int(r['y'],16)]=r['group']
 for a,b in [(0,0),(1,bits(.5)),(bits(-2.),bits(.5)),(0x7fefffffffffffff,bits(-.5)),(bits(1.),0x7ff0000000000001),(0xfff0000000000001,bits(0.))]:jobs[a,b]='IEEE_and_sNaN_control'
 refs=['qfp_composed_pow','qfp_composed_pow_exact','qfp_composed_pow_integer'];oracle=Oracle();rows=[];calls=shortcuts=0
 selected=json.loads((O/'selected-public-jobs.json').read_text());fixed={tuple(p)for p in selected['strict_fixed_pair']};equality=selected['separate_equal_transition'][0];up_seen=False
 for (a,b),group in jobs.items():
  exp=oracle.reference('pow',a,b);shortcuts+=any((v&0x7fffffffffffffff)>0x7ff0000000000000 and not v&(1<<51)for v in [a,b])
  for state_name,state in states.items():
   active['state']=state_name;outputs={};costs={};correct={};captures={}
   for label in ['parent','control','candidate',*refs]:
    m=machines[label if label in machines else'Qfplib']
    if label in traces:traces[label][1]()
    m.uc.mem_write(0xd0000060,state);got,_,cost=m.call(label if label in refs else'_ZN12compact_math3powEdd',a,b,count=True);calls+=1
    after=bytes(m.uc.mem_read(0xd0000060,28));assert after==state if state_name=='DIRTY'else not struct.unpack('<7I',after)[6]&2
    outputs[label]=f'{got:016X}';costs[label]=cost;correct[label]=equal(got,exp)
    if label not in refs:assert correct[label]
    if label in traces:captures[label]=json.loads(json.dumps(traces[label][0]))
   co,ca=captures['control'],captures['candidate'];assert outputs['parent']==outputs['control']==outputs['candidate']and costs['parent']==costs['control']
   assert co['calls']==ca['calls']and co['first']==ca['first']and co['after']==ca['after']and co['seeds']==ca['seeds']
   assert len(ca['calls'])==len(ca['pops'])==len(ca['returns'])
   saving=2*len(ca['first'])+sum(inline_saved(d)for d in ca['seeds']);assert costs['parent']-costs['candidate']==saving
   up_seen |= any(inline_saved(d)==5 for d in ca['seeds'])
   pair=f'{a:016X}',f'{b:016X}'
   if pair in fixed:assert all(costs['candidate']<costs[n]for n in refs if correct[n])
   if pair==(equality['x'],equality['y'])and state_name==equality['SIO']:assert costs['candidate']==costs[equality['reference']]and correct[equality['reference']]
   rows.append(dict(x=pair[0],y=pair[1],SIO=state_name,group=group,expected=f'{exp:016X}',outputs=outputs,instructions=costs,correct=correct,captures=captures))
 assert up_seen and any(v['entry_SP']!=SP for r in rows for v in r['captures']['candidate']['inline'])
 save('public-arm-mpfr.json',dict(status='PASS_BOUNDED_NESTED_INLINE_PRIVATE_CONTEXT_STRICT_FIX_AND_SEPARATE_EQUALITY',pairs=len(jobs),actual_ARM_calls=calls,
  directed_MPFR_inputs=len(jobs)-shortcuts,sNaN_shortcuts=shortcuts,MPFR_version=oracle.version,
  one_new_strict_pair_actually_reproduced=True,separate_reference_state_equality_reproduced_not_strict_win=True,one_up_extra_saving5_reproduced=True,
  nested_inlineSP_equals_ownentrySPminus20_not_outerMachineSP_checked=True,old_seedBL8align_only_old_context=True,
  macro_preserved_live_registers_frame20_and_after_second_full_state28=True,READY9ALU_and_all7DIRTY_SIO_preserved=True,
  every_positive1_root_entry_POP_and_actual_return_source_site_verified=True,actual_cost_sign2_and_inline4or5_every_case=True,
  all3_real_Qfplib_correct_wrong_outputs_costs_preserved=True,no_generic_ddiv_or_global_speed_claim=True,near_one_sibling_not_loaded=True,
  observed_stack_bytes={n:SP-m.stack_lowest for n,m in machines.items()},rows=rows,device_IO=0))
if __name__=='__main__':
 assert len(sys.argv)==2 and sys.argv[1]in ['unit','scalar','public'];globals()[sys.argv[1]]()
