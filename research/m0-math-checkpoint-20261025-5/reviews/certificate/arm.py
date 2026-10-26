"""Bounded bare certificate and fresh real private-context CPU qualification."""
import ast,hashlib,json,random,struct,sys,traceback
from collections import Counter
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-reciprocal-certificate-20261025';P=R/'.build/m0-pow-reciprocal-inline-20261025'
SUP=R/'.build/m0-float-fma-qualification-20261023/support';sys.path[:0]=[str(SUP),str(R/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP,STOP,bits
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R12,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_XPSR
MASK=(1<<32)-1;RAW=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3];REGS=[*RAW,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R12,UC_ARM_REG_SP,UC_ARM_REG_XPSR]
LIVE=[*RAW,UC_ARM_REG_R5,UC_ARM_REG_R12,UC_ARM_REG_SP];CERTLIVE=[*RAW,UC_ARM_REG_R7,UC_ARM_REG_R12,UC_ARM_REG_SP]
states=dict(READY=struct.pack('<7I',0,0,0,0,0,0,1),DIRTY=struct.pack('<7I',17,3,17,3,5,2,3))
run=dict(started=0,completed=0,MPFR=0,sNaN=0,current=None)
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def save(n,d):
 with(O/n).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
 print(json.dumps(ref(O/n)),flush=True)
def memory(e,a,n):
 s=next(s for s in e.sections if s[1]!=8 and s[3]<=a and a+n<=s[3]+s[5]);return e.bytes_at(s)[a-s[3]:a-s[3]+n]
def equal(a,b):return bool((a&0x7fffffffffffffff)>0x7ff0000000000000 and a&(1<<51))if (b&0x7fffffffffffffff)>0x7ff0000000000000 else a==b
def call(m,fn,a,b):
 run['started']+=1;got,_,cost=m.call(fn,a,b,count=True);run['completed']+=1;return got,cost
def expected(oracle,fn,a,b):
 short=any((v&0x7fffffffffffffff)>0x7ff0000000000000 and not v&(1<<51)for v in [a,b])
 run['sNaN'if short else'MPFR']+=1;return oracle.reference(fn,a,b)
fn=next(n for n in ast.parse((O/'accounting.py').read_text()).body if isinstance(n,ast.FunctionDef)and n.name=='certificate');exec(compile(ast.Module(body=[fn],type_ignores=[]),'<own-universal-certificate-model>','exec'),globals())
def unit():
 machines={n:Machine(O/'rebuild/unit'/(n+'.elf'),True)for n in ['control','candidate']};active={};rng=random.Random(0xC3712025);rows=[];classes=Counter()
 for label,m in machines.items():
  assert not m.rom_models and not m.rom_initializers
  start=m.elf.symbols['unit_certificate_begin']&~1
  def hook(m,label,start):
   def code(uc,pc,n,user):
    if pc==start:
     uc.reg_write(UC_ARM_REG_XPSR,0x01000000|(active['flags']<<28));uc.reg_write(UC_ARM_REG_R1,active['r1']);uc.reg_write(UC_ARM_REG_R12,active['r12'])
     active[label+'_live']=[uc.reg_read(r)for r in CERTLIVE];active[label+'_frame']=bytes(uc.mem_read(SP-20,20))
    if label=='candidate'and pc==start+12:
     model=active['model'];x=uc.reg_read(UC_ARM_REG_XPSR)
     assert [uc.reg_read(r)for r in CERTLIVE]==active[label+'_live']and bytes(uc.mem_read(SP-20,20))==active[label+'_frame']
     assert uc.reg_read(UC_ARM_REG_R4)==model['estimate']and uc.reg_read(UC_ARM_REG_R5)==(active['u']>>16)*(active['v']>>16)
     assert ((x>>30)&1)==int(not model['fast'])and ((x>>29)&1)==(model['estimate']>>31)
     active['classifier_checked']=True
   def write(uc,access,a,n,v,user):
    assert SP-20<=a<a+n<=SP
    if label=='candidate':assert not start<=uc.reg_read(UC_ARM_REG_PC)<start+16
   return code,write
  code,write=hook(m,label,start);m.uc.hook_add(UC_HOOK_CODE,code);m.uc.hook_add(UC_HOOK_MEM_WRITE,write)
 selection=json.loads((O/'unit-selection.json').read_text())['triples']
 for i,r in enumerate(selection):
  for flags in range(16):
   base,u,v=r['base'],r['u'],r['v'];model=certificate(base,u,v)
   active.update(r,flags=flags,model=model,r1=rng.getrandbits(32),r12=rng.getrandbits(32),classifier_checked=False)
   run['current']=dict(stage='unit',index=i,flags=flags,base=base,u=u,v=v)
   want=MASK if model['negative']else 1 if model['exact']else 0;costs={}
   for label,m in machines.items():
    got,cost=call(m,'unit_remainder_sign',base|(u<<32),v|(rng.getrandbits(32)<<32));costs[label]=cost
    assert got&MASK==want and m.uc.reg_read(UC_ARM_REG_R1)==active['r1']and m.uc.reg_read(UC_ARM_REG_R12)==active['r12']
   assert active['classifier_checked'];cl=('fast'if model['fast']else'full')+'_'+('negative'if model['negative']else'zero'if model['exact']==0 else'positive');classes[cl]+=1
   rows.append(dict(**r,NZCV=flags,expected=want,model=model,instructions=costs))
 assert set(classes)=={'fast_negative','fast_positive','full_negative','full_positive','full_zero'}
 save('unit-arm.json',dict(status='PASS_BOUNDED_REAL_THUMB_SHARED_CERTIFICATE_ALL_FLAGS_INCLUSIVE_EDGES',tests=len(rows),actual_ARM_calls=run['completed'],all16_flags_each_selected_triple=True,
  exact_zero_INTMIN_wrap_borrow_cross_products_and_all_decision_classes=True,actual_Z_uncertain_C_sign_and_preserved_R0_R1_R2_R3_R7_R12_SP_frame_checked=True,
  no_macro_memory_access_or_stackwrite=True,Machine_PCS_SP_PC_and_only20B_wrapper_stackwrites=True,unit_wrapper_cost_not_production_claim=True,classes=dict(classes),rows=rows,device_IO=0))
def loader():
 t=R/'.build/m0-pow-exp-table-product-20261025';im=ElfImage(t/'candidate.elf');te=im.symbols['mk61_m0_pow_exp_table_product']&~1
 fn=next(n for n in ast.parse((R/'.build/m0-pow-exp-table-product-independent-20261025/arm.py').read_text()).body if isinstance(n,ast.FunctionDef)and n.name=='machine');env=dict(R=R,W=t,im=im,entry=te,Machine=Machine,ElfImage=ElfImage,memory=memory)
 exec(compile(ast.Module(body=[fn],type_ignores=[]),'<accepted-table-loader>','exec'),env);machines={}
 for label in ['parent','control','candidate','Qfplib']:
  m=env['machine']('Qfplib'if label=='Qfplib'else'candidate')
  if label!='Qfplib':
   for folder in ['m0-pow-square128-r2-20261025','m0-pow-boundary128-20261025']:ElfImage(R/'.build'/folder/'candidate.elf').load(m.uc)
   e=ElfImage(P/'candidate.elf'if label=='parent'else O/'rebuild'/(label+'.elf'));e.load(m.uc)
   m.elf.symbols.update({n:a for n,a in e.symbols.items()if n.startswith(('mk61_m0_reciprocal1','mk61_m0_inline'))})
   assert bytes(m.uc.mem_read(te,20))==memory(im,te,20)
  machines[label]=m
 return machines
def state(uc):
 sp=uc.reg_read(UC_ARM_REG_SP);r=[uc.reg_read(n)for n in REGS];r[-1]&=0xf0000000;return dict(registers=r,frame28=bytes(uc.mem_read(sp,28)).hex())
def audit(m,label,active):
 e=ElfImage(O/'rebuild'/(label+'.elf'));candidate=label=='candidate';entry=e.symbols['mk61_m0_reciprocal1']&~1;sw=e.symbols['mk61_m0_reciprocal1_sw_from_guard']&~1
 tags=['mk61_m0_reciprocal1','mk61_m0_reciprocal1_sw'];at={}
 for tag in tags:
  for suffix in ['_first_product','_after_second_product','_y_low_shift','_certificate_begin','_certificate_up','_certificate_down']+(['_certificate_full']if candidate else[]):at[e.symbols[tag+suffix]&~1]=(suffix,tag)
  at[(e.symbols[tag+'_certificate_down']&~1)+8]=('_pack',tag)
 begin=e.symbols['mk61_m0_inline_seed_begin']&~1;done=e.symbols['mk61_m0_inline_seed_done']&~1;table=e.named_sections['.ddiv'][3]+e.named_sections['.ddiv'][5]-256
 out={};cur={};tick=0
 def clear():out.update(calls=[],first=[],after=[],zeros=[],pre_cert=[],certificates=[],down=[],pack=[],inline=[],pops=[],returns=[],latency9=[],seeds=[],classified=0,restored=0);cur.clear()
 def code(uc,pc,n,user):
  nonlocal tick
  tick+=1
  if cur and pc==cur['return']:
   assert uc.reg_read(UC_ARM_REG_SP)==cur['sp'];out['returns'].append(pc);cur['returned']=True
  if pc==entry:
   raw=[uc.reg_read(r)for r in RAW];assert raw[:2]==[0,0x3ff00000];sp=uc.reg_read(UC_ARM_REG_SP);assert sp%8==0
   ret=uc.reg_read(UC_ARM_REG_LR)&~1;assert ret==(0x1014e668+2732+4 if active['public']else STOP)
   cur.clear();cur.update(raw=raw,sp=sp,saved=[uc.reg_read(r)for r in [UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_LR]],return_=ret);cur['return']=ret
   out['calls'].append(dict(numerator='3FF0000000000000',denominator=f'{raw[2]|raw[3]<<32:016X}',entry_SP=sp,return_site=hex(ret)))
   if not active['public']:uc.reg_write(UC_ARM_REG_XPSR,0x01000000|(active['flags']<<28));uc.reg_write(UC_ARM_REG_R12,0xC3251000|active['flags'])
  if pc==sw:
   raw=cur['raw'];E=(raw[3]>>20)&2047;assert 1<=E<=2044 and uc.reg_read(UC_ARM_REG_R6)==2044-E and [uc.reg_read(r)for r in RAW]==raw and uc.reg_read(UC_ARM_REG_SP)==cur['sp']-20
  if pc==begin:
   raw=cur['raw'];E=(raw[3]>>20)&2047;sp=uc.reg_read(UC_ARM_REG_SP);D=uc.reg_read(UC_ARM_REG_R1)
   assert D==((raw[3]&0xfffff)|0x100000)>>4 and 65536<=D<131072 and uc.reg_read(UC_ARM_REG_R12)==4*(2044-E)+(raw[3]>>31)
   assert sp==cur['sp']-20 and bytes(uc.mem_read(sp,20))==struct.pack('<5I',*cur['saved'])
   assert uc.reg_read(UC_ARM_REG_R0)==0 and uc.reg_read(UC_ARM_REG_R2)==raw[2]and uc.reg_read(UC_ARM_REG_R3)==((raw[3]&0xfffff)|0x100000)
   cur['inline_live']=[uc.reg_read(r)for r in LIVE];cur['D']=D;cur['reads']=0;out['seeds'].append(D)
  if pc==done:
   assert [uc.reg_read(r)for r in LIVE]==cur['inline_live']and cur['reads']==1
   assert uc.reg_read(UC_ARM_REG_R6)==MASK//cur['D']and uc.reg_read(UC_ARM_REG_R7)==MASK%cur['D']
   assert bytes(uc.mem_read(cur['sp']-20,20))==struct.pack('<5I',*cur['saved'])
   out['inline'].append(dict(entry_SP=cur['sp'],inline_SP=uc.reg_read(UC_ARM_REG_SP),D=cur['D'],live=cur['inline_live']))
  if pc in at:
   suffix,tag=at[pc]
   if suffix=='_first_product':assert uc.reg_read(UC_ARM_REG_R0)==0;out['first'].append(uc.reg_read(UC_ARM_REG_R6))
   if suffix=='_after_second_product':assert uc.reg_read(UC_ARM_REG_SP)==cur['sp']-28;out['after'].append(state(uc))
   if suffix=='_y_low_shift':assert uc.reg_read(UC_ARM_REG_R4)==0;out['zeros'].append(state(uc))
   if suffix=='_certificate_begin':
    st=state(uc);out['pre_cert'].append(st);model=certificate(uc.reg_read(UC_ARM_REG_R4),uc.reg_read(UC_ARM_REG_R2),uc.reg_read(UC_ARM_REG_R0))
    cur['cert_model']=model;cur['cert_midpoint']=[uc.reg_read(r)for r in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R12,UC_ARM_REG_SP]]
    cur['cert_live']=[uc.reg_read(r)for r in CERTLIVE];cur['cert_begin']=pc;cur['cert_full_pc']=e.symbols[tag+'_certificate_full']&~1 if candidate else None
    row=dict(model,actual_full=False if candidate else True,actual_decision=None);out['certificates'].append(row)
   if suffix=='_certificate_full':
    row=out['certificates'][-1];assert not row['fast']and uc.reg_read(UC_ARM_REG_R4)==row['estimate']and uc.reg_read(UC_ARM_REG_R5)==(row['u']>>16)*(row['v']>>16);row['actual_full']=True
   if suffix=='_certificate_up':
    row=out['certificates'][-1];assert not row['negative'];assert [uc.reg_read(r)for r in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R12,UC_ARM_REG_SP]]==cur['cert_midpoint'];row['actual_decision']='up'
   if suffix=='_certificate_down':
    row=out['certificates'][-1]
    if row['actual_decision']is None:assert row['negative'];row['actual_decision']='down'
    assert not candidate or row['actual_full']==row['full']
    wanted=cur['cert_midpoint'].copy()
    if not row['negative']:
     z=(wanted[0]|wanted[1]<<32)+1;wanted[0],wanted[1]=z&MASK,(z>>32)&MASK
    assert [uc.reg_read(r)for r in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R12,UC_ARM_REG_SP]]==wanted
    out['down'].append(wanted)
   if suffix=='_pack':out['pack'].append([uc.reg_read(r)for r in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R12,UC_ARM_REG_SP]])
  if candidate and cur.get('cert_begin')and pc==cur['cert_begin']+12:
   row=cur['cert_model'];x=uc.reg_read(UC_ARM_REG_XPSR)
   assert [uc.reg_read(r)for r in CERTLIVE]==cur['cert_live']and uc.reg_read(UC_ARM_REG_R4)==row['estimate']
   assert ((x>>30)&1)==int(not row['fast'])and ((x>>29)&1)==(row['estimate']>>31);out['classified']+=1
  if candidate and cur.get('cert_full_pc')and pc==cur['cert_full_pc']+2:
   assert uc.reg_read(UC_ARM_REG_R4)==cur['cert_model']['base'];out['restored']+=1
  if cur and e.named_sections['.ddiv'][3]<=pc<e.named_sections['.ddiv'][3]+e.named_sections['.ddiv'][5]and bytes(uc.mem_read(pc,2))==bytes.fromhex('f0bd'):
   sp=uc.reg_read(UC_ARM_REG_SP);assert sp==cur['sp']-20 and bytes(uc.mem_read(sp,20))==struct.pack('<5I',*cur['saved']);out['pops'].append(hex(cur['return']))
 def write(uc,access,a,n,v,user):
  pc=uc.reg_read(UC_ARM_REG_PC);assert not begin<=pc<done
  if candidate and cur.get('cert_begin'):assert not cur['cert_begin']<=pc<cur['cert_begin']+16
  if cur and not cur.get('returned')and 0xd0000060<=a<0xd000007c:
   assert active['state']!='DIRTY'
   if a==0xd0000064:cur['issue']=tick
 def read(uc,access,a,n,v,user):
  pc=uc.reg_read(UC_ARM_REG_PC)
  if begin<=pc<done:assert a==table+2*((cur['D']>>9)-128)and n==2;cur['reads']+=1
  if candidate and cur.get('cert_begin'):assert not cur['cert_begin']<=pc<cur['cert_begin']+16
  if cur and not cur.get('returned')and 0xd0000060<=a<0xd000007c:
   if active['state']=='DIRTY':assert a==0xd0000078
   if a==0xd0000070:assert tick-cur['issue']-1==9;out['latency9'].append(9)
 m.uc.hook_add(UC_HOOK_CODE,code);m.uc.hook_add(UC_HOOK_MEM_READ,read);m.uc.hook_add(UC_HOOK_MEM_WRITE,write);clear();return out,clear
def equivalent(co,ca):
 for key in ['calls','first','after','zeros','pre_cert','down','pack','seeds']:assert co[key]==ca[key],key
 assert len(co['certificates'])==len(ca['certificates'])==ca['classified']
 for c,n in zip(co['certificates'],ca['certificates']):
  assert {k:v for k,v in c.items()if k!='actual_full'}=={k:v for k,v in n.items()if k!='actual_full'}
def scalar():
 machines=loader();active=dict(public=False);traces={n:audit(machines[n],n,active)for n in ['control','candidate']};selection=json.loads((O/'scalar-selection.json').read_text());jobs={}
 def add(b,f,g):jobs.setdefault((b,f),g)
 for cl,r in selection['branch_class_examples'].items():
  for f in range(16):add(int(r['denominator'],16),f,cl+'_all16flags')
 for f in range(16):add(int(selection['remaining'][0]['denominator'],16),f,'remaining_DIRTY149_vs146_all16flags')
 parentselection=json.loads((R/'.build/m0-pow-reciprocal-inline-independent-20261025/scalar-selection.json').read_text())
 for r in parentselection['remaining']:add(int(r['denominator'],16),r['NZCV'],'parent_loss_now_fixed_or_retained')
 for r in selection['equal_states']:add(int(r['denominator'],16),r['NZCV'],'correct_Qfp_equality_not_strict')
 T=1<<50
 for mag in [0,1,T-1,T,T+1,(1<<52)-1]:
  for sign in [0,1]:add(mag|(sign<<63),mag&15,'signed_IEEE_overflow_edges')
 for E in [1,2044,2045,2046,2047]:
  for sign in [0,1]:add((E<<52)|123|(sign<<63),E&15,'guard_special_extreme')
 for b in [0x7ff0000000000000,0xfff0000000000000,0x7ff0000000000001,0xfff0000000000001,0x7ff8000000000000,0xfff8000000000000,bits(1.),bits(1.125),bits(1.5),bits(2.)]:add(b,0,'IEEE_dyadic')
 oracle=Oracle();cache={};rows=[];increases=Counter();classes=Counter();newdeficits=[]
 for (b,flags),group in jobs.items():
  if b not in cache:cache[b]=expected(oracle,'ddiv',bits(1.),b)
  exp=cache[b]
  for state_name,sio in states.items():
   active.update(state=state_name,flags=flags);run['current']=dict(stage='scalar',denominator=f'{b:016X}',flags=flags,SIO=state_name);results={};captures={}
   for label,m in machines.items():
    if label in traces:traces[label][1]()
    m.uc.mem_write(0xd0000060,sio);got,cost=call(m,'qfp_ddiv'if label=='Qfplib'else'mk61_m0_reciprocal1',bits(1.),b)
    after=bytes(m.uc.mem_read(0xd0000060,28));assert after==sio if state_name=='DIRTY'else not struct.unpack('<7I',after)[6]&2
    results[label]=dict(output=f'{got:016X}',instructions=cost,correct=equal(got,exp))
    if label in traces:captures[label]=json.loads(json.dumps(traces[label][0]));assert len(captures[label]['calls'])==len(captures[label]['pops'])==1
   assert results['parent']==results['control']and results['candidate']['output']==results['parent']['output']and all(results[n]['correct']for n in ['parent','control','candidate'])
   co,ca=captures['control'],captures['candidate'];equivalent(co,ca)
   pc,c=results['parent']['instructions'],results['candidate']['instructions'];assert pc-c==sum(r['expected_saving']for r in ca['certificates'])
   if c>pc:increases[c-pc]+=1
   if results['Qfplib']['correct']and c>results['Qfplib']['instructions']and pc<=results['Qfplib']['instructions']:newdeficits.append(run['current'])
   for r in ca['certificates']:classes[('fast'if r['fast']else'full')+'_'+r['decision']+('_cross'if r['cross_overflow']else'_nocross')]+=1
   rows.append(dict(denominator=f'{b:016X}',flags=flags,group=group,SIO=state_name,expected=f'{exp:016X}',results=results,captures=captures))
 assert set(increases)=={7,8}and len(classes)==8 and not newdeficits
 remain=[r for r in rows if r['denominator']=='3FF27D0DF6735E90'and r['SIO']=='DIRTY'];assert remain and all([r['results'][n]['instructions']for n in ['candidate','Qfplib']]==[149,146]for r in remain)
 save('scalar-arm-mpfr.json',dict(status='PASS_FRESH_PRIVATE_CERTIFICATE_LIVE_JOIN_ALL_EIGHT_CLASSES_AND_IEEE',flag_jobs=len(jobs),distinct_denominators=len(cache),actual_ARM_calls=run['completed'],directed_MPFR_inputs=run['MPFR'],sNaN_shortcuts=run['sNaN'],MPFR_version=oracle.version,
  all16NZCV_each_branch_class_and_remaining_loss=True,every_pre_certificate_R0_R7_R12_SP_NZCV_frame28_equal=True,
  known_zero_yL_and_classifier_ZC_actual_branch_restore_live_down_pack_checked=True,original_frame20_entry_return_PCS_and_inline_ownentrySPminus20_checked=True,
  DIRTY7words_no_writes_READY9ALU_unchanged=True,classes=dict(classes),observed_parent_cost_increases=dict(increases),all_correct_wrong_Qfp_and_increases_retained=True,
  remaining_DIRTY149_vs146_reproduced=True,new_correctQfp_deficits=newdeficits,no_universal_parent_performance_claim=True,observed_stack_bytes={n:SP-m.stack_lowest for n,m in machines.items()},rows=rows,device_IO=0))
def public():
 machines=loader();active=dict(public=True);traces={n:audit(machines[n],n,active)for n in ['control','candidate']};selection=json.loads((O/'selected-public-jobs.json').read_text());jobs={(int(r['x'],16),int(r['y'],16)):r['group']for r in selection['jobs']}
 for a,b in [(0,0),(1,bits(.5)),(bits(-2.),bits(.5)),(0x7fefffffffffffff,bits(-.5)),(bits(1.),0x7ff0000000000001),(0xfff0000000000001,bits(0.))]:jobs[a,b]='IEEE_sNaN_control'
 refs=['qfp_composed_pow','qfp_composed_pow_exact','qfp_composed_pow_integer'];oracle=Oracle();rows=[];classes=Counter();slow_witness=[]
 strict={tuple(x)for x in selection['strict_fixed_pairs']};eqfix={tuple(x)for x in selection['equal_fixed_pairs']};fix_has_equal=False
 for (a,b),group in jobs.items():
  exp=expected(oracle,'pow',a,b)
  for state_name,sio in states.items():
   active['state']=state_name;run['current']=dict(stage='public',x=f'{a:016X}',y=f'{b:016X}',SIO=state_name);outputs={};costs={};correct={};captures={}
   for label in ['parent','control','candidate',*refs]:
    m=machines[label if label in machines else'Qfplib']
    if label in traces:traces[label][1]()
    m.uc.mem_write(0xd0000060,sio);got,cost=call(m,label if label in refs else'_ZN12compact_math3powEdd',a,b)
    after=bytes(m.uc.mem_read(0xd0000060,28));assert after==sio if state_name=='DIRTY'else not struct.unpack('<7I',after)[6]&2
    outputs[label]=f'{got:016X}';costs[label]=cost;correct[label]=equal(got,exp)
    if label not in refs:assert correct[label]
    if label in traces:captures[label]=json.loads(json.dumps(traces[label][0]))
   co,ca=captures['control'],captures['candidate'];equivalent(co,ca);assert outputs['parent']==outputs['control']==outputs['candidate']and costs['parent']==costs['control']
   assert len(ca['calls'])==len(ca['pops'])==len(ca['returns']);assert costs['parent']-costs['candidate']==sum(r['expected_saving']for r in ca['certificates'])
   pair=f'{a:016X}',f'{b:016X}'
   if pair in strict:assert all(costs['candidate']<costs[n]for n in refs if correct[n])
   if pair in eqfix:
    assert all(costs['candidate']<=costs[n]for n in refs if correct[n]);fix_has_equal |= any(costs['candidate']==costs[n]for n in refs if correct[n])
   if pair==('3FF2C7DE5B557A7D','C028000000000000'):
    assert costs['candidate']==costs['parent']+8 and all(costs['parent']>costs[n]for n in refs if correct[n]);slow_witness.append(dict(SIO=state_name,parent=costs['parent'],candidate=costs['candidate'],references={n:costs[n]for n in refs}))
   for r in ca['certificates']:classes[('fast'if r['fast']else'full')+'_'+r['decision']+('_cross'if r['cross_overflow']else'_nocross')]+=1
   rows.append(dict(x=pair[0],y=pair[1],SIO=state_name,group=group,expected=f'{exp:016X}',outputs=outputs,instructions=costs,correct=correct,captures=captures))
 assert fix_has_equal and len(slow_witness)==2 and any(v['entry_SP']!=SP for r in rows for v in r['captures']['candidate']['inline'])
 save('public-arm-mpfr.json',dict(status='PASS_NESTED_REAL_ROOT_CALLER_STRICT_EQUALITY_FIX_AND_TWO_EXPLICIT_REGRESSIONS',pairs=len(jobs),actual_ARM_calls=run['completed'],directed_MPFR_inputs=run['MPFR'],sNaN_shortcuts=run['sNaN'],MPFR_version=oracle.version,
  strict_pair_and_equality_pair_separate=True,both_already_losing_correctQfp_further_slowed_witnesses=slow_witness,
  fresh_positive_one_caller_return_site_frame20_private_guard_R6_R12_and_all_live_joins=True,
  nested_inlineSP_ownentryminus20_not_outerSP=True,every_actual_classifier_branch_and_full_restore_and_live_RNE_skip_checked=True,
  READY9ALU_and_DIRTY7words_preserved=True,classes=dict(classes),all3realQfp_outputs_correctness_and_costs_retained=True,
  no_generic_ABI_or_integration_performance_GO=True,near_one_sibling_not_loaded=True,observed_stack_bytes={n:SP-m.stack_lowest for n,m in machines.items()},rows=rows,device_IO=0))
if __name__=='__main__':
 assert len(sys.argv)==2 and sys.argv[1]in ['unit','scalar','public']
 try:globals()[sys.argv[1]]()
 except BaseException:
  save('RUNTIME-FAILURE-'+sys.argv[1]+'.json',dict(status='EXCLUDED_INCOMPLETE_OWN_RUNTIME_CHECK',run=run,completed_calls=run['completed'],partial_calls=run['started']-run['completed'],traceback=traceback.format_exc(),device_IO=0));raise
