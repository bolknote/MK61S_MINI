"""Independent focused public ARM/MPFR and exact bare-unit adversaries."""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter
import hashlib,json,math,struct,sys
sys.dont_write_bytecode=True
from bounds import R,P,V,O,S,table62,delta32,remaining,normalized,product_error,model,round_fraction
Q=R/'.build/m0-float-fma-qualification-20261023'
sys.path[:0]=[str(Q),str(Q/'support'),str(R/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from m0_mpfr_oracle import Oracle,bits
from check_stm32_vectors import ElfImage
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def equal(a,b):
 return a==b or (a&0x7fffffffffffffff)>0x7ff0000000000000 and (b&0x7fffffffffffffff)>0x7ff0000000000000
assert read(O/'binding-rebuild.json')['status'].startswith('PASS_')
saved=read(P/'qualification.json');rows=saved['rows'];idx={(r['x'],r['SIO']):r for r in rows}
assert len(idx)==97526 and len({r['x'] for r in rows})==48763
previous=read(R/'.build/m0-exp-tight-firstpass-20261024/qualification.json')
assert len(previous['rows'])==len(rows)
for a,b in zip(rows,previous['rows']):
 assert (a['x'],a['SIO'],a['group'],a['expected'])==(b['x'],b['SIO'],b['group'],b['expected'])
 for label in ['resident','control','Qfplib']:
  assert a['outputs'][label]==b['outputs'][label] and a['instructions'][label]==b['instructions'][label] and a['correct'][label]==b['correct'][label]
 assert a['outputs']['candidate']==a['outputs']['tight_trial']==b['outputs']['candidate']
 assert a['instructions']['tight_trial']==b['instructions']['candidate']
 assert a['instructions']['candidate']-a['instructions']['tight_trial'] in (-7,0)
 assert a['correct']['candidate'] and equal(int(a['outputs']['candidate'],16),int(a['expected'],16))
del previous
def loss(r,n):return r['correct']['Qfplib'] and r['instructions'][n]>r['instructions']['Qfplib']
count={n:len({r['x'] for r in rows if loss(r,n)}) for n in ['resident','tight_trial','candidate']}
assert count==dict(resident=6149,tight_trial=460,candidate=395)
assert not any(loss(r,'candidate') and not loss(r,'resident') for r in rows)
assert not any(loss(r,'candidate') and not loss(r,'tight_trial') for r in rows)
hist=Counter(r['instructions']['candidate']-r['instructions']['control'] for r in rows if r['instructions']['candidate']>r['instructions']['control'])
assert sum(hist.values())==5800 and max(hist)==39
retained=read(P/'retained-exp-regressions.json')
retained_rows=retained.get('rows',retained.get('regressions'))
assert retained_rows is not None and len(retained_rows)==5800
assert {(r['x'],r['SIO']) for r in retained_rows}=={(r['x'],r['SIO']) for r in rows if r['instructions']['candidate']>r['instructions']['control']}
jobs={}
def add(raw,group):
 if 0<=raw<1<<64:jobs.setdefault(raw,group)
old=read(V/'slower-inputs.json')['rows'];historical={int(r['x'],16) for r in old if r['operation']=='exp'}
assert len(historical)==16
for raw in sorted(historical):add(raw,'all_historical16')
costseen=set();newtight=set();tailseen=set();normseen=set();biasseen=set()
chosen_indices=set(sorted(range(512),key=lambda i:abs(delta32[i]-0x58000000))[:2]+sorted(range(512),key=lambda i:abs(delta32[i]+0x58000000))[:2]+[delta32.index(min(delta32)),delta32.index(max(delta32)),0,1,511])
for r in rows:
 if r['SIO']!='READY':continue
 raw=int(r['x'],16);d=r['instructions']['candidate']-r['instructions']['control']
 if d>0 and d not in costseen:add(raw,'each_retained_regression_cost_witness');costseen.add(d)
 if loss(r,'tight_trial') and not loss(r,'resident'):
  newtight.add(raw);add(raw,'all_old_tight_new_losses_now_closed')
 m=model(raw)
 if m and not m.get('fallback') and not m['tiny']:
  key=(m['normalized'],m['tail'],raw>>63)
  if 504<=m['tail']<=520 and key not in tailseen:
   add(raw,'actual_guard_tail_both_signs');tailseen.add(key)
  if m['normalized'] and (m['k'],raw>>63) not in normseen:
   add(raw,'actual_normalized_binades');normseen.add((m['k'],raw>>63))
  if m['index'] in chosen_indices and (m['index'],raw>>63) not in biasseen:
   add(raw,'actual_Q94_bias_extreme_rows');biasseen.add((m['index'],raw>>63))
assert costseen==set(hist) and len(newtight)==61
# A few fresh neighbours of exact changed-gate witnesses; these were not
# chosen from broad random replay and need not be part of the old corpus.
witnesses=[raw for raw,g in jobs.items() if g in ('actual_guard_tail_both_signs','actual_Q94_bias_extreme_rows')]
for raw in witnesses[::4]:
 for off in [-2,-1,1,2]:add(raw+off,'fresh_neighbours_of_changed_gate_witness')
for raw in [0,1,2,(1<<52)-1,1<<52,0x7fefffffffffffff,0x7ff0000000000000,0x7ff0000000000001,0x7ff8000000000042]:
 for sign in [0,1<<63]:add(raw|sign,'IEEE')
for x in [2**-54,2**-40,2**-11,0.0007,709.782712893384,-745.1332191019411,1024.0]:
 for raw in [bits(x),bits(-x)]:
  for off in [-2,-1,0,1,2]:add(raw+off,'source_domain_and_endpoint_neighbours')
for n in [-524288,-131073,-513,-512,-511,-1,0,1,255,256,511,512,513,131073,524287]:
 raw=bits((n+0.5)*math.log(2)/512)
 for off in [-1,0,1]:add(raw+off,'fresh_segment_estimate_midpoints')
ROM=R/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
BASE=V/'firmware/mk61s-picocalc-pico-h.elf';REF=R/'.build/m0-v138-execution-20261023/reference/reference.elf'
machines={};traces={label:Counter() for label in ['candidate','control']};products={label:[] for label in traces}
for label in ['candidate','control']:
 m=Machine(BASE,True,bootrom=ROM);e=ElfImage(P/(label+'.elf'));e.load(m.uc);m.elf.symbols['review_exp']=e.symbols['mk61_m0_exp'];machines[label]=m
 for name in ['exp_refine','mk61_m0_cr_exp','mk61_m0_exp_endpoint']:
  a=e.symbols[name]&~1
  def hook(uc,a,s,u,label=label,name=name):traces[label][name]+=1
  m.uc.hook_add(UC_HOOK_CODE,hook,begin=a,end=a)
 def prod(uc,a,s,u,label=label):
  aa=uc.reg_read(UC_ARM_REG_R0)|(uc.reg_read(UC_ARM_REG_R1)<<32);bb=uc.reg_read(UC_ARM_REG_R2)|(uc.reg_read(UC_ARM_REG_R3)<<32)
  assert aa<1<<63 and bb<1<<54
  products[label].append((aa,bb))
 m.uc.hook_add(UC_HOOK_CODE,prod,begin=0x20038ee4,end=0x20038ee4)
machines['Qfplib']=Machine(REF,True)
oracle=Oracle();states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
public=[];model_checks=0
for ji,(raw,group) in enumerate(jobs.items()):
 if ji%128==0:print('public',ji,'/',len(jobs),flush=True)
 expected=oracle.reference('exp',raw)
 for sn,state in states.items():
  outputs={};counts={};correct={};trace={}
  for label,m in machines.items():
   before=dict(traces.get(label,{}));products.get(label,[]).clear()
   m.uc.mem_write(0xd0000060,state);got,_,cost=m.call('qfp_dexp' if label=='Qfplib' else 'review_exp',raw,count=True)
   outputs[label]=f'{got:016X}';counts[label]=cost;correct[label]=equal(got,expected)
   if label!='Qfplib':assert correct[label],(label,hex(raw),hex(got),hex(expected))
   after=bytes(m.uc.mem_read(0xd0000060,28))
   if sn=='DIRTY':assert after==state
   else:assert not struct.unpack('<7I',after)[6]&2
   if label in traces:trace[label]={n:traces[label][n]-before.get(n,0) for n in traces[label]}
  assert outputs['candidate']==outputs['control']
  prev=idx.get((f'{raw:016X}',sn))
  if prev:
   for label in machines:assert outputs[label]==prev['outputs'][label] and counts[label]==prev['instructions'][label],(hex(raw),sn,label,counts,prev['instructions'])
  md=model(raw)
  if md and not md.get('fallback') and products['candidate']:
   assert md['b']==products['candidate'][0][1] and table62[md['index']]==products['candidate'][0][0]
   model_checks+=1
  public.append(dict(x=f'{raw:016X}',group=group,SIO=sn,expected=f'{expected:016X}',outputs=outputs,instructions=counts,correct=correct,trace=trace))
(O/'public-results.json').write_text(json.dumps(dict(status='PASS_FOCUSED_PUBLIC_EXP',MPFR=oracle.version,unique_inputs=len(jobs),actual_ARM_calls=6*len(jobs),actual_MPFR_calls=len(jobs),rows=public),indent=2)+'\n')
# Bare unit accesses must stay inside its defined functions/tables/stack.
# Neither the full firmware nor ROM is loaded in this machine.
unit=Machine(P/'unit.elf',True,stack_bytes=512);ue=ElfImage(P/'unit.elf');sio=[0]
unit.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,lambda *x:sio.__setitem__(0,sio[0]+1),begin=0xd0000060,end=0xd000007b)
ranges=[(v&~1,(v&~1)+ue.sizes[n]) for n,v in ue.symbols.items() if v&1 and ue.sizes.get(n)]
def pc(uc,a,s,u):assert any(lo<=a<a+s<=hi for lo,hi in ranges),hex(a)
unit.uc.hook_add(UC_HOOK_CODE,pc)
bare=[];endpoint_checks=0;accepts=Counter();sentinel=0x7ff80000000005e0
def run(name,a,b,fx,expected,metadata):
 for sn,state in states.items():
  unit.uc.mem_write(0x20000000,fx);unit.uc.mem_write(0xd0000060,state)
  got,_,cost=unit.call(name,a,b,count=True)
  assert got==expected,(name,metadata,hex(got),hex(expected))
  assert bytes(unit.uc.mem_read(0xd0000060,28))==state and bytes(unit.uc.mem_read(0x20000000,8))==fx
  if name in ['audit_product','audit_parent_product']:assert cost==(84 if name=='audit_product' else 91)
  bare.append(dict(function=name,SIO=sn,output=f'{got:016X}',instructions=cost,**metadata))
# Hit exact column3 rounding midpoints and neighbouring high32 residues,
# then add maximum upper columns to exercise post-rounding carry chains.
pairs=set()
for A in [1,3,65535,65537,(1<<30)-1,(1<<31)-1]:
 for off in [-2,-1,0,1,2]:
  B=(((1<<31)+off)*pow(A,-1,1<<32))&0xffffffff
  for bh in [0,1,(1<<22)-1]:pairs.add((A<<32,B+(bh<<32)))
av={0,1,(1<<63)-1};bv={0,1,(1<<54)-1}
for k in [15,16,31,32,47,48,62]:
 for off in [-1,0,1]:av.add((1<<k)+off)
for k in [15,16,31,32,47,48,53]:
 for off in [-1,0,1]:bv.add((1<<k)+off)
for a in av:
 for b in bv:pairs.add((a,b))
for a,b in sorted(pairs):
 omitted=(a&65535)*(b&65535)+(((a&65535)*((b>>16)&65535)+((a>>16)&65535)*(b&65535))<<16)
 exp=(a*b-omitted+(1<<63))>>64
 assert abs(F(exp)-F(a*b,S))<=product_error
 for fn in ['audit_product','audit_parent_product']:run(fn,a,b,b'\0'*8,exp,dict(a=f'{a:X}',b=f'{b:X}',kind='column3_round_and_upper_carry'))
for i in sorted(chosen_indices):
 for neg in [False,True]:
  for tail in [0,508,509,510,511,512,513,514,515,516,1023]:
   d=abs(tail-512);extra=d==3 and (delta32[i]>=-0x58000000 if tail>512 else delta32[i]<=0x58000000)
   ok=d>=4 or extra;accepts['normal_accept' if ok else 'normal_decline']+=1
   retained=(1<<52)+([0,1,(1<<52)-1][tail%3]);q=(retained<<10)|tail;k=[-1022,0,1023][tail%3]
   fx=struct.pack('<2I',(-i)&511 if neg else i,int(neg)<<31)
   expected=round_fraction(F(q)*F(2)**(k-62)) if ok else sentinel
   if ok:
    for err in [-F(delta32[i],1<<32)-remaining,-F(delta32[i],1<<32)+remaining]:
     assert round_fraction((F(q)-err)*F(2)**(k-62))==expected;endpoint_checks+=1
   run('audit_pack',q,k&0xffffffff,fx,expected,dict(index=i,negative=neg,tail=tail,extra=extra,accepted=ok))
for tail in [0,504,506,508,510,512,514,516,518,520,1022]:
 for k in [-1022,0,1023]:
  q=(((1<<53)-1)<<10)|tail;ok=abs(tail-512)>=6
  expected=round_fraction(F(q)*F(2)**(k-62)) if ok else sentinel
  if ok:
   for err in [-normalized,normalized]:assert round_fraction((F(q)-err)*F(2)**(k-62))==expected;endpoint_checks+=1
  accepts['normalized_accept' if ok else 'normalized_decline']+=1
  run('audit_pack',q,(k&0xffffffff)|(1<<32),b'\0'*8,expected,dict(index=0,normalized=True,tail=tail,accepted=ok))
tiny_inputs=set()
for ex in range(-54,-40):
 for neg in [False,True]:
  sh=-ex-int(neg);lower=(1<<52)>>sh;upper=((1<<53)-1)>>sh
  for retained in {lower,upper}:
   midpoint=(retained<<sh)+(1<<(sh-1))
   for off in [-4098,-4097,-4096,-1,0,1,4096,4097,4098]:
    sig=midpoint+off
    if 1<<52<=sig<1<<53:
     raw=((ex+1023)<<52)+(sig-(1<<52))+(int(neg)<<63)
     if 0x3c90000000000000<(raw&((1<<63)-1))<0x3d70000000000000:tiny_inputs.add(raw)
for raw in sorted(tiny_inputs):
 mag=raw&((1<<63)-1);ex=(mag>>52)-1023;sig=(mag&((1<<52)-1))|(1<<52);x=F(sig)*F(2)**(ex-52)
 if raw>>63:x=-x
 md=abs(x);lower=1+x+md*md*(F(1,2)-md/6);upper=1+x+md*md/(2*(1-md))
 sigshift=-ex-int(raw>>63);ret,suf=divmod(sig,1<<sigshift);half=1<<(sigshift-1)
 decline=0<suf-half<4097 if raw>>63 else 0<half-suf<4097
 if decline:expected=0x7ff8000000000000
 else:
  expected=round_fraction(lower);assert expected==round_fraction(upper);endpoint_checks+=2
 accepts['tiny_decline' if decline else 'tiny_accept']+=1
 run('audit_tiny',raw,0,b'\0'*8,expected,dict(x=f'{raw:016X}',accepted=not decline))
assert sio[0]==0 and all(accepts[x]>0 for x in ['normal_accept','normal_decline','normalized_accept','normalized_decline','tiny_accept','tiny_decline'])
(O/'bare-results.json').write_text(json.dumps(dict(status='PASS_FOCUSED_BARE_ARM',actual_ARM_calls=len(bare),product_pairs=len(pairs),tiny_inputs=len(tiny_inputs),function_counts=dict(Counter(r['function'] for r in bare)),rational_endpoint_checks=endpoint_checks,accepted_declined=dict(accepts),SIO_accesses=sio[0],observed_stack_bytes=SP-unit.stack_lowest,PC_limited_to_unit=True,no_firmware_or_ROM=True,rows=bare),indent=2)+'\n')
# Existing callers: own fresh execution of all four newly fixed pow cases,
# three retained route examples and both trigonometric controls. The author
# already ran all189; there is no need to repeat that unchanged corpus.
cr=read(P/'existing-callers.json');fixed={}
for r in cr['rows']:
 if r['SIO']=='READY' and r['correct']['Qfplib'] and r['instructions']['candidate']<=r['instructions']['Qfplib']<r['instructions']['parent']:fixed[(r['x'],r['y'])]=r
assert len(fixed)==4
call_jobs=list(fixed.values());seen=set()
for r in cr['rows']:
 key=(r['operation'],r['Qfplib_symbol'])
 if r['SIO']=='READY' and key not in seen:call_jobs.append(r);seen.add(key)
cm={'parent':Machine(BASE,True,bootrom=ROM),'candidate':Machine(BASE,True,bootrom=ROM),'Qfplib':Machine(REF,True)}
cm['candidate'].uc.mem_write(0x20038ee4,(P/'rounded-product.bin').read_bytes())
callrows=[]
for job in call_jobs:
 op=job['operation'];a=int(job['x'],16);b=int(job['y'],16) if job.get('y') else 0
 expected=oracle.reference(op,a,b) if op=='pow' else oracle.reference(op,a)
 for sn,state in states.items():
  oo={};cc={};co={}
  for label,m in cm.items():
   m.uc.mem_write(0xd0000060,state);got,_,cost=m.call(job['Qfplib_symbol'] if label=='Qfplib' else '_ZN12compact_math3'+op+('Edd' if op=='pow' else 'Ed'),a,b,count=True)
   oo[label]=f'{got:016X}';cc[label]=cost;co[label]=equal(got,expected)
   if label!='Qfplib':assert co[label]
   after=bytes(m.uc.mem_read(0xd0000060,28))
   if sn=='DIRTY':assert after==state
   else:assert not struct.unpack('<7I',after)[6]&2
  saved_row=next(r for r in cr['rows'] if r['operation']==op and r['x']==job['x'] and r['y']==job['y'] and r['SIO']==sn)
  assert oo==saved_row['outputs'] and cc==saved_row['instructions'] and co==saved_row['correct']
  callrows.append(dict(operation=op,x=job['x'],y=job['y'],SIO=sn,expected=f'{expected:016X}',outputs=oo,instructions=cc,correct=co,reference_symbol=job['Qfplib_symbol']))
(O/'caller-results.json').write_text(json.dumps(dict(status='PASS_FOCUSED_SHARED_PRODUCT_CALLERS',all4_new_pow_fixes_freshly_executed=True,actual_ARM_calls=3*len(callrows),actual_MPFR_calls=len(call_jobs),rows=callrows),indent=2)+'\n')
historical_rows=[r for r in public if int(r['x'],16) in historical]
fixed_exp={r['x'] for r in historical_rows if r['correct']['Qfplib'] and r['instructions']['candidate']<=r['instructions']['Qfplib']}
assert len(fixed_exp)==14
out=dict(status='PASS_INDEPENDENT_FOCUSED_EXP_PRODUCT_ARM_MPFR',MPFR=oracle.version,public_exp_unique=len(jobs),public_exp_ARM_calls=6*len(jobs),public_exp_MPFR_calls=len(jobs),author_baseline_rows_checked_for_exact_inheritance=97526,independent_source_model_product_checks=model_checks,historical_exp16_fixed=14,historical_exp16_remaining=2,all61_old_tight_new_losses_selected=True,retained_regressions=5800,retained_regression_histogram=dict(sorted(hist.items())),all_cost_types_freshly_replayed=sorted(costseen),expanded_raw_losses=count,public_trace={n:dict(v) for n,v in traces.items()},own_public_stack_subset={n:SP-m.stack_lowest for n,m in machines.items()},author_full_public_stack736_retained_not_reswept=True,bare_ARM_calls=len(bare),bare_product_pairs=len(pairs),bare_endpoint_checks=endpoint_checks,bare_function_counts=dict(Counter(r['function'] for r in bare)),bare_PC_isolated_no_ROM_or_firmware=True,bare_SIO_accesses=sio[0],bare_stack_bytes=SP-unit.stack_lowest,caller_ARM_calls=3*len(callrows),caller_MPFR_calls=len(call_jobs),all4_new_pow_fixes_freshly_replayed=True,total_own_ARM_calls=6*len(jobs)+len(bare)+3*len(callrows),total_own_MPFR_calls=len(jobs)+len(call_jobs),counts_are_instructions_not_physical_cycles=True,hardware=False,canonical=False,whole_math_GO=False)
(O/'focused-arm.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
