"""Bounded actual seed/private join/public checks; no physical interfaces."""
import ast,hashlib,json,random,struct,sys
from collections import Counter
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-reciprocal-soft-20261025'
SUP=R/'.build/m0-float-fma-qualification-20261023/support';sys.path[:0]=[str(SUP),str(R/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP,bits
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_WRITE,UC_HOOK_MEM_READ
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R12,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_XPSR
REGS=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3];JOINREGS=[*REGS,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R12,UC_ARM_REG_SP]
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def save(n,d):
 with (O/n).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
 print(json.dumps(ref(O/n)),flush=True)
def memory(e,a,n):
 s=next(s for s in e.sections if s[1]!=8 and s[3]<=a and a+n<=s[3]+s[5]);return e.bytes_at(s)[a-s[3]:a-s[3]+n]
def equal(a,b):return bool((a&0x7fffffffffffffff)>0x7ff0000000000000 and a&(1<<51))if (b&0x7fffffffffffffff)>0x7ff0000000000000 else a==b
def seed():
 m=Machine(O/'seed-only.elf',True);entry=m.elf.symbols['mk61_m0_ddiv_seed17']&~1;active={};hist=Counter();rows=[]
 assert not m.rom_models and not m.rom_initializers
 def code(uc,pc,n,user):
  assert entry<=pc and pc+n<=entry+194
  if pc==entry:
   uc.reg_write(UC_ARM_REG_XPSR,0x01000000|(active['flags']<<28));uc.reg_write(UC_ARM_REG_R12,active['r12']);uc.reg_write(UC_ARM_REG_R3,active['r3'])
 def memory_forbidden(*args):raise AssertionError('seed has no data memory accesses')
 m.uc.hook_add(UC_HOOK_CODE,code);m.uc.hook_add(UC_HOOK_MEM_WRITE,memory_forbidden);m.uc.hook_add(UC_HOOK_MEM_READ,memory_forbidden)
 rng=random.Random(0x517B025);edges=[65536,65537,65538,65551,65552,70000,80000,87380,98303,98304,98305,100000,120000,131069,131070,131071]
 jobs=[(d,f)for d in edges for f in range(16)]+[(rng.randrange(65536,131072),i&15)for i in range(32)]
 for D,flags in jobs:
  active.update(flags=flags,r12=rng.getrandbits(32),r3=rng.getrandbits(32));a=rng.getrandbits(32)
  got,_,cost=m.call('mk61_m0_ddiv_seed17',a,D,width=32,count=True);q=got&0xffffffff;assert q==0xffffffff//D
  assert m.uc.reg_read(UC_ARM_REG_R1)==D and m.uc.reg_read(UC_ARM_REG_R3)==active['r3']and m.uc.reg_read(UC_ARM_REG_R12)==active['r12']
  hist[cost]+=1;rows.append(dict(D=D,flags=flags,quotient=q,u0=(q+1)>>1,instructions=cost))
 save('seed-arm.json',dict(status='PASS_BOUNDED_ACTUAL_EXACT_SEED194',actual_ARM_calls=len(jobs),actual_MPFR_inputs=0,
  all16NZCV_each16edgeD_plus32samples=True,all_quotients_exact=True,R1_R3_R12_PCS_SP_PC_preserved=True,
  no_memory_or_stack_accesses_and_no_firmware_ROM_or_arithmetic_models=True,PC194only=True,cost_histogram=dict(hist),rows=rows,device_IO=0))
states=dict(READY=struct.pack('<7I',0,0,0,0,0,0,1),DIRTY=struct.pack('<7I',17,3,17,3,5,2,3))
def load_machines():
 table=R/'.build/m0-pow-exp-table-product-20261025';im=ElfImage(table/'candidate.elf');entry=im.symbols['mk61_m0_pow_exp_table_product']&~1
 tree=ast.parse((R/'.build/m0-pow-exp-table-product-independent-20261025/arm.py').read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='machine')
 env=dict(R=R,W=table,im=im,entry=entry,Machine=Machine,ElfImage=ElfImage,memory=memory)
 exec(compile(ast.Module(body=[fn],type_ignores=[]),'<accepted-table-loader>','exec'),env)
 machines={}
 for label in ['parent','control','candidate','Qfplib']:
  m=env['machine']('Qfplib'if label=='Qfplib'else'candidate')
  if label!='Qfplib':
   for folder in ['m0-pow-square128-r2-20261025','m0-pow-boundary128-20261025']:ElfImage(R/'.build'/folder/'candidate.elf').load(m.uc)
   if label!='parent':
    e=ElfImage(O/'rebuild'/(label+'.elf'));e.load(m.uc);m.elf.symbols.update({n:a for n,a in e.symbols.items()if n.startswith(('mk61_m0_hint','mk61_m0_ddiv_sw','mk61_m0_ddiv_seed'))})
   assert bytes(m.uc.mem_read(entry,20))==memory(im,entry,20)and not m.rom_models
  machines[label]=m
 return machines
def audit(m,label,active):
 e=ElfImage(O/'rebuild'/(label+'.elf'));entry=e.symbols['mk61_m0_hint_ddiv']&~1;sw=e.symbols['mk61_m0_ddiv_sw_from_guard']&~1;seed=e.symbols['mk61_m0_ddiv_seed17']&~1
 joins=[e.symbols[n]&~1 for n in ['mk61_m0_hint_join','mk61_m0_sw_join']];out=dict(entry=None,sw=[],seeds=[],joins=[],flags_after_add=[],MMIO=[]);running=dict(on=False,return_pc=0)
 def code(uc,pc,n,user):
  if running['on']and pc==running['return_pc']:running['on']=False
  if pc==entry:
   raw=[uc.reg_read(r)for r in REGS];sp=uc.reg_read(UC_ARM_REG_SP);saved=[uc.reg_read(r)for r in [UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_LR]]
   out['entry']=dict(raw=raw,sp=sp,saved=saved);running.update(on=True,return_pc=saved[-1]&~1)
   if active.get('set_flags'):
    uc.reg_write(UC_ARM_REG_XPSR,0x01000000|(active['flags']<<28));uc.reg_write(UC_ARM_REG_R12,0xC0250000|active['flags'])
  if pc==sw:
   ent=out['entry'];raw=ent['raw'];sp=uc.reg_read(UC_ARM_REG_SP);a=raw[0]|(raw[1]<<32);b=raw[2]|(raw[3]<<32)
   exp=((a>>52)&2047)-((b>>52)&2047)+1021
   assert 1<=(a>>52)&2047<=2046 and 1<=(b>>52)&2047<=2046 and 0<=exp<=2043
   assert [uc.reg_read(r)for r in REGS]==raw and uc.reg_read(UC_ARM_REG_R6)==exp
   assert sp==ent['sp']-20 and bytes(uc.mem_read(sp,20))==struct.pack('<5I',*ent['saved'])
   assert struct.unpack('<7I',uc.mem_read(0xd0000060,28))[6]&2
   out['sw'].append(dict(raw=[f'{v:08X}'for v in raw],R6=exp,SP=sp,frame=bytes(uc.mem_read(sp,20)).hex()))
  if pc==seed:
   ent=out['entry'];raw=ent['raw'];sp=uc.reg_read(UC_ARM_REG_SP);d=uc.reg_read(UC_ARM_REG_R1);sign=(raw[1]^raw[3])>>31
   assert sp%8==0 and sp==ent['sp']-40 and uc.reg_read(UC_ARM_REG_R0)==0xffffffff
   assert d==((raw[3]&0xfffff)|0x100000)>>4 and 65536<=d<131072
   exp=((raw[1]>>20)&2047)-((raw[3]>>20)&2047)+1021
   assert uc.reg_read(UC_ARM_REG_R12)==4*exp+sign
   expected=(raw[0],(raw[1]&0xfffff)|0x100000,raw[2],(raw[3]&0xfffff)|0x100000,sign)
   assert bytes(uc.mem_read(sp,20))==struct.pack('<5I',*expected)
   out['seeds'].append(d)
  if pc in joins:
   sp=uc.reg_read(UC_ARM_REG_SP);out['joins'].append(dict(registers=[uc.reg_read(r)for r in JOINREGS],frame=bytes(uc.mem_read(sp,20)).hex()))
  if pc in [j+10 for j in joins]:out['flags_after_add'].append(uc.reg_read(UC_ARM_REG_XPSR)&0xf0000000)
 def read(uc,access,a,n,v,user):
  if running['on']and 0xd0000060<=a<0xd000007c:
   out['MMIO'].append(dict(kind='read',address=hex(a),bytes=n))
   if active.get('state')=='DIRTY':assert a==0xd0000078 and n==4
 def write(uc,access,a,n,v,user):
  if running['on']and 0xd0000060<=a<0xd000007c:
   out['MMIO'].append(dict(kind='write',address=hex(a),bytes=n))
   assert active.get('state')!='DIRTY'
 m.uc.hook_add(UC_HOOK_CODE,code);m.uc.hook_add(UC_HOOK_MEM_READ,read);m.uc.hook_add(UC_HOOK_MEM_WRITE,write)
 def clear():
  out.update(entry=None,sw=[],seeds=[],joins=[],flags_after_add=[],MMIO=[]);running['on']=False
 return out,clear
def ddiv():
 machines=load_machines();active=dict(set_flags=True);traces={n:audit(machines[n],n,active)for n in ['control','candidate']};jobs={}
 def add(a,b,group):jobs.setdefault((a,b),group)
 direct=json.loads((W/'direct-proof.json').read_text())['rows']
 for r in direct:
  if r['group']=='real_reciprocal':add(int(r['a'],16),int(r['b'],16),'actual_root_reciprocal')
 for i,D in enumerate([65536,65537,70000,87380,98304,100000,131070,131071]):
  add(bits(1.0625)|((i&1)<<63),(1023<<52)|((D-65536)<<36)|(123+i)|(((i>>1)&1)<<63),'seed_D_edges_signs')
 for ea,eb in [(1,1022),(1,1023),(2046,1024),(2046,1023),(1,2046),(2046,1)]:add((ea<<52)|123,(eb<<52)|456,'result_exponent_guard_edges')
 for a,b in [(0,0),(0,bits(-1.)),(bits(-1.),0),(1,bits(2.)),(0x0010000000000000,bits(2.)),(0x7fefffffffffffff,bits(.5)),(bits(1.),bits(1.5)),(bits(1.),bits(1.125)),(0x7ff0000000000000,bits(2.)),(bits(1.),0x7ff0000000000000),(bits(1.),0x7ff0000000000001),(0xfff0000000000001,bits(1.))]:add(a,b,'IEEE_dyadic_and_sNaN')
 oracle=Oracle();rows=[];calls=snans=matched=0
 for i,((a,b),group)in enumerate(jobs.items()):
  expected=oracle.reference('ddiv',a,b);snans+=any((v&0x7fffffffffffffff)>0x7ff0000000000000 and not v&(1<<51)for v in [a,b]);ready=None;readyflags=None
  for state_name,state in states.items():
   active.update(flags=i&15,state=state_name);results={};captures={}
   for label,m in machines.items():
    if label in traces:traces[label][1]()
    m.uc.mem_write(0xd0000060,state);fn='qfp_ddiv'if label=='Qfplib'else'__aeabi_ddiv'if label=='parent'else'mk61_m0_hint_ddiv'
    got,_,cost=m.call(fn,a,b,count=True);calls+=1;after=bytes(m.uc.mem_read(0xd0000060,28))
    assert after==state if state_name=='DIRTY'else not struct.unpack('<7I',after)[6]&2
    results[label]=dict(output=f'{got:016X}',instructions=cost,correct=equal(got,expected))
    if label in traces:captures[label]=json.loads(json.dumps(traces[label][0]))
   assert results['parent']==results['control']and all(results[n]['correct']for n in ['parent','control','candidate'])
   assert results['candidate']['output']==results['parent']['output']and results['candidate']['instructions']<=results['parent']['instructions']
   if state_name=='READY':
    assert results['candidate']==results['parent']and not captures['candidate']['seeds']
    assert captures['control']['joins']==captures['candidate']['joins'];ready=captures['control']['joins'];readyflags=captures['control']['flags_after_add']
   elif captures['candidate']['seeds']:
    assert captures['candidate']['joins']==ready and captures['candidate']['flags_after_add']==readyflags;matched+=1
    assert captures['candidate']['MMIO']==[dict(kind='read',address='0xd0000078',bytes=4)]
   rows.append(dict(a=f'{a:016X}',b=f'{b:016X}',group=group,SIO=state_name,expected=f'{expected:016X}',results=results,captures=captures))
 assert matched>=8
 save('ddiv-arm-mpfr.json',dict(status='PASS_BOUNDED_ACTUAL_GUARDED_CLONE_PRIVATE_JOIN_AND_IEEE_RNE',unique_pairs=len(jobs),actual_ARM_calls=calls,
  directed_MPFR_inputs=len(jobs)-snans,sNaN_shortcuts=snans,MPFR_version=oracle.version,
  actual_private_software_READY_hardware_join_matches=matched,R0_R6_R12_SP_saved20B_equal=True,flags_after_first_common_ADDS_equal=True,
  raw_operands_guardedR6_saved_frame_not_scalar_C_prototype_checked=True,seed_call_8alignment_and_saved_four_operands_sign_word=True,
  DIRTY_read_CSR_only_no_divider_writes_all7words_preserved=True,READY_exact_parent_control_candidate_costs=True,
  old_control_bits_cost_calibrated=True,all_Qfp_outputs_including_wrong_retained=True,strict_quietNaN=True,
  ROM_initializers_excluded_from_call_count=True,observed_stack_bytes={n:SP-m.stack_lowest for n,m in machines.items()},rows=rows,device_IO=0))
def public():
 machines=load_machines();active=dict(set_flags=False);traces={n:audit(machines[n],n,active)for n in ['control','candidate']};jobs={}
 for r in json.loads((O/'selected-public-jobs.json').read_text())['jobs']:jobs[int(r['x'],16),int(r['y'],16)]=r['group']
 for a,b in [(0,0),(1,bits(.5)),(bits(-2.),bits(.5)),(0x7fefffffffffffff,bits(-.5)),(bits(1.),0x7ff0000000000001),(0xfff0000000000001,bits(0.))]:jobs[a,b]='IEEE_and_sNaN_controls'
 refs=['qfp_composed_pow','qfp_composed_pow_exact','qfp_composed_pow_integer'];oracle=Oracle();rows=[];calls=snans=matched=0
 fresh=json.loads((W/'new-qualification.json').read_text())['rows'];fresh={(r['x'],r['y'],r['SIO']):r for r in fresh};fixed={tuple(p)for p in json.loads((W/'qualification.json').read_text())['fixed_pairs']}
 for (a,b),group in jobs.items():
  expected=oracle.reference('pow',a,b);snans+=any((v&0x7fffffffffffffff)>0x7ff0000000000000 and not v&(1<<51)for v in [a,b]);ready=None;readyflags=None
  for state_name,state in states.items():
   active['state']=state_name;outputs={};costs={};correct={};captures={}
   for label in ['parent','control','candidate',*refs]:
    m=machines[label if label in machines else'Qfplib']
    if label in traces:traces[label][1]()
    m.uc.mem_write(0xd0000060,state);got,_,cost=m.call(label if label in refs else'_ZN12compact_math3powEdd',a,b,count=True);calls+=1
    after=bytes(m.uc.mem_read(0xd0000060,28));assert after==state if state_name=='DIRTY'else not struct.unpack('<7I',after)[6]&2
    outputs[label]=f'{got:016X}';costs[label]=cost;correct[label]=equal(got,expected)
    if label not in refs:assert correct[label]
    if label in traces:captures[label]=json.loads(json.dumps(traces[label][0]))
   assert outputs['parent']==outputs['control']==outputs['candidate']and costs['parent']==costs['control']and costs['candidate']<=costs['parent']
   if state_name=='READY':
    assert costs['candidate']==costs['parent']and not captures['candidate']['seeds'];ready=captures['control']['joins'];readyflags=captures['control']['flags_after_add']
   elif captures['candidate']['seeds']:
    assert captures['candidate']['joins']==ready and captures['candidate']['flags_after_add']==readyflags;matched+=1
   key=f'{a:016X}',f'{b:016X}',state_name
   if key in fresh:assert fresh[key]['outputs']==outputs and fresh[key]['instructions']==costs and fresh[key]['software_seed_divisors']==captures['candidate']['seeds']
   if key[:2]in fixed:assert all(costs['candidate']<costs[n]for n in refs if correct[n])
   rows.append(dict(x=key[0],y=key[1],SIO=state_name,group=group,expected=f'{expected:016X}',outputs=outputs,instructions=costs,correct=correct,captures=captures))
 assert len({(r['x'],r['y'])for r in rows if (r['x'],r['y'])in fixed})==48
 save('public-arm-mpfr.json',dict(status='PASS_BOUNDED_ACTUAL_PUBLIC_POW_ALL48_SAVED_STRICT_FIXES',unique_pairs=len(jobs),actual_ARM_calls=calls,
  directed_MPFR_inputs=len(jobs)-snans,sNaN_shortcuts=snans,MPFR_version=oracle.version,all48_fixes_actual_bothSIO_strict_against_all_correct_refs=True,
  READY_costs_unchanged=True,DIRTY_guard_and_saved20_raw_operands_seed_alignment_checked=True,private_JOIN_equal_READYhardware_and_first_ADDS_flags=True,
  actual_DIRTY_join_checks=matched,all3_real_Qfplib_compositions_wrong_outputs_and_costs_retained=True,strict_quietNaN=True,
  no_new_raw_loss_or_candidate_wrong=True,SIO7words_PCS_SP_PC_checked=True,
  no_generic_private_continuation_call=True,near_one_sibling_not_loaded=True,ROM_initializers_excluded=True,
  observed_stack_bytes={n:SP-m.stack_lowest for n,m in machines.items()},rows=rows,device_IO=0))
if __name__=='__main__':
 assert len(sys.argv)==2 and sys.argv[1]in ['seed','ddiv','public'];globals()[sys.argv[1]]()
