"""Independent exact log-threshold and rational degree-five exponential oracle."""
from fractions import Fraction as F
import math
ONE=0x3ff0000000000000;LOW=0x3c90000000000000;HIGH=0x3df0000000000000;G=1<<20;MASK=(1<<32)-1
def power(e):return F(1<<e) if e>=0 else F(1,1<<(-e))
def round_integer(f):
 q,r=divmod(f.numerator,f.denominator);return q+int(2*r>f.denominator or(2*r==f.denominator and q&1))
def taylor_bits(raw):
 field=(raw>>52)&2047;m=(raw&((1<<52)-1))|((1<<52) if field else 0);scale=field-1075 if field else -1074
 t=F(m)*power(scale);assert t<power(-30)
 n=raw>>63;x=-t if n else t;p=sum((x**k)/math.factorial(k) for k in range(6));err=t**6/(720*(1-t));h=power(-53 if n else -52)
 bits=[]
 for end in [p-err,p+err]:
  d=round_integer((1-end)/h if n else (end-1)/h);bits.append(ONE-d if n else ONE+d)
 assert bits[0]==bits[1],(f'{raw:016X}',bits)
 return bits[0]
def threshold(z,e,n):
 q=e+55+2*n;k,t=divmod(z*z,1<<q);b=(z*z*z)//(3*(1<<(52+n)))
 return k+int(t+b>=1<<q) if n else k-int(t<=b)
def source_threshold(z,e,n):
 q=e+55+2*n
 if z<65536:return (z*z)>>q
 square=z*z;lo=square&MASK;hi=square>>32;result=(lo>>q)|((hi<<(32-q))&MASK);tail=lo&((1<<q)-1)
 c_lo=lo*z;c_hi=hi*z+(c_lo>>32);scaled=(c_hi>>20)>>n;b=(scaled*43691)>>17
 return result+int(tail+b>=1<<q) if n else result-int(tail<=b)
def exact_model(raw,quadratic_only=False):
 n=raw>>63;e=((raw>>52)&2047)-1023;s=-e-n;m=(1<<52)|(raw&((1<<52)-1));r,rem=divmod(m,1<<s);half=1<<(s-1)
 up=rem>half if n else rem>=half;d=rem-half if n else half-rem
 if 1<=d<=G:
  z=2*r+1;t=(z*z)>>(e+55+2*n) if quadratic_only else threshold(z,e,n)
  up=d>t if n else d<=t
 return ONE+(-1 if n else 1)*(r+int(up))
def word_model(raw):
 n=raw>>63;e=((raw>>52)&2047)-1023;s=-e-n;hi=((raw>>32)&0xfffff)|0x100000;lo=raw&MASK
 if s==32:
  assert n==1
  r=hi;half=1<<31;up=lo>half;d=(lo-half)&MASK;near=1<=d<=G
 else:
  shift=s-32;tail=hi&((1<<shift)-1);half=1<<(shift-1);r=hi>>shift
  if n:up=tail>half or(tail==half and lo!=0);d=lo;near=tail==half and 1<=lo<=G
  else:up=tail>=half;d=(-lo)&MASK;near=tail+1==half and lo>(1<<32)-G-1
 if near:
  t=source_threshold(2*r+1,e,n);up=d>t if n else d<=t
 return ONE+(-1 if n else 1)*(r+int(up))
