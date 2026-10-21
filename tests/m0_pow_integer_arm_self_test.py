#!/usr/bin/env python3
"""Verify the checked integer-power fast path without a floating-point oracle."""
from pathlib import Path
from fractions import Fraction as F
import argparse,hashlib,json,random,struct,sys
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'tests'))
from native_eabi_m0_arm_self_test import Machine,bits
parser=argparse.ArgumentParser(description='Check positive integer pow3..8 on ARM against exact integer RNE results.')
parser.add_argument('--elf',type=Path,required=True)
parser.add_argument('--source-root',type=Path,default=root)
parser.add_argument('--samples',type=int,default=10000)
parser.add_argument('--json',type=Path,required=True)
args=parser.parse_args();assert args.samples>=0
elf=args.elf;m=Machine(elf,True)
S=1<<62;mask=(1<<52)-1;infinity=0x7ff0000000000000;sentinel=infinity|(1<<51)
# Enumerate both normalization outcomes at every multiply. These error
# states overapproximate all correlated mantissas and all normal bases.
def mul_errors(a,b):
 out=set()
 for x in a:
  for y in b:
   assert F(x*y,S)<F(1,2)
   e=2*x+2*y+7;out.update([e,(e>>1)+1])
 return out
square=mul_errors({0},{0});fourth=mul_errors(square,square)
errors={3:mul_errors(square,{0}),4:fourth,5:mul_errors(fourth,{0}),6:mul_errors(fourth,square),8:mul_errors(fourth,fourth)}
errors[7]=mul_errors(errors[6],{0});assert max(max(s) for s in errors.values())<256
# Unwrapped normalized operands multiply into[2^62,2^64). With the
# proven6.5-unit product bound, any unsigned wrap is below2^62 and rejected.
assert F(13,2)<S and max(max(s) for s in errors.values())<512

def nearest_shift(n,shift):
 if shift<=0:return n<<(-shift)
 q=n>>shift;r=n-(q<<shift);half=1<<(shift-1)
 return q+(r>half or (r==half and q&1))
def exact_power(x,n):
 magnitude=x&((1<<63)-1);sgn=(x&(1<<63)) if n&1 else 0
 if not magnitude:return sgn
 if magnitude==infinity:return infinity|sgn
 assert magnitude<infinity
 e=(magnitude>>52)-1023;sig=(magnitude&mask)|(1<<52)
 if magnitude<(1<<52):e=-1022;sig=magnitude
 integer=pow(sig,n);scale=(e-52)*n;exponent=integer.bit_length()-1+scale
 if exponent<-1022:return nearest_shift(integer,-scale-1074)|sgn
 shift=integer.bit_length()-53;q=nearest_shift(integer,shift)
 if q==1<<53:q>>=1;exponent+=1
 if exponent>1023:return infinity|sgn
 assert exponent>=-1022 and 1<<52<=q<1<<53
 return ((exponent+1023)<<52)|(q&mask)|sgn

rng=random.Random(0x360308);pairs=[]
for n in range(3,9):
 values={1,2,3,(1<<52)-1,1<<52,(1<<52)+1,0x3ff0000000000000,0x7fefffffffffffff}
 for e in range(-1022,1024):values.add((e+1023)<<52)
 for e in [-1075//n,-1074//n,-1022//n,0,1023//n,1024//n]:
  if not -1022<=e<=1023:continue
  center=(e+1023)<<52
  for d in range(-2048,2049):
   value=center+d
   if 0<value<infinity:values.add(value)
 for _ in range(args.samples):
  values.add((rng.randrange(1,2047)<<52)|rng.getrandbits(52))
  e=rng.randrange(max(-1022,-1076//n),min(1024,1025//n)+1)
  if e<=1023:values.add(((e+1023)<<52)|rng.getrandbits(52))
 for x in sorted(values):pairs.append((x,n))
digest=hashlib.sha256();accepted=ambiguous=normal_accepted=0;maxerr=0;sample=[]
for i,(x,n) in enumerate(pairs):
 y=bits(float(n));expected=exact_power(x,n)
 fast=m.call('pow_small_integer',x,y>>32)[0]
 if fast==sentinel:ambiguous+=1
 else:
  accepted+=1;normal_accepted+=0<fast<infinity
  assert fast==expected,('fast',hex(x),n,hex(fast),hex(expected))
 actual=m.call('_ZN12compact_math3powEdd',x,y)[0]
 assert actual==expected,('public positive',hex(x),n,hex(actual),hex(expected))
 if i%16==0:
  negative=x|(1<<63);want=exact_power(negative,n);got=m.call('_ZN12compact_math3powEdd',negative,y)[0]
  assert got==want,('negative parity',hex(negative),n,hex(got),hex(want))
 digest.update(struct.pack('<4Q',x,n,expected,actual))
 if (i+1)%20000==0:print('PASS',i+1,'/',len(pairs),'fast accepted',accepted,flush=True)
for x,n in [(bits(1.5),3),(bits(1.3),7),(bits(100.5),8),(bits(2.),5)]:
 got,_,count=m.call('_ZN12compact_math3powEdd',x,bits(float(n)),count=True);sample.append(dict(x=hex(x),n=n,instructions=count))
report=dict(status='PASS',cases=len(pairs),fast_accepted=accepted,finite_nonzero_fast_accepted=normal_accepted,fast_rejected=ambiguous,wrong_rounding=0,elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),source_sha256=hashlib.sha256((args.source_root/'code/native_eabi_m0_pow_integer.inc').read_bytes()).hexdigest(),exact_oracle='Full integer significand**n and exact binary scale; one final integer ties-to-even rounding to binary64 including gradual underflow and overflow. No libm or MPFR approximation.',maximum_q62_error_by_n={n:max(e) for n,e in sorted(errors.items())},normalization_error_states_by_n={n:sorted(e) for n,e in sorted(errors.items())},arm_abi='Every call checks R4-R11, SP and bounded stack writes.',samples=sample,digest_sha256=digest.hexdigest(),scope='Positive integer3..8 shortcut on normal finite magnitudes, ambiguous cells use existing pow; independent integer finite corpus plus rational all-input enclosure. Original universal pow fallback limitation remains.')
args.json.parent.mkdir(parents=True,exist_ok=True)
args.json.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)
