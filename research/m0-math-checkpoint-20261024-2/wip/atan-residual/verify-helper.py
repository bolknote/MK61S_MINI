"""Check actual ARM signed-residual repair against unbounded quotients."""
from pathlib import Path
from fractions import Fraction as F
import hashlib,json,random,struct,sys,time
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path.insert(0,str(Q/'support'))
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
ELF=P/'firmware/mk61s-picocalc-pico-h.elf';ROM=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
image=ElfImage(W/'candidate.elf');machine=Machine(ELF,True,bootrom=ROM);image.load(machine.uc)
names=[n for n in image.symbols if n.startswith('atan_fast_tail_repair')];assert len(names)==1,names
machine.elf.symbols['repair_helper']=image.symbols[names[0]]
pairs=set()
for bit in range(59,65):
 for d in ((1<<bit)-1,1<<bit,(1<<bit)+1):
  if not (1<<59)<=d<(1<<64):continue
  for n in (0,1,3,d//4,d//2-1,d//2):pairs.add((n,d))
rng=random.Random(0xA7A6DE17)
for _ in range(1024):
 d=rng.randrange(1<<59,1<<64);pairs.add((rng.randrange(d//2+1),d))
states=(struct.pack('<7I',0,0,0,0,0,0,1),struct.pack('<7I',17,3,17,3,5,2,3))
bound=F(1)+F(34,1<<20);digest=hashlib.sha256();cases=0;minimum=F(0);maximum=F(0);maxdelta=0;examples=[];quotients=set();start=time.monotonic()
for pair_index,(n,d) in enumerate(sorted(pairs)):
 H=F(n<<64,d);floor=H.numerator//H.denominator
 offsets=range(-32,34) if pair_index<128 else (-32,-31,-1,0,1,31,32,33)
 for offset in offsets:
  h=floor+offset
  if h<0 or h>=(1<<63) or abs(F(h)-H)>=33:continue
  for si,state in enumerate(states):
   machine.uc.mem_write(0xd0000060,state)
   got=machine.call('repair_helper',n,d,c=h)[0]&0xffffffff
   delta=got-(1<<32) if got>>31 else got
   error=F(delta)-(H-h)
   assert abs(error)<bound,(hex(n),hex(d),h,delta,str(error))
   assert abs(delta)<=33
   residual=(n<<64)-h*d
   exact_truncated=(abs(residual)>>38)//(d>>38)
   expected=-exact_truncated if residual<0 else exact_truncated
   assert delta==expected,(hex(n),hex(d),h,delta,expected)
   after=bytes(machine.uc.mem_read(0xd0000060,28))
   assert after==state,('The bounded divider must not access SIO',si)
   cases+=1;minimum=min(minimum,error);maximum=max(maximum,error);maxdelta=max(maxdelta,abs(delta))
   quotients.add(abs(delta));digest.update(struct.pack('<QQQiB',n,d,h,delta,si))
   if len(examples)<24:examples.append(dict(n=f'{n:016X}',d=f'{d:016X}',h=f'{h:016X}',delta=delta,error=str(error),SIO='DIRTY' if si else 'READY'))
assert quotients==set(range(34)),quotients
report=dict(status='PASS_ACTUAL_ARM_RESIDUAL_HELPER_EXACT_RATIONAL',numerator_denominator_pairs=len(pairs),ARM_calls=cases,all_bounded_quotients_0_to_33_covered=True,
            independent_reference='Exact unbounded Fraction((n<<64),d)-h plus Python exact truncated division; validates signed128-bit carries and the Thumb binary divider.',
            strict_error_bound=str(bound),observed_error_min=str(minimum),observed_error_max=str(maximum),maximum_absolute_delta=maxdelta,
            digest_sha256=digest.hexdigest(),candidate_ELF_sha256=hashlib.sha256((W/'candidate.elf').read_bytes()).hexdigest(),source_sha256=hashlib.sha256((W/'native_eabi_m0_atan_fast.inc').read_bytes()).hexdigest(),
            observed_stack_bytes=SP-machine.stack_lowest,PCS_SP_and_bounded_writes_checked_every_call=True,READY_and_DIRTY_preserved_every_call=True,helper_no_SIO_access=True,
            examples=examples,elapsed_seconds=time.monotonic()-start,hardware_accessed=False,canonical_or_frozen_changed=False,goal_complete=False)
(W/'helper-proof.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='examples'},indent=2))
