"""Exact dyadic arithmetic measures actual root-boundary distances, no ARM/MPFR."""
from pathlib import Path
from collections import Counter
import json,struct
W=Path(__file__).resolve().parent
data=json.loads((W/'probe.json').read_bytes());rows=[];hist=Counter();model_counts=Counter()
def dyadic(raw):
 e=(raw>>52)&2047
 return (raw&((1<<52)-1))|(1<<52),int(e)-1023-52
def align(a,e,b,f):
 base=min(e,f)
 return a<<(e-base),b<<(f-base)
def model_square(a,e,r,p):
 t=(a*a)>>p;r=2*r+16;e*=2
 if t>>(p-1):e+=1
 else:t*=2;r*=2
 return t,e,r
def model_mul(a,e,r,b,f,s,p):
 t=(a*b)>>p;r=r+s+16;e+=f
 if t>>(p-1):e+=1
 else:t*=2;r*=2
 return t,e,r
def model_compare(a,e,r,b,f,s):
 if e-f>=2:return 1
 if e-f<=-2:return -1
 if e<f:a>>=1;r=(r>>1)+1
 elif e>f:b>>=1;s=(s>>1)+1
 return 1 if a-b>r+s else -1 if b-a>r+s else 0
for row in data['rows']:
 if row['SIO']!='READY':continue
 x,y=int(row['x'],16),int(row['y'],16)&0x7fffffffffffffff
 for call in row['boundary_calls']:
  denominator=call['denominator'];cell=int(call['cell'],16)
  ym,ye=dyadic(y);n,tail=divmod(ym*denominator,1<<(-ye)) if ye<0 else ((ym*denominator)<<ye,0)
  assert tail==0 and n<=32
  xm,xe=dyadic(x);cm,ce=dyadic(cell);cm=cm*2+1;ce-=1
  power,pe=xm**n,xe*n;mid,me=cm**denominator,ce*denominator
  ph,pl,exponent,radius=struct.unpack('<QQiI',bytes.fromhex(call['power']));center=(ph<<64)|pl
  a,b=align(center-radius,exponent-127,power,pe);assert a<=b
  a,b=align(center+radius,exponent-127,power,pe);assert a>=b
  if call['inverse']:a,b=align(power*mid,pe+me,1,0)
  else:a,b=align(power,pe,mid,me)
  diff=abs(a-b);gap=max(a.bit_length(),b.bit_length())-diff.bit_length() if diff else 'exact_tie'
  hist[str(gap)]+=1
  decisions={}
  for p in [80,96,112,128]:
   mid_center=cm<<(p-54);mid_exp=(cell>>52)-1023;mid_radius=0
   d=denominator
   while d>1:mid_center,mid_exp,mid_radius=model_square(mid_center,mid_exp,mid_radius,p);d>>=1
   shift=128-p
   value=center>>shift
   error=((radius+(1<<shift)-1)>>shift)+1 if shift else radius
   if call['inverse']:
    q,qe,qr=model_mul(mid_center,mid_exp,mid_radius,value,exponent,error,p)
    decision=-model_compare(q,qe,qr,1<<(p-1),0,0)
   else:decision=model_compare(value,exponent,error,mid_center,mid_exp,mid_radius)
   exact_side=(a>b)-(a<b)
   if call['inverse']:exact_side=-exact_side
   assert not decision or decision==exact_side
   decisions[str(p)]=decision
   model_counts[p]+=bool(decision)
  rows.append(dict(x=row['x'],y=row['y'],cell=call['cell'],denominator=denominator,numerator=n,
                   inverse=call['inverse'],relative_gap_bits=gap,ideal_truncation_model_decisions=decisions))
out=dict(status='EXACT_DYADIC_GAP_AND_PARENT_POWER_ENCLOSURE_AUDIT',boundary_calls_ready=len(rows),
 actual_ARM_or_MPFR_calls=0,relative_gap_bits_histogram=dict(hist),
 ideal_exact_truncation_filter_decisions=dict(model_counts),
 model_radii_use_same_conservative16_not_a_new_ARM_implementation=True,
 all_captured_actual_P128_power_enclosures_verified_against_exact_dyadic_powers=True,
 rows=rows,hardware_accessed=False)
(W/'required-precision.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items()if k!='rows'},indent=2))
