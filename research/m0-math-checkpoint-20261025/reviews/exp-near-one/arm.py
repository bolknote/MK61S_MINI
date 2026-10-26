"""Bounded CPU-only actual Thumb/math checks, independently selected inputs.

No physical devices, transport APIs, firmware boot, Git or network. The public
functions use the already accepted CPU harness and captured ROM instructions;
bare integer and pack units have no external calls or memory models.
Run one named part at a time; completed evidence is never overwritten.
"""
import ctypes as C
import hashlib,json,random,struct,sys
from collections import Counter
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-exp-near-one-20261024'
SUP=R/'.build/m0-float-fma-qualification-20261023/support'
sys.path[:0]=[str(SUP),str(R/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle,_Number
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ
from unicorn.arm_const import UC_ARM_REG_SP,UC_ARM_REG_XPSR,UC_ARM_REG_R12
MASK=(1<<64)-1;SIGN=1<<63
def ref(p):p=Path(p);data=p.read_bytes();return dict(path=str(p),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
def save(n,d):
 with (O/n).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
 print(json.dumps(ref(O/n)),flush=True)
def retained(a,b,k):return sum(((a>>(16*i))&65535)*((b>>(16*j))&65535)<<(16*(i+j))for i in range(3)for j in range(4)if i+j>=k)
def product64(a,b):return (retained(a,b,3)+(1<<63))>>64
def product48(a,b):return retained(a,b,2)>>48
def small_model(a):
 negative=a>>63;e=((a>>52)&2047)-1023;m=(a&((1<<52)-1))|(1<<52);x64=m>>(-e-12)
 coefficient=11728124029611
 if e==-12:
  t=product64(2345624805922,x64);coefficient=coefficient-t if negative else coefficient+t
 t=product64(coefficient,x64);coefficient=46912496118443-t if negative else 46912496118443+t
 tail=product64(coefficient,x64);square=((m>>5)**2)>>(26-e);ct=product48(tail,square)
 correction=(square>>1)-ct if negative else (square>>1)+ct;fifth_error=0
 if e<=-13:
  if e>-15:
   c=m>>47;s=-4*e-48;fifth=(c**5>>(s+8))//15
   correction=correction-fifth if negative else correction+fifth;fifth_error=(21174>>s)+2
  else:fifth_error=69 if e==-15 else 5 if e==-16 else 1
 extra=(1<<(e+22))if e>=-22 else 0;error=4*(square>>48)+32+extra+fifth_error
 shift=16-e-negative;U=1<<shift;N=(m<<16)+(-correction if negative else correction)
 unsafe=(N+U//2+error)%U<=2*error;q=(N+U//2)//U
 return dict(correction=correction,error=error,unsafe=unsafe,packed=(0x3ff0000000000000-q if negative else 0x3ff0000000000000+q),e=e)

def bare():
 path=W/'small-products-unit.elf';im=ElfImage(path);m=Machine(path,True)
 names=['mk61_m0_exp_small_product64','mk61_m0_exp_small_product48','mk61_m0_exp_small_square48']
 state=dict(entry=0,end=0,flags=0);costs={n:Counter()for n in names};lowest=SP;reads=0
 def audit(uc,pc,size,_):
  nonlocal lowest
  assert state['entry']<=pc<state['end']
  if pc==state['entry']:
   uc.reg_write(UC_ARM_REG_XPSR,0x01000000|(state['flags']<<28));uc.reg_write(UC_ARM_REG_R12,0xBAD06100|state['flags'])
  lowest=min(lowest,uc.reg_read(UC_ARM_REG_SP))
 def read(uc,access,address,size,value,_):
  nonlocal reads
  assert SP-36<=address and address+size<=SP
  reads+=1
 m.uc.hook_add(UC_HOOK_CODE,audit);m.uc.hook_add(UC_HOOK_MEM_READ,read)
 calls=0
 def call(name,a,b):
  nonlocal calls
  state.update(entry=im.symbols[name]&~1,end=(im.symbols[name]&~1)+im.sizes[name])
  got,_,cost=m.call(name,a,b,count=True);calls+=1;costs[name][cost]+=1;return got
 pairs={(0,0),((1<<48)-1,(1<<58)-1),(1,(1<<58)-1),((1<<48)-1,1),((1<<32)-1,(1<<48)-1),((1<<32)+1,(1<<48)+1)}
 rng=random.Random(0x251061)
 pairs.update((rng.getrandbits(48),rng.getrandbits(58))for _ in range(24))
 for a,b in sorted(pairs):
  q=call(names[0],a,b);assert q==product64(a,b)and abs((q<<64)-a*b)<(7<<63)+(1<<49)
  q=call(names[1],a,b);assert q==product48(a,b)and 0<=a*b-(q<<48)<3*(1<<48)
 for shift in range(38,59):
  for a in [0,(1<<47)+65535,(1<<48)-1]:assert call(names[2],a,shift)==a*a>>shift
 for flags in range(16):
  state['flags']=flags
  for a,b in [(0,0),((1<<48)-1,(1<<58)-1),((1<<32)+65535,(1<<57)+65535)]:
   assert call(names[0],a,b)==product64(a,b)
   assert call(names[1],a,b)==product48(a,b)
   shift=38+flags%21;assert call(names[2],a,shift)==a*a>>shift
 assert SP-lowest==36 and all(len(c)==1 for c in costs.values())and not m.rom_models
 save('bare-arm.json',dict(status='PASS_BOUNDED_ACTUAL_INTEGER_ARM',qualified_calls=calls,product_pairs=len(pairs),
  square_pairs=63,all16NZCV_on3_adversarial_triples=True,costs={n:dict(c)for n,c in costs.items()},stack_frame=SP-lowest,
  bounded_stack_reads=reads,Machine_checks_R4_R11_SP_and_bounded_stack_writes=True,
  literal_public_binding=ref(O/'binding.json'),unit=ref(path),no_external_calls_models_or_SIO=True,
  device_IO=0,MPFR_inputs=0))

def pack():
 m=Machine(W/'pack-unit.elf',True);rows=[];accepted=rejected=0
 for e in range(-32,-11):
  for sign in [0,1]:
   U=1<<(16-e-sign);error=5148
   for significand in [1<<52,(1<<53)-1]:
    a=(sign<<63)|((e+1023)<<52)|(significand-(1<<52))
    for delta in [-error-1,0,error+1]:
     target=U//2+delta
     correction=((significand<<16)-target if sign else target-(significand<<16))%(U)
     correction|=((1<<57)//U)*U
     N=(significand<<16)+(-correction if sign else correction)
     unsafe=(N+U//2+error)%U<=2*error
     got,_,cost=m.call('audit_exp_small_pack',a,correction,c=error,count=True)
     if unsafe:assert got==MASK;rejected+=1
     else:
      q=(N+U//2)//U;expected=0x3ff0000000000000-q if sign else 0x3ff0000000000000+q
      assert got==expected;accepted+=1
      assert (N-error+U//2)//U==q==(N+error+U//2)//U
     rows.append(dict(e=e,sign=sign,m=f'{significand:014X}',correction=correction,error=error,unsafe=unsafe,cost=cost))
 assert accepted and rejected and not m.rom_models
 save('pack-arm.json',dict(status='PASS_BOUNDED_LITERAL_PACK_ACTUAL_ARM',qualified_calls=len(rows),accepted=accepted,rejected=rejected,
  all21binades_bothsigns_3packingbranches=True,unsafe_admissions=0,rows=rows,stack_bytes_observed=SP-m.stack_lowest,
  independent_unbounded_integer_oracle=True,literal_binding=ref(O/'literal-unit-binding.json'),device_IO=0,MPFR_inputs=0))

def correction_enclosure(oracle,x,model):
 lib=oracle.lib;pointer=C.POINTER(_Number)
 for name,args in [('mpfr_set_ui',[pointer,C.c_ulong,C.c_int]),('mpfr_sub_ui',[pointer,pointer,C.c_ulong,C.c_int]),
                   ('mpfr_sub',[pointer,pointer,pointer,C.c_int]),('mpfr_mul_2si',[pointer,pointer,C.c_long,C.c_int]),('mpfr_cmp',[pointer,pointer])]:
  fn=getattr(lib,name);fn.argtypes=args;fn.restype=C.c_int
 values=[_Number()for _ in range(5)]
 for v in values:lib.mpfr_init2(C.byref(v),256)
 number,lower,upper,left,right=values
 try:
  lib.mpfr_set_d(C.byref(number),struct.unpack('<d',struct.pack('<Q',x))[0],0)
  for output,direction in [(lower,3),(upper,2)]:
   lib.mpfr_exp(C.byref(output),C.byref(number),direction)
   lib.mpfr_sub_ui(C.byref(output),C.byref(output),1,direction)
   lib.mpfr_sub(C.byref(output),C.byref(output),C.byref(number),direction)
   lib.mpfr_mul_2si(C.byref(output),C.byref(output),68-model['e'],direction)
  lib.mpfr_set_ui(C.byref(left),model['correction']-model['error'],0)
  lib.mpfr_set_ui(C.byref(right),model['correction']+model['error'],0)
  assert lib.mpfr_cmp(C.byref(lower),C.byref(left))>0 and lib.mpfr_cmp(C.byref(upper),C.byref(right))<0
 finally:
  for v in values:lib.mpfr_clear(C.byref(v))

def public():
 base=R/'.build/m0-asin-scaled-bound-v164-20261023/firmware/mk61s-picocalc-pico-h.elf';rom=R/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
 machines=[]
 for label,elf in [('candidate',W/'candidate.elf'),('parent',R/'.build/m0-exp-directed-product-20261024/candidate.elf')]:
  m=Machine(base,True,bootrom=rom);im=ElfImage(elf);im.load(m.uc);m.elf.symbols['review_exp']=im.symbols['mk61_m0_exp'];machines.append((label,m,im))
 q=Machine(R/'.build/m0-v138-execution-20261023/reference/reference.elf',True)
 assert all(not m.rom_models for _,m,_ in machines)and not q.rom_models
 event=dict(small=0,refine=0)
 c=machines[0][1];im=machines[0][2]
 def tick(uc,pc,size,_):
  if pc==im.symbols['exp_small_rne']&~1:event['small']+=1
  if pc==im.symbols['exp_refine']&~1:event['refine']+=1
 c.uc.hook_add(UC_HOOK_CODE,tick)
 jobs={}
 def add(x,why):jobs.setdefault(x,why)
 for e in range(-32,-11):
  for sign in [0,1]:
   for frac in [0,(1<<52)-1,0x123456789abcd]:add((sign<<63)|((e+1023)<<52)|frac,'every_small_binade')
 for e in [-33,-32,-12,-11]:
  for sign in [0,1]:
   for delta in [-1,0,1]:add((sign<<63)+((e+1023)<<52)+delta,'dispatch_neighbors')
 for row in json.loads((W/'original-exp16.json').read_text())['rows']:add(int(row['x'],16),'original16')
 for x in json.loads((W/'result.json').read_text())['public_examples']:add(int(x,16),'recorded_example')
 for row in json.loads((W/'remaining-parent-audit.json').read_text())['rows'][:8]:add(int(row['x'],16),'retained_refinement_loss')
 for x in [0,SIGN,1,SIGN|1,0x0010000000000000,0x8010000000000000,0x7ff0000000000000,0xfff0000000000000,
           0x7ff8000012345678,0xfff8000012345678,0x7ff0000012345678,0xfff0000012345678]:add(x,'IEEE_control')
 states=dict(READY=struct.pack('<7I',0,0,0,0,0,0,1),DIRTY=struct.pack('<7I',17,3,17,3,5,2,3))
 oracle=Oracle();rows=[];calls=0;shortcuts=0;mpfr_inputs=0;enclosures=0;fast=declined=0
 for index,(x,group)in enumerate(jobs.items()):
  expected=oracle.reference('exp',x);mag=x&~SIGN;snan=mag>0x7ff0000000000000 and not x&(1<<51)
  if snan:shortcuts+=1
  else:mpfr_inputs+=1
  e=((x>>52)&2047)-1023;model=small_model(x)if -32<=e<=-12 else None
  if model:
   correction_enclosure(oracle,x,model);enclosures+=1
   if model['unsafe']:declined+=1
   else:fast+=1
  for state_name,state in states.items():
   outputs={};costs={};event.update(small=0,refine=0)
   for label,m,_ in machines:
    m.uc.mem_write(0xd0000060,state);got,_,cost=m.call('review_exp',x,count=True);calls+=1
    assert got==expected or ((got&~SIGN)>0x7ff0000000000000 and (expected&~SIGN)>0x7ff0000000000000),(hex(x),label,hex(got),hex(expected))
    after=bytes(m.uc.mem_read(0xd0000060,28))
    assert after==state if state_name=='DIRTY' else not struct.unpack('<7I',after)[6]&2
    outputs[label]=f'{got:016X}';costs[label]=cost
    if label=='candidate'and model:
     assert event['small']==1 and bool(event['refine'])==model['unsafe']
     if not model['unsafe']:assert got==model['packed']
   q.uc.mem_write(0xd0000060,state);qgot,_,qcost=q.call('qfp_dexp',x,count=True);calls+=1
   assert bytes(q.uc.mem_read(0xd0000060,28))==state
   outputs['Qfplib']=f'{qgot:016X}';costs['Qfplib']=qcost
   qcorrect=qgot==expected or ((qgot&~SIGN)>0x7ff0000000000000 and (expected&~SIGN)>0x7ff0000000000000)
   if group=='original16':assert qcorrect and costs['candidate']<qcost
   assert outputs['candidate']==outputs['parent']
   rows.append(dict(x=f'{x:016X}',group=group,SIO=state_name,expected=f'{expected:016X}',outputs=outputs,costs=costs,Qfplib_correct=qcorrect,
                    small_model=model,candidate_events=dict(event)))
  if index%64==0:print('bounded-public',index,'/',len(jobs),flush=True)
 assert fast and declined
 save('public-arm-mpfr.json',dict(status='PASS_BOUNDED_PUBLIC_ACTUAL_ARM_AND_DIRECTED_MPFR',unique_inputs=len(jobs),qualified_ARM_calls=calls,
  directed_MPFR_rounded_inputs=mpfr_inputs,sNaN_shortcuts=shortcuts,MPFR_version=oracle.version,
  additional_256bit_directed_correction_enclosures=enclosures,model_fast_inputs=fast,model_declined_inputs=declined,
  original16_both_states_strict=True,DIRTY28bytes_and_READY_checked=True,
  observed_stack_bytes={label:SP-m.stack_lowest for label,m,_ in machines},reference_stack_observed=SP-q.stack_lowest,
  actual_ROM_initializer_calls_excluded={label:m.rom_initializers for label,m,_ in machines},
  rows=rows,no_other_operation_qualification=True,no_physical_cycle_bound=True,device_IO=0,
  source_harness=ref(SUP/'native_eabi_m0_arm_self_test.py'),source_oracle=ref(SUP/'m0_mpfr_oracle.py')))

if __name__=='__main__':
 assert len(sys.argv)==2 and sys.argv[1]in ['bare','pack','public']
 globals()[sys.argv[1]]()
