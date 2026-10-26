"""Bounded complete1/x and public pow CPU checks; never a generic new ddiv."""
import ast,hashlib,json,struct,sys
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-reciprocal-one-20261025';P=R/'.build/m0-pow-reciprocal-lut-20261025'
SUP=R/'.build/m0-float-fma-qualification-20261023/support';sys.path[:0]=[str(SUP),str(R/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP,STOP,bits
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R12,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_XPSR
RAW=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3];REGS=[*RAW,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R12,UC_ARM_REG_SP,UC_ARM_REG_XPSR]
states=dict(READY=struct.pack('<7I',0,0,0,0,0,0,1),DIRTY=struct.pack('<7I',17,3,17,3,5,2,3))
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def save(n,d):
 with (O/n).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
 print(json.dumps(ref(O/n)),flush=True)
def memory(e,a,n):
 s=next(s for s in e.sections if s[1]!=8 and s[3]<=a and a+n<=s[3]+s[5]);return e.bytes_at(s)[a-s[3]:a-s[3]+n]
def equal(a,b):return bool((a&0x7fffffffffffffff)>0x7ff0000000000000 and a&(1<<51))if (b&0x7fffffffffffffff)>0x7ff0000000000000 else a==b
def guard(E):return 11 if 1<=E<=2044 else 12 if E in[2045,2046] else 5
def loader():
 table=R/'.build/m0-pow-exp-table-product-20261025';im=ElfImage(table/'candidate.elf');entry=im.symbols['mk61_m0_pow_exp_table_product']&~1
 fn=next(n for n in ast.parse((R/'.build/m0-pow-exp-table-product-independent-20261025/arm.py').read_text()).body if isinstance(n,ast.FunctionDef)and n.name=='machine')
 env=dict(R=R,W=table,im=im,entry=entry,Machine=Machine,ElfImage=ElfImage,memory=memory)
 exec(compile(ast.Module(body=[fn],type_ignores=[]),'<accepted-table-loader>','exec'),env);machines={}
 for label in ['parent','control','candidate','Qfplib']:
  m=env['machine']('Qfplib'if label=='Qfplib'else'candidate')
  if label!='Qfplib':
   for folder in ['m0-pow-square128-r2-20261025','m0-pow-boundary128-20261025']:ElfImage(R/'.build'/folder/'candidate.elf').load(m.uc)
   e=ElfImage(P/'candidate.elf'if label=='parent'else O/'rebuild'/(label+'.elf'));e.load(m.uc)
   m.elf.symbols.update({n:a for n,a in e.symbols.items()if n.startswith(('mk61_m0_hint','mk61_m0_ddiv_sw','mk61_m0_ddiv_seed','mk61_m0_sw_','mk61_m0_reciprocal1'))})
   name='mk61_m0_reciprocal1'if label=='candidate'else'mk61_m0_hint_ddiv'
   assert m.elf.symbols[name]==0x101e1041 and bytes(m.uc.mem_read(entry,20))==memory(im,entry,20)
  machines[label]=m
 return machines
def audit(m,label,active):
 e=ElfImage(O/'rebuild'/(label+'.elf'));candidate=label=='candidate';entry=e.symbols['mk61_m0_reciprocal1'if candidate else'mk61_m0_hint_ddiv']&~1
 sw=e.symbols['mk61_m0_reciprocal1_sw_from_guard'if candidate else'mk61_m0_ddiv_sw_from_guard']&~1;seed=e.symbols['mk61_m0_ddiv_seed17']&~1
 tags=['mk61_m0_reciprocal1','mk61_m0_reciprocal1_sw']if candidate else['mk61_m0_hint','mk61_m0_sw']
 firsts={e.symbols[t+'_first_product']&~1 for t in tags};afters={e.symbols[t+'_after_second_product']&~1 for t in tags};joins={e.symbols[t+'_join']&~1 for t in tags}
 out={};current={};tick=0
 def clear():
  out.update(calls=[],first=[],after=[],seeds=[],pops=[],return_sites=[],R3_restore=[],hardware_latency=[]);current.clear()
 def code(uc,pc,n,user):
  nonlocal tick
  tick+=1
  if current and pc==current['return']:
   assert uc.reg_read(UC_ARM_REG_SP)==current['sp'];out['return_sites'].append(pc);current['returned']=True
  if pc==entry:
   raw=[uc.reg_read(r)for r in RAW];assert raw[0]==0 and raw[1]==0x3ff00000
   ret=uc.reg_read(UC_ARM_REG_LR)&~1
   assert ret==(0x1014e668+2732+4 if active['public']else STOP)
   saved=[uc.reg_read(r)for r in [UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_LR]]
   current.clear();current.update(raw=raw,sp=uc.reg_read(UC_ARM_REG_SP),saved=saved,return_=ret);current['return']=ret
   out['calls'].append(dict(numerator='3FF0000000000000',denominator=f'{raw[2]|(raw[3]<<32):016X}',return_site=hex(ret)))
   if not active['public']:
    uc.reg_write(UC_ARM_REG_XPSR,0x01000000|(active['flags']<<28));uc.reg_write(UC_ARM_REG_R12,0xc1025000|active['flags'])
  if pc==sw:
   raw=current['raw'];E=(raw[3]>>20)&2047;exp=2044-E;sp=uc.reg_read(UC_ARM_REG_SP)
   assert 1<=E<=2044 and uc.reg_read(UC_ARM_REG_R6)==exp and [uc.reg_read(r)for r in RAW]==raw
   assert sp==current['sp']-20 and bytes(uc.mem_read(sp,20))==struct.pack('<5I',*current['saved'])
  if pc==seed:
   raw=current['raw'];E=(raw[3]>>20)&2047;sp=uc.reg_read(UC_ARM_REG_SP);D=uc.reg_read(UC_ARM_REG_R1)
   assert sp==current['sp']-40 and sp%8==0 and 1<=E<=2044
   assert D==((raw[3]&0xfffff)|0x100000)>>4 and 65536<=D<131072
   assert uc.reg_read(UC_ARM_REG_R0)==(0 if candidate else 0xffffffff)
   sign=raw[3]>>31;assert uc.reg_read(UC_ARM_REG_R12)==4*(2044-E)+sign
   temporary=(0,0x3ff00000 if candidate else 0x100000,raw[2],(raw[3]&0xfffff)|0x100000,sign)
   assert bytes(uc.mem_read(sp,20))==struct.pack('<5I',*temporary)
   current['seed_return']=uc.reg_read(UC_ARM_REG_LR)&~1;current['D']=D;current['saved_R3']=temporary[3];out['seeds'].append(D)
  if current and pc==current.get('seed_return'):
   assert uc.reg_read(UC_ARM_REG_R0)==0xffffffff//current['D']and uc.reg_read(UC_ARM_REG_R3)==0xffffffff%current['D']
   current['leaf_R3']=uc.reg_read(UC_ARM_REG_R3)
  if pc in joins and 'leaf_R3'in current:
   assert uc.reg_read(UC_ARM_REG_R3)==current['saved_R3']
   out['R3_restore'].append(dict(leaf=current['leaf_R3'],restored=current['saved_R3']))
  if pc in firsts:
   assert uc.reg_read(UC_ARM_REG_R0)==0
   if not candidate:assert uc.reg_read(UC_ARM_REG_R1)==0x100000 and uc.reg_read(UC_ARM_REG_R4)==0x80000000
   out['first'].append(uc.reg_read(UC_ARM_REG_R6))
  if pc in afters:
   sp=uc.reg_read(UC_ARM_REG_SP);assert sp==current['sp']-28
   values=[uc.reg_read(r)for r in REGS];values[-1]&=0xf0000000
   out['after'].append(dict(registers=values,frame=bytes(uc.mem_read(sp,28)).hex()))
  if current and 0x101e1000<=pc<seed and bytes(uc.mem_read(pc,2))==bytes.fromhex('f0bd'):
   sp=uc.reg_read(UC_ARM_REG_SP);assert sp==current['sp']-20 and bytes(uc.mem_read(sp,20))==struct.pack('<5I',*current['saved'])
   assert struct.unpack('<5I',uc.mem_read(sp,20))[-1]&~1==current['return'];out['pops'].append(dict(pc=hex(pc),return_site=hex(current['return'])))
 def write(uc,access,a,n,v,user):
  if current and not current.get('returned')and 0xd0000060<=a<0xd000007c:
   assert active['state']!='DIRTY'
   if a==0xd0000064:current['issue_tick']=tick
 def read(uc,access,a,n,v,user):
  if current and not current.get('returned')and 0xd0000060<=a<0xd000007c:
   if active['state']=='DIRTY':assert a==0xd0000078
   if a==0xd0000070:
    assert tick-current['issue_tick']-1==9;out['hardware_latency'].append(9)
 m.uc.hook_add(UC_HOOK_CODE,code);m.uc.hook_add(UC_HOOK_MEM_WRITE,write);m.uc.hook_add(UC_HOOK_MEM_READ,read);clear();return out,clear
def scalar():
 machines=loader();active=dict(public=False);audits={n:audit(machines[n],n,active)for n in ['control','candidate']};selection=json.loads((O/'scalar-loss-selection.json').read_text());jobs={}
 def add(b,f,g):jobs.setdefault((b,f),g)
 for s in selection['normal_denominators']:
  for flags in range(16):add(int(s,16),flags,'all_remaining9normal_losses_all16flags')
 for s in selection['all_denominators']:add(int(s,16),0,'all_remaining18unique_denominators')
 edges=[0,1,0xfffffffffffff,0x10000000000000,0x7fefffffffffffff,0x7ff0000000000000,0x7ff0000000000001,0x7ff8000000000000]
 for b in edges:
  for sign in [0,1]:
   for f in range(16):add(b|(sign<<63),f,'IEEE_edges_all16flags')
 for E in [1,2,2043,2044,2045,2046]:
  for sign in [0,1]:add((E<<52)|123|(sign<<63),E&15,'exact_exponent_guard_edges')
 for b in [bits(1.),bits(1.125),bits(1.5),bits(2.)]:add(b,0,'dyadic_special')
 oracle=Oracle();cache={};shortcuts=0;rows=[];calls=0;normal_witness={}
 for (b,flags),group in jobs.items():
  if b not in cache:
   cache[b]=oracle.reference('ddiv',bits(1.),b);shortcuts+=bool((b&0x7fffffffffffffff)>0x7ff0000000000000 and not b&(1<<51))
  expected=cache[b]
  for state_name,state in states.items():
   active.update(state=state_name,flags=flags);results={};captures={}
   for label,m in machines.items():
    if label in audits:audits[label][1]()
    fn='qfp_ddiv'if label=='Qfplib'else'mk61_m0_reciprocal1'if label=='candidate'else'mk61_m0_hint_ddiv'
    m.uc.mem_write(0xd0000060,state);got,_,cost=m.call(fn,bits(1.),b,count=True);calls+=1;after=bytes(m.uc.mem_read(0xd0000060,28))
    assert after==state if state_name=='DIRTY'else not struct.unpack('<7I',after)[6]&2
    results[label]=dict(output=f'{got:016X}',instructions=cost,correct=equal(got,expected))
    if label in audits:
     captures[label]=json.loads(json.dumps(audits[label][0]));assert len(captures[label]['calls'])==len(captures[label]['pops'])==1
   assert results['parent']==results['control']and results['candidate']['output']==results['parent']['output']and all(results[n]['correct']for n in ['parent','control','candidate'])
   assert captures['control']['first']==captures['candidate']['first']and captures['control']['after']==captures['candidate']['after']and captures['control']['seeds']==captures['candidate']['seeds']
   saving=guard((b>>52)&2047)+15*len(captures['candidate']['first'])+8*len(captures['candidate']['seeds'])
   assert results['parent']['instructions']-results['candidate']['instructions']==saving
   if f'{b:016X}'in selection['normal_denominators']:
    assert results['Qfplib']['correct']and results['candidate']['instructions']>results['Qfplib']['instructions']
    normal_witness.setdefault((f'{b:016X}',state_name),dict(denominator=f'{b:016X}',SIO=state_name,candidate=results['candidate']['instructions'],Qfplib=results['Qfplib']['instructions'],lag=results['candidate']['instructions']-results['Qfplib']['instructions']))
   rows.append(dict(denominator=f'{b:016X}',flags=flags,group=group,SIO=state_name,expected=f'{expected:016X}',results=results,captures=captures))
 assert len(normal_witness)==18
 ranges={s:[min(r['lag']for r in normal_witness.values()if r['SIO']==s),max(r['lag']for r in normal_witness.values()if r['SIO']==s)]for s in states};assert ranges==dict(READY=[2,5],DIRTY=[15,21])
 save('scalar-arm-mpfr.json',dict(status='PASS_BOUNDED_PRIVATE_ONE_ALL_NORMAL_DEFICITS_IEEE_AND_FULL_AFTER_SECOND_STATE',jobs=len(jobs),distinct_denominators=len(cache),actual_ARM_calls=calls,
  directed_MPFR_inputs=len(cache)-shortcuts,sNaN_shortcuts=shortcuts,oracle_cache_per_denominator_reused_for_flags=True,MPFR_version=oracle.version,
  all9remaining_normal_denominators_each16flags_bothSIO=True,all18_remaining_denominators_and_IEEE_classes=True,
  all_after_second_R0_R7_R12_SP_NZCV_frame28_equal=True,all_raw1preconditions_R6_original20B_R3_save_alignment_checked=True,
  READY_actual9ALU_issue_read_latency_checked=True,return_pop_original_saved_frame_and_PC_checked=True,
  all_cost_deltas_guard_plus15first_plus8software=True,all3candidate_parent_control_correct=True,Qfplib_wrong_and_correct_outputs_costs_retained=True,
  normal_loss_witnesses=list(normal_witness.values()),correct_normal_lag_ranges=ranges,no_universal_speed_claim=True,
  observed_stack_bytes={n:SP-m.stack_lowest for n,m in machines.items()},rows=rows,device_IO=0))
def public():
 machines=loader();active=dict(public=True);audits={n:audit(machines[n],n,active)for n in ['control','candidate']};jobs={}
 for r in json.loads((O/'selected-public-jobs.json').read_text())['jobs']:jobs[int(r['x'],16),int(r['y'],16)]=r['group']
 for a,b in [(0,0),(1,bits(.5)),(bits(-2.),bits(.5)),(0x7fefffffffffffff,bits(-.5)),(bits(1.),0x7ff0000000000001),(0xfff0000000000001,bits(0.))]:jobs[a,b]='IEEE_and_sNaN_controls'
 oracle=Oracle();refs=['qfp_composed_pow','qfp_composed_pow_exact','qfp_composed_pow_integer'];rows=[];calls=shortcuts=0;fixed={tuple(p)for p in json.loads((W/'qualification.json').read_text())['fixed_pairs']}
 for (a,b),group in jobs.items():
  expected=oracle.reference('pow',a,b);shortcuts+=any((v&0x7fffffffffffffff)>0x7ff0000000000000 and not v&(1<<51)for v in [a,b])
  for state_name,state in states.items():
   active['state']=state_name;outputs={};costs={};correct={};captures={}
   for label in ['parent','control','candidate',*refs]:
    m=machines[label if label in machines else'Qfplib']
    if label in audits:audits[label][1]()
    m.uc.mem_write(0xd0000060,state);got,_,cost=m.call(label if label in refs else'_ZN12compact_math3powEdd',a,b,count=True);calls+=1;after=bytes(m.uc.mem_read(0xd0000060,28))
    assert after==state if state_name=='DIRTY'else not struct.unpack('<7I',after)[6]&2
    outputs[label]=f'{got:016X}';costs[label]=cost;correct[label]=equal(got,expected)
    if label not in refs:assert correct[label]
    if label in audits:captures[label]=json.loads(json.dumps(audits[label][0]))
   assert outputs['parent']==outputs['control']==outputs['candidate']and costs['parent']==costs['control']
   co,ca=captures['control'],captures['candidate'];assert co['calls']==ca['calls']and co['first']==ca['first']and co['after']==ca['after']and co['seeds']==ca['seeds']
   assert len(ca['calls'])==len(ca['pops'])==len(ca['return_sites'])
   saving=sum(guard((int(c['denominator'],16)>>52)&2047)for c in ca['calls'])+15*len(ca['first'])+8*len(ca['seeds']);assert costs['parent']-costs['candidate']==saving
   pair=f'{a:016X}',f'{b:016X}'
   if pair in fixed:assert all(costs['candidate']<costs[n]for n in refs if correct[n])
   rows.append(dict(x=pair[0],y=pair[1],SIO=state_name,group=group,expected=f'{expected:016X}',outputs=outputs,instructions=costs,correct=correct,captures=captures))
 assert len({(r['x'],r['y'])for r in rows if(r['x'],r['y'])in fixed})==5
 save('public-arm-mpfr.json',dict(status='PASS_BOUNDED_PUBLIC_ONE_ALL5_NEW_STRICT_FIXES_AND_ACTUAL_CALL_RETURN_CONTRACTS',pairs=len(jobs),actual_ARM_calls=calls,
  directed_MPFR_inputs=len(jobs)-shortcuts,sNaN_shortcuts=shortcuts,MPFR_version=oracle.version,
  all5_new_strict_fixes_bothSIO=True,exact_numerator1_every_entry_expected_root_return_every_POP_and_actual_return=True,
  after_second_full_registers_NZCV_frame28_identical=True,all_actual_costs_exact_guard_product_seed_law=True,
  original20B_R6_R3_R12_seed_alignment_SIO7words_preserved=True,READY9ALU_issue_read_checked=True,
  all3_real_Qfplib_compositions_correct_wrong_outputs_and_costs_retained=True,strict_quietNaN=True,
  no_generic_new_ddiv_ABI=True,near_one_sibling_not_loaded=True,ROM_initializers_excluded=True,
  observed_stack_bytes={n:SP-m.stack_lowest for n,m in machines.items()},rows=rows,device_IO=0))
if __name__=='__main__':
 assert len(sys.argv)==2 and sys.argv[1]in ['scalar','public'];globals()[sys.argv[1]]()
