"""Actual unchanged ARM reciprocal/ratio under the new one-sided bounds."""
from pathlib import Path
from fractions import Fraction as F
import hashlib,json,random,struct,sys,time
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path.insert(0,str(Q/'support'))
from native_eabi_m0_arm_self_test import Machine
ELF=P/'firmware/mk61s-picocalc-pico-h.elf';ROM=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
certificate=json.loads((W/'certificate.json').read_text());negative_bound=F(certificate['reciprocal_error'])
m=Machine(ELF,True,bootrom=ROM);rng=random.Random(0xA7A6B10D)
denominators=[]
for top in range(32768,65536):denominators.extend((top<<48,((top+1)<<48)-1))
denominators.extend((1<<63)|rng.getrandbits(63) for _ in range(4096))
states=(struct.pack('<7I',0,0,0,0,0,0,1),struct.pack('<7I',17,3,17,3,5,2,3))
digest=hashlib.sha256();maximum=F(0);minimum=F(0);calls=0;ratio_calls=0;start=time.monotonic()
for index,d in enumerate(denominators):
 for state_index,state in enumerate(states):
  m.uc.mem_write(0xd0000060,state);r=m.call('atan_fast_reciprocal',d)[0];calls+=1
  if state_index:assert bytes(m.uc.mem_read(0xd0000060,28))==state
  error=F(r*d-(1<<126),d);assert -negative_bound<error<3,(hex(d),hex(r),str(error))
  maximum=max(maximum,error);minimum=min(minimum,error);digest.update(struct.pack('<QQB',d,r,state_index))
  if index>=65536:
   n=rng.randrange(d//2+1);m.uc.mem_write(0xd0000060,state);h=m.call('atan_fast_ratio',n,d)[0];calls+=1;ratio_calls+=1
   if state_index:assert bytes(m.uc.mem_read(0xd0000060,28))==state
   error=F(h*d-(n<<64),d)
   assert -(F(13,2)+F(n,1<<62)*negative_bound)<error<F(13,2)+F(n,1<<62)*3,(hex(n),hex(d),str(error))
   digest.update(struct.pack('<QQQB',n,d,h,state_index))
 if (index+1)%16384==0:print('reciprocal progress',index+1,'/',len(denominators),flush=True)
report=dict(status='PASS_ACTUAL_ARM_ONE_SIDED_RECIPROCAL_AND_RATIO',normalized_denominators=len(denominators),seed_bucket_endpoints=65536,
            ARM_calls=calls,ratio_calls=ratio_calls,READY_and_DIRTY=True,DIRTY_preserved_every_call=True,PCS_SP_checked_every_call=True,
            observed_reciprocal_error_min=str(minimum),observed_reciprocal_error_max=str(maximum),strict_lower_error_bound=str(-negative_bound),strict_upper_error_bound=3,
            transcript_sha256=digest.hexdigest(),ELF_sha256=hashlib.sha256(ELF.read_bytes()).hexdigest(),code_unchanged=True,
            elapsed_seconds=time.monotonic()-start,scope='Finite actual ARM support for the analytic one-sided bound, not an exhaustive2^64 test.',hardware_accessed=False)
(W/'reciprocal-proof.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
