"""Independent full-significand midpoint model and rational Taylor RNE oracle."""
from fractions import Fraction as F
ONE=0x3ff0000000000000;LOW=0x3c90000000000000;HIGH=0x3d90000000000000
MASK=(1<<32)-1
def power(e):return F(1<<e) if e>=0 else F(1,1<<(-e))
def decode(raw):
 field=(raw>>52)&2047;frac=raw&((1<<52)-1)
 return frac|((1<<52) if field else 0),field-1075 if field else -1074
def rounded_integer(f):
 q,r=divmod(f.numerator,f.denominator)
 return q+int(2*r>f.denominator or(2*r==f.denominator and q&1))
def taylor_bits(raw):
 """A cubic rational interval, independent of the midpoint-floor formula."""
 m,e=decode(raw);t=F(m)*power(e);assert t<power(-36)
 negative=bool(raw>>63);x=-t if negative else t
 p=1+x+x*x/2+x*x*x/6
 tail=t**4/(24*(1-t))
 h=power(-53 if negative else -52)
 ends=[]
 for endpoint in (p-tail,p+tail):
  displacement=(1-endpoint)/h if negative else (endpoint-1)/h
  rounded=rounded_integer(displacement)
  ends.append(ONE-rounded if negative else ONE+rounded)
 assert ends[0]==ends[1],(f'{raw:016X}',ends)
 return ends[0]
def midpoint_model(raw):
 mag=raw&((1<<63)-1);assert LOW<mag<HIGH
 neg=int(raw>>63);e=((raw>>52)&2047)-1023;m=(1<<52)|(raw&((1<<52)-1));s=-e-neg
 retained,rem=divmod(m,1<<s);half=1<<(s-1)
 odd=2*retained+1;quadratic=(odd*odd)>>(e+55+2*neg)
 if neg:
  d=rem-half;up=rem>half
  if 1<=d<=16384:up=d>quadratic
 else:
  d=half-rem;up=rem>=half
  if 1<=d<=16384:up=d<=quadratic
 return ONE+(-1 if neg else 1)*(retained+int(up))
def word_model(raw):
 neg=int(raw>>63);e=((raw>>52)&2047)-1023;shift=-e-neg-32
 hi=((raw>>32)&0xfffff)|0x100000;lo=raw&MASK;tail=hi&((1<<shift)-1);half=1<<(shift-1);r=hi>>shift
 if neg:
  up=tail>half or(tail==half and lo!=0)
  if tail==half and 1<=lo<=16384:up=lo>((2*r+1)**2>>(e+57))
 else:
  up=tail>=half
  if tail+1==half and lo>(1<<32)-16385:up=((1<<32)-lo)<=((2*r+1)**2>>(e+55))
 return ONE+(-1 if neg else 1)*(r+int(up))
def helper_cost(raw):
 neg=int(raw>>63);e=((raw>>52)&2047)-1023;shift=-e-neg-32
 hi=((raw>>32)&0xfffff)|0x100000;lo=raw&MASK;tail=hi&((1<<shift)-1);half=1<<(shift-1)
 if not neg:return 46 if tail+1!=half else 49 if lo<=(1<<32)-16385 else 59
 if tail>half:return 40
 if tail<half:return 43
 if lo==0:return 45
 if lo>16384:return 50
 return 59
def public_tiny_cost(raw):
 return helper_cost(raw)+34+3*int(((raw>>32)&0x7fffffff)==0x3c900000)
