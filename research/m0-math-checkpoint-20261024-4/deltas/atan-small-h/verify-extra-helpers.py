"""Check ninth and inverted residue contracts against unbounded rationals."""
from pathlib import Path
from fractions import Fraction as F
import hashlib,json,random,struct,sys,time
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
sys.path.insert(0,str(ROOT/'.build/m0-float-fma-qualification-20261023/support'))
from native_eabi_m0_arm_self_test import Machine,SP
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
build=json.loads((W/'candidate-build.json').read_text());unit=json.loads((W/'ninth-unit-build.json').read_text())
assert sha(W/'candidate.elf')==build['ELF_sha256']
assert sha(W/'native_eabi_m0_atan_fast.inc')==build['source_include_sha256']==unit['public_source_sha256']
assert sha(W/'ninth-unit.elf')==unit['wrapper_ELF_sha256']
ninth=Machine(W/'ninth-unit.elf',True,stack_bytes=128)
inverse=Machine(W/'candidate.elf',True,stack_bytes=128)
states=(struct.pack('<7I',0,0,0,0,0,0,1),struct.pack('<7I',17,3,17,3,5,2,3))
def signed32(v):return v-(1<<32) if v>>31 else v
jobs={0,1,2,(1<<63)-1,(1<<62)-1,1<<62,(1<<62)+1}
for bit in range(63):
 for offset in (-1,0,1):
  if 0<=(1<<bit)+offset<(1<<63):jobs.add((1<<bit)+offset)
rng=random.Random(0xA7A90051)
for _ in range(1024):jobs.add(rng.randrange(1<<63))
calls=0;profiled=0;counts=[];digest=hashlib.sha256();maximum=F(0);start=time.monotonic()
for index,h in enumerate(sorted(jobs)):
 exact=F(h**9,9*(1<<560))
 for r5 in range(-4,10):
  exact_delta5=((abs(r5)+2)//5)*(-1 if r5<0 else 1)
  for si,state in enumerate(states):
   ninth.uc.mem_write(0xd0000060,state)
   enabled=index<48
   got,_,cost=ninth.call('check_ninth',h,r5&0xffffffff,count=enabled)
   delta=signed32(got&0xffffffff);remainder=signed32((got>>32)&0xffffffff)
   assert remainder==r5-5*exact_delta5 and -2<=remainder<=2
   value=delta-exact_delta5;assert 0<=value<=14
   error=abs(F(value)-exact);assert error<F(51,100),(hex(h),r5,str(error))
   assert bytes(ninth.uc.mem_read(0xd0000060,28))==state
   maximum=max(maximum,error);calls+=1
   if enabled:counts.append(cost);profiled+=1
   digest.update(struct.pack('<QiiiB',h,r5,delta,remainder,si))
pairs=set()
for bit in (58,59):
 for d in ((1<<bit)-64,1<<bit,(1<<bit)+64):
  if not (1<<58)<=d<(1<<60):continue
  for n in (0,64,(d//4)&~63,(d//2)&~63):pairs.add((n,d))
for _ in range(512):
 d=rng.randrange(1<<52,1<<54)<<6;n=rng.randrange(d//128+1)<<6;pairs.add((n,d))
inv_calls=0;accepted=0;declined=0;inv_digest=hashlib.sha256()
for n,d in sorted(pairs):
 H=F(n<<64,d);floor=H.numerator//H.denominator;factor=d>>6
 for offset in (-32,-1,0,1,32,33):
  h=floor+offset
  if h<0 or h>=(1<<63) or abs(F(h)-H)>=33:continue
  exact_residue=(n<<58)-h*factor
  assert abs(exact_residue)<1<<63
  expected=0<=-exact_residue+(factor>>1)<factor
  for si,state in enumerate(states):
   inverse.uc.mem_write(0xd0000060,state)
   got=inverse.call('atan_inverse_half',h,d)[0]&0xffffffff
   assert got==expected,(hex(n),hex(d),hex(h),got,expected)
   if got:assert abs(F(h)-H)<=F(1,2)
   assert bytes(inverse.uc.mem_read(0xd0000060,28))==state
   inv_calls+=1;accepted+=bool(got);declined+=not got
   inv_digest.update(struct.pack('<QQQB',n,d,h,got))
assert accepted>100 and declined>100
third_jobs={0,1,2,(1<<49)-1}
for bit in range(49):
 for offset in (-2,-1,0,1,2):
  if 0<=(1<<bit)+offset<(1<<49):third_jobs.add((1<<bit)+offset)
for hi in (0,1,2,3,0x7fff,0xffff,0x10000,0x1ffff):
 for lo in (0,1,2,0x7fffffff,0x80000000,0xfffffffd,0xfffffffe,0xffffffff):
  if (hi<<32)|lo < (1<<49):third_jobs.add((hi<<32)|lo)
for _ in range(2048):third_jobs.add(rng.randrange(1<<49))
third_calls=0;third_digest=hashlib.sha256()
for value in sorted(third_jobs):
 expected=(value+1)//3
 for si,state in enumerate(states):
  ninth.uc.mem_write(0xd0000060,state)
  got=ninth.call('check_third',value)[0]
  assert got==expected and -1<=value-3*got<=1
  assert bytes(ninth.uc.mem_read(0xd0000060,28))==state
  third_calls+=1;third_digest.update(struct.pack('<QQB',value,got,si))
report=dict(status='PASS_NINTH_AND_INVERTED_RESIDUE_UNBOUNDED_ARM_CONTRACTS',
            reduced_h_samples=len(jobs),ninth_ARM_calls=calls,ninth_profiled_calls=profiled,
            ninth_wrapper_instruction_range=[min(counts),max(counts)],ninth_max_error_Q70=float(maximum),
            ninth_exact_bound='51/100 Q70',ninth_reference='Unbounded Fraction(h**9,9*2**560), exact nearest division by5 and actual decoded ARM outputs.',
            inverse_pairs=len(pairs),inverse_ARM_calls=inv_calls,inverse_accepted=accepted,inverse_declined=declined,
            inverse_reference='Unbounded signed residual with shifted interval, and Fraction((n<<64),d)-h; every accepted case has error<=1/2.',
            exact_third_inputs=len(third_jobs),exact_third_ARM_calls=third_calls,exact_third_transcript_sha256=third_digest.hexdigest(),
            ninth_stack_bytes=SP-ninth.stack_lowest,inverse_stack_bytes=SP-inverse.stack_lowest,
            PCS_SP_bounded_writes_and_both_SIO_states_checked_every_call=True,no_firmware_or_ROM_mapped=True,
            ninth_transcript_sha256=digest.hexdigest(),inverse_transcript_sha256=inv_digest.hexdigest(),
            source_sha256=sha(W/'native_eabi_m0_atan_fast.inc'),candidate_ELF_sha256=sha(W/'candidate.elf'),
            ninth_wrapper_ELF_sha256=sha(W/'ninth-unit.elf'),hardware_accessed=False,goal_complete=False,
            elapsed_seconds=time.monotonic()-start)
(W/'extra-helper-proof.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
