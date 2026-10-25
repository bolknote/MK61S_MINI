"""Bounded bare certificate and fresh real private-context CPU qualification."""
import ast,hashlib,json,random,struct,sys,traceback
from collections import Counter
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-reciprocal-bound3-20261025';P=R/'.build/m0-pow-reciprocal-zero-20261025'
SUP=R/'.build/m0-float-fma-qualification-20261023/support';sys.path[:0]=[str(SUP),str(R/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP,STOP,bits
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R12,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_XPSR
MASK=(1<<32)-1;RAW=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3];REGS=[*RAW,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R12,UC_ARM_REG_SP,UC_ARM_REG_XPSR]
LIVE=[*RAW,UC_ARM_REG_R5,UC_ARM_REG_R12,UC_ARM_REG_SP];CERTLIVE=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R12,UC_ARM_REG_SP]
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
fn=next(n for n in ast.parse((R/'.build/m0-pow-reciprocal-certificate-independent-20261025/accounting.py').read_text()).body if isinstance(n,ast.FunctionDef)and n.name=='certificate');exec(compile(ast.Module(body=[fn],type_ignores=[]),'<accepted-universal-certificate-arithmetic>','exec'),globals())
DOMAIN={r['D']:r for r in json.loads((O/'integer-domain.json').read_text())['rows']}
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
  for suffix in ['_first_product','_before_second_product','_after_second_product','_after_y_residual','_half_normalization','_y_low_shift','_certificate_begin','_certificate_full','_certificate_up','_certificate_down','_pack_begin']:at[e.symbols[tag+suffix]&~1]=(suffix,tag)
 begin=e.symbols['mk61_m0_inline_seed_begin']&~1;done=e.symbols['mk61_m0_inline_seed_done']&~1;table=e.named_sections['.ddiv'][3]+e.named_sections['.ddiv'][5]-256
 out={};cur={};tick=0
 def clear():out.update(calls=[],first=[],before=[],after=[],residual=[],half=[],zeros=[],pre_cert=[],certificates=[],down=[],pack=[],inline=[],pops=[],returns=[],latency9=[],seeds=[],classified=0,restored=0,zero_up=0,rounded=[]);cur.clear()
 def code(uc,pc,n,user):
  nonlocal tick
  tick+=1
  if cur and pc==cur['return']:
   assert uc.reg_read(UC_ARM_REG_SP)==cur['sp'];out['returns'].append(pc);cur['returned']=True
  if pc==entry:
   raw=[uc.reg_read(r)for r in RAW];assert raw[:2]==[0,0x3ff00000];sp=uc.reg_read(UC_ARM_REG_SP);assert sp%8==0
   ret=uc.reg_read(UC_ARM_REG_LR)&~1;assert ret==(0x1014f118 if active['public']else STOP)
   cur.clear();cur.update(raw=raw,sp=sp,saved=[uc.reg_read(r)for r in [UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_LR]],return_=ret);cur['return']=ret
   out['calls'].append(dict(numerator='3FF0000000000000',denominator=f'{raw[2]|raw[3]<<32:016X}',entry_SP=sp,return_site=hex(ret)))
   if not active['public']:uc.reg_write(UC_ARM_REG_XPSR,0x01000000|(active['flags']<<28));uc.reg_write(UC_ARM_REG_R12,0x03251000|active['flags'])
  if pc==sw:
   raw=cur['raw'];E=(raw[3]>>20)&2047;assert 1<=E<=2044 and uc.reg_read(UC_ARM_REG_R6)==2044-E and [uc.reg_read(r)for r in RAW]==raw and uc.reg_read(UC_ARM_REG_SP)==cur['sp']-20
  if pc==begin:
   raw=cur['raw'];E=(raw[3]>>20)&2047;sp=uc.reg_read(UC_ARM_REG_SP);D=uc.reg_read(UC_ARM_REG_R1)
   assert D==((raw[3]&0xfffff)|0x100000)>>4 and 65536<=D<131072 and uc.reg_read(UC_ARM_REG_R12)==4*(2044-E)+(raw[3]>>31)
   assert sp==cur['sp']-20 and bytes(uc.mem_read(sp,20))==struct.pack('<5I',*cur['saved'])
   assert uc.reg_read(UC_ARM_REG_R0)==0 and uc.reg_read(UC_ARM_REG_R2)==raw[2]and uc.reg_read(UC_ARM_REG_R3)==((raw[3]&0xfffff)|0x100000)
   cur['inline_live']=[uc.reg_read(r)for r in LIVE];cur['D']=D;cur['reads']=0;out['seeds'].append(D)
  if pc==done:
   assert [uc.reg_read(r)for r in LIVE]==cur['inline_live']and cur['reads']==1 and uc.reg_read(UC_ARM_REG_R6)==MASK//cur['D']and uc.reg_read(UC_ARM_REG_R7)==((MASK%cur['D']-cur['D'])&MASK if candidate and DOMAIN[cur['D']]['error']==3 else MASK%cur['D'])
   out['inline'].append(dict(entry_SP=cur['sp'],inline_SP=uc.reg_read(UC_ARM_REG_SP),D=cur['D']))
  if pc==done+4:out['rounded'].append(state(uc))
  if pc in at:
   suffix,tag=at[pc]
   if suffix=='_first_product':assert uc.reg_read(UC_ARM_REG_R0)==0;out['first'].append(uc.reg_read(UC_ARM_REG_R6))
   if suffix=='_before_second_product':assert uc.reg_read(UC_ARM_REG_R0)==uc.reg_read(UC_ARM_REG_R4)==0;out['before'].append(state(uc))
   if suffix=='_after_second_product':assert uc.reg_read(UC_ARM_REG_SP)==cur['sp']-28;assert uc.reg_read(UC_ARM_REG_R4)==0;out['after'].append(state(uc))
   if suffix=='_after_y_residual':assert uc.reg_read(UC_ARM_REG_R4)==0;out['residual'].append(state(uc))
   if suffix=='_half_normalization':assert uc.reg_read(UC_ARM_REG_R4)==0;out['half'].append(0)
   if suffix=='_y_low_shift':assert uc.reg_read(UC_ARM_REG_R4)==0;out['zeros'].append(state(uc))
   if suffix=='_certificate_begin':
    assert uc.reg_read(UC_ARM_REG_R6)==0;out['pre_cert'].append(state(uc))
    model=certificate(uc.reg_read(UC_ARM_REG_R4),uc.reg_read(UC_ARM_REG_R2),uc.reg_read(UC_ARM_REG_R0));model.pop('expected_saving')
    cur['model']=model;cur['midpoint']=[uc.reg_read(r)for r in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R12,UC_ARM_REG_SP]]
    cur['cert_live']=[uc.reg_read(r)for r in CERTLIVE];cur['cert_begin']=pc;cur['full_pc']=e.symbols[tag+'_certificate_full']&~1
    out['certificates'].append(dict(model,actual_full=False,actual_decision=None))
   if suffix=='_certificate_full':
    row=out['certificates'][-1];assert not row['fast']and uc.reg_read(UC_ARM_REG_R4)==row['estimate']and uc.reg_read(UC_ARM_REG_R5)==(row['u']>>16)*(row['v']>>16);row['actual_full']=True
   if suffix=='_certificate_up':
    row=out['certificates'][-1];assert not row['negative']and [uc.reg_read(r)for r in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R12,UC_ARM_REG_SP]]==cur['midpoint'];row['actual_decision']='up'
    if candidate:assert uc.reg_read(UC_ARM_REG_R6)==0;out['zero_up']+=1
   if suffix=='_certificate_down':
    row=out['certificates'][-1]
    if row['actual_decision']is None:assert row['negative'];row['actual_decision']='down'
    assert row['actual_full']==row['full']
    if candidate and row['fast']:assert uc.reg_read(UC_ARM_REG_R6)==0
    wanted=cur['midpoint'].copy()
    if not row['negative']:
     z=(wanted[0]|wanted[1]<<32)+1;wanted[0],wanted[1]=z&MASK,(z>>32)&MASK
    assert [uc.reg_read(r)for r in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R12,UC_ARM_REG_SP]]==wanted;out['down'].append(wanted)
   if suffix=='_pack_begin':out['pack'].append(state(uc))
  if candidate and cur.get('cert_begin')and pc==cur['cert_begin']+12:
   row=cur['model'];x=uc.reg_read(UC_ARM_REG_XPSR)
   assert [uc.reg_read(r)for r in CERTLIVE]==cur['cert_live']and uc.reg_read(UC_ARM_REG_R4)==row['estimate']and uc.reg_read(UC_ARM_REG_R6)==0
   assert ((x>>30)&1)==int(not row['fast'])and ((x>>29)&1)==row['estimate']>>31;out['classified']+=1
  if cur.get('full_pc')and pc==cur['full_pc']+2:assert uc.reg_read(UC_ARM_REG_R4)==cur['model']['base'];out['restored']+=1
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
def equivalent(c,n):
 for key in ['calls','first','after','residual','half','zeros','pre_cert','certificates','down','pack','seeds']:assert c[key]==n[key],key
 for key in ['before','rounded']:
  assert len(c[key])==len(n[key])
  for a,b in zip(c[key],n[key]):
   assert a['frame28']==b['frame28']and[x for i,x in enumerate(a['registers'])if i!=7]==[x for i,x in enumerate(b['registers'])if i!=7],key
   D=a['registers'][1];delta=D if D in DOMAIN and DOMAIN[D]['error']==3 else 0;assert b['registers'][7]==(a['registers'][7]-delta)&MASK
 assert len(n['certificates'])==n['classified']
def saving(t):return 3*sum(DOMAIN[D]['error']==3 for D in t['seeds'])
def unit():
 machines={label:Machine(O/'rebuild/unit'/(label+'.elf'),True)for label in ['control','candidate']};active={};rng=random.Random(0xB0032025);rows=[];classes=Counter()
 for label,m in machines.items():
  assert not m.rom_models and not m.rom_initializers
  begin=m.elf.symbols['mk61_m0_inline_seed_begin']&~1;done=m.elf.symbols['mk61_m0_inline_seed_done']&~1;table=m.elf.named_sections['.unit'][3]+m.elf.named_sections['.unit'][5]-256
  def hooks(label,begin,done,table):
   def code(uc,pc,n,user):
    if pc==begin:
     assert uc.reg_read(UC_ARM_REG_R0)==0;uc.reg_write(UC_ARM_REG_XPSR,0x01000000|(active['flags']<<28));uc.reg_write(UC_ARM_REG_R5,active['r5']);uc.reg_write(UC_ARM_REG_R12,active['r12'])
     active[label+'_live']=[uc.reg_read(r)for r in LIVE];active[label+'_frame']=bytes(uc.mem_read(SP-20,20));active[label+'_reads']=0;active[label+'_bpl']=False;active[label+'_sbc']=False
    if label=='candidate'and pc==done-8:active[label+'_bpl']=True
    if label=='candidate'and pc==done-2:
     assert active['error']in [2,3]and uc.reg_read(UC_ARM_REG_R0)==0 and ((uc.reg_read(UC_ARM_REG_XPSR)>>29)&1)==int(active['error']==2);active[label+'_sbc']=True
    if pc==done:
     assert [uc.reg_read(r)for r in LIVE]==active[label+'_live']and bytes(uc.mem_read(SP-20,20))==active[label+'_frame']
     row=DOMAIN[active['D']];assert uc.reg_read(UC_ARM_REG_R6)==row['quotient']and uc.reg_read(UC_ARM_REG_R7)==(row['new_residue']if label=='candidate'else row['old_residue'])
     assert active[label+'_reads']==1
   def read(uc,access,a,n,v,user):
    if begin<=uc.reg_read(UC_ARM_REG_PC)<done:assert n==2 and a==table+2*((active['D']>>9)-128);active[label+'_reads']+=1
   def write(uc,access,a,n,v,user):assert SP-20<=a<a+n<=SP and not begin<=uc.reg_read(UC_ARM_REG_PC)<done
   return code,read,write
  code,read,write=hooks(label,begin,done,table);m.uc.hook_add(UC_HOOK_CODE,code);m.uc.hook_add(UC_HOOK_MEM_READ,read);m.uc.hook_add(UC_HOOK_MEM_WRITE,write)
 for D in json.loads((O/'unit-selection.json').read_text())['values']:
  for flags in range(16):
   active.update(D=D,flags=flags,error=DOMAIN[D]['error'],r5=rng.getrandbits(32),r12=rng.getrandbits(32));run['current']=dict(stage='unit',D=D,NZCV=flags);results={}
   b=rng.getrandbits(64)
   for label,m in machines.items():
    got,cost=call(m,'unit_inline_seed',D<<32,b);assert got&MASK==DOMAIN[D]['quotient'];results[label]=cost
   assert active['candidate_bpl']==(active['error']>0)and active['candidate_sbc']==(active['error']>=2)
   assert results['control']-results['candidate']==(3 if active['error']==3 else 0);classes[active['error']]+=1
   rows.append(dict(D=D,NZCV=flags,error=active['error'],quotient=DOMAIN[D]['quotient'],old_residue=DOMAIN[D]['old_residue'],new_residue=DOMAIN[D]['new_residue'],instructions=results))
 assert set(classes)=={-1,0,1,2,3}
 save('unit-arm.json',dict(status='PASS_BOUNDED_ACTUAL_THUMB_ALL5_ERRORS_ALL16_FLAGS_PRIVATE_ZERO_AND_BORROW',tests=len(rows),actual_ARM_calls=run['completed'],all16flags_each_selected_D=True,
  R0zero_precondition_and_R0_R1_R2_R3_R5_R12_SP_frame20_preserved=True,quotient_exact_all5classes_and_only_error3_R7_minusD=True,
  actual_BPL_error1_exit_and_second_ADDcarry_error2_3_immediate_SBC_checked=True,one_aligned_table_read_no_macro_stackwrites_calls=True,
  Machine_PCS_SP_PC_checked=True,instruction_nonincrease_NOT_cycle_nonregression=True,classes=dict(classes),rows=rows,devices=0))
def execute(machines,traces,active,a,b,exp,state_name,public):
 sio=states[state_name];active['state']=state_name;results={};captures={};refs=['qfp_composed_pow','qfp_composed_pow_exact','qfp_composed_pow_integer']if public else['Qfplib']
 for label in ['parent','control','candidate',*refs]:
  m=machines[label if label in machines else'Qfplib']
  if label in traces:traces[label][1]()
  m.uc.mem_write(0xd0000060,sio)
  fn=label if label in refs and public else'qfp_ddiv'if label=='Qfplib'else'_ZN12compact_math3powEdd'if public else'mk61_m0_reciprocal1'
  got,cost=call(m,fn,a,b);after=bytes(m.uc.mem_read(0xd0000060,28));assert after==sio if state_name=='DIRTY'else not struct.unpack('<7I',after)[6]&2
  results[label]=dict(output=f'{got:016X}',instructions=cost,correct=equal(got,exp))
  if label in traces:captures[label]=json.loads(json.dumps(traces[label][0]))
 assert results['parent']==results['control']and results['candidate']['output']==results['parent']['output']and all(results[n]['correct']for n in ['parent','control','candidate'])
 c,n=captures['control'],captures['candidate'];equivalent(c,n)
 assert results['parent']['instructions']-results['candidate']['instructions']==saving(n)>=0
 assert len(n['calls'])==len(n['pops'])
 if public:assert len(n['returns'])==len(n['calls'])
 return results,captures
def scalar():
 machines=loader();active=dict(public=False);traces={n:audit(machines[n],n,active)for n in ['control','candidate']};sel=json.loads((O/'scalar-selection.json').read_text());prior=json.loads((R/'.build/m0-pow-reciprocal-zero-independent-20261025/scalar-selection.json').read_text());jobs={}
 def add(b,f,g):jobs.setdefault((b,f),g)
 for error,r in sel['all5_error_class_examples'].items():
  for f in range(16):add(int(r['denominator'],16),f,'error_'+error+'_all16flags')
 for cl,r in prior['branch_class_examples'].items():
  for f in range(16):add(int(r['denominator'],16),f,'R3certificate_'+cl+'_all16flags')
 for r in sel['expanded_two_old_losses_now_fixed']:
  for f in range(16):add(int(r['denominator'],16),f,'old_expanded_loss_all16flags')
 T=1<<50
 for mag in [0,1,T-1,T,T+1,(1<<52)-1]:
  for sign in [0,1]:add(mag|(sign<<63),mag&15,'IEEE_tiny_signed_edges')
 for E in [1,2044,2045,2046,2047]:
  for sign in [0,1]:add((E<<52)|123|(sign<<63),E&15,'guard_special_extreme')
 for b in [0x7ff0000000000000,0xfff0000000000000,0x7ff0000000000001,0xfff0000000000001,0x7ff8000000000000,0xfff8000000000000,bits(1.),bits(1.125),bits(1.5),bits(2.)]:add(b,0,'IEEE_dyadic')
 oracle=Oracle();cache={};rows=[];deltas=Counter();observed_errors=Counter();fixed_seen=set()
 for (b,f),group in jobs.items():
  if b not in cache:cache[b]=expected(oracle,'ddiv',bits(1.),b)
  active['flags']=f
  for sio in states:
   run['current']=dict(stage='scalar',D=f'{b:016X}',NZCV=f,SIO=sio);rr,cc=execute(machines,traces,active,bits(1.),b,cache[b],sio,False);deltas[rr['candidate']['instructions']-rr['parent']['instructions']]+=1
   for D in cc['candidate']['seeds']:observed_errors[DOMAIN[D]['error']]+=1
   for r in sel['expanded_two_old_losses_now_fixed']:
    if f'{b:016X}'==r['denominator']and sio=='DIRTY':
     assert [rr[n]['instructions']for n in ['parent','candidate','Qfplib']]==[r['results'][n]['instructions']for n in ['parent','candidate','Qfplib']];assert rr['candidate']['instructions']<=rr['Qfplib']['instructions'];fixed_seen.add(b)
   rows.append(dict(denominator=f'{b:016X}',flags=f,group=group,SIO=sio,expected=f'{cache[b]:016X}',results=rr,captures=cc))
 assert set(observed_errors)=={-1,0,1,2,3}and len(fixed_seen)==2 and set(deltas)<={0,-3}
 save('scalar-arm-mpfr.json',dict(status='PASS_FRESH_PRIVATE_R0_ZERO_NEW_R7_RULE_THEN_COMPLETE_ALL_LIVE_JOINS',flag_jobs=len(jobs),distinct_denominators=len(cache),actual_ARM_calls=run['completed'],directed_MPFR_inputs=run['MPFR'],sNaN_shortcuts=run['sNaN'],MPFR_version=oracle.version,
  all5seed_errors_all16NZCV=True,post_ADD1_LSR_NZCV_and_all_live_registers_equal_except_exact_R7_minusD_error3=True,
  R7_dead_before_overwrite_then_entire_after_second_residual_certificate_pack_equal=True,
  Zero_scratch_R3certificate_and_fullpositive_zero_contracts_freshly_checked=True,
  original_frame20_PCS_R6guard_R12_rawoperands_inline_ownSP_READY9ALU_DIRTY7words_checked=True,
  both_old_expanded_losses_actually_fixed_instructions_not_cycles=True,no_generic_seed_or_CABI=True,
  error1_branch_direction_cycle_effect_unmeasured=True,old_control_and_candidate_roles_separate=True,
  error_counts=dict(observed_errors),instruction_deltas=dict(deltas),all_correct_wrong_Qfp_results_costs_retained=True,
  no_universal_Qfp_speed_or_performanceadoption_GO=True,observed_stack_bytes={n:SP-m.stack_lowest for n,m in machines.items()},rows=rows,devices=0))
def public():
 machines=loader();active=dict(public=True);traces={n:audit(machines[n],n,active)for n in ['control','candidate']};sel=json.loads((O/'selected-public-jobs.json').read_text());jobs={(int(r['x'],16),int(r['y'],16)):r['group']for r in sel['jobs']};anc={(r['x'],r['y'],r['SIO']):r for r in sel['ancestry32']}
 for a,b in [(0,0),(1,bits(.5)),(bits(-2.),bits(.5)),(0x7fefffffffffffff,bits(-.5)),(bits(1.),0x7ff0000000000001),(0xfff0000000000001,bits(0.))]:jobs[a,b]='IEEE_sNaN_control'
 oracle=Oracle();rows=[];anc_checked=[];fast=0
 for (a,b),group in jobs.items():
  exp=expected(oracle,'pow',a,b)
  for sio in states:
   run['current']=dict(stage='public',x=f'{a:016X}',y=f'{b:016X}',SIO=sio);rr,cc=execute(machines,traces,active,a,b,exp,sio,True)
   fast+=rr['candidate']['instructions']<rr['parent']['instructions'];key=f'{a:016X}',f'{b:016X}',sio
   if key in anc and anc[key]['has_correct_Qfp']:
    r=anc[key];assert rr['parent']['instructions']==r['Zero']and rr['candidate']['instructions']==r['Bound3']and r['Bound3']>r['Inline']
    assert all(rr['candidate']['instructions']>v['instructions']for n,v in rr.items()if n.startswith('qfp_')and v['correct']);anc_checked.append(r)
   rows.append(dict(x=key[0],y=key[1],SIO=sio,group=group,expected=f'{exp:016X}',results=rr,captures=cc))
 assert fast and len(anc_checked)==2 and any(v['entry_SP']!=SP for r in rows for v in r['captures']['candidate']['inline'])
 save('public-arm-mpfr.json',dict(status='PASS_FRESH_NESTED_SOLE_CALLER_BOUND3_SEED_AND_FULL_RNE_CONTEXT',pairs=len(jobs),actual_ARM_calls=run['completed'],directed_MPFR_inputs=run['MPFR'],sNaN_shortcuts=run['sNaN'],MPFR_version=oracle.version,
  positive1_rawR0zero_at_actual_inline_SBC_caller_and_actual_BL_return_checked=True,
  exact_R7_dead_delta_then_full_product_residual_certificate_pack_NZCV_frame28_equal=True,
  all3real_Qfp_correct_wrong_outputs_and_costs_retained=True,oldloop_control_roles_separate=True,
  ancestral2_already_losing_regressions_still_kept=anc_checked,instruction_saving3_NOT_cycle_or_adoption_GO=True,
  no_generic_ABI_near_one_not_loaded=True,observed_stack_bytes={n:SP-m.stack_lowest for n,m in machines.items()},rows=rows,devices=0))
if __name__=='__main__':
 assert len(sys.argv)==2 and sys.argv[1]in ['unit','scalar','public']
 try:globals()[sys.argv[1]]()
 except BaseException:
  save('RUNTIME-FAILURE-'+sys.argv[1]+'.json',dict(status='EXCLUDED_INCOMPLETE_OWN_RUNTIME_CHECK',run=run,completed_calls=run['completed'],partial_calls=run['started']-run['completed'],traceback=traceback.format_exc(),devices=0));raise
