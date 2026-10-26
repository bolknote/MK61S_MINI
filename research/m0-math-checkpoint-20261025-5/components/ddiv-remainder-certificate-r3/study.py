"""Exact integer certificate, including both modular sign discontinuities."""
from pathlib import Path
from collections import Counter
import hashlib,itertools,json,random
W=Path(__file__).resolve().parent;MASK=(1<<32)-1;LIMIT=(1<<17)-1
def sign(v):return -1 if v&(1<<31)else 1 if v else 0
def check(base,u,v):
 product=u*v;high=product>>32;borrow=bool(product&MASK);d=(u>>16)*(v>>16)
 omitted=high-d+borrow;assert 0<=omitted<=LIMIT
 estimate=(base-d)&MASK;exact=(base-high-borrow)&MASK
 folded=(estimate>>17)<<18&MASK
 uncertain=folded==0;carry=(estimate>>31)&1
 assert uncertain==(((estimate&0x7fffffff)>>17)==0)
 if not uncertain:assert sign(estimate)==sign(exact)!=0 and carry==((exact>>31)&1)
 return uncertain,omitted
limbs=[0,1,2,32767,32768,65534,65535]
estimates=[0,1,131070,131071,131072,131073,(1<<31)-2,(1<<31)-1,1<<31,(1<<31)+1,(1<<31)+131070,(1<<31)+131071,(1<<31)+131072,(1<<31)+131073,MASK-1,MASK]
counts=Counter();maximum=0;edge_count=0
for uh,ul,vh,vl in itertools.product(limbs,repeat=4):
 u=(uh<<16)|ul;v=(vh<<16)|vl;d=uh*vh
 for estimate in estimates:
  uncertain,omitted=check((estimate+d)&MASK,u,v);counts['fallback'if uncertain else'certified']+=1;maximum=max(maximum,omitted);edge_count+=1
rng=random.Random(0x614CE271)
for _ in range(300000):
 uncertain,omitted=check(rng.getrandbits(32),rng.getrandbits(32),rng.getrandbits(32));counts['fallback'if uncertain else'certified']+=1;maximum=max(maximum,omitted)
out=dict(status='PASS_EXACT_INTEGER_CERTIFICATE_MODEL_AND_BOUNDARIES',analytic_bound=LIMIT,
 proof='hi32(u*v)-uh*vh<=uh+vh<=131070; add borrow<=1. The selected modular interval excludes both signed discontinuities.',
 structured_cases=edge_count,random_cases=300000,classification=dict(counts),observed_max_omitted=maximum,
 uncertain_band_includes_zero_and_INT32_MIN=True,all_certified_signs_identical=True,actual_ARM_or_MPFR_calls=0,hardware_accessed=False)
(W/'study.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
