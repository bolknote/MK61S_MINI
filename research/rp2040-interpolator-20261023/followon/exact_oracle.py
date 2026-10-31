from math import isqrt

def root_oracle(b,inverse=False):
 sign=b>>63;mag=b&((1<<63)-1);inf=0x7ff0000000000000
 if mag>inf:return b|(1<<51)
 if not mag:return ((sign<<63)|inf) if inverse else b
 if mag==inf and not inverse:return b|(1<<51) if sign else b
 if sign:return inf|(1<<51)
 if mag==inf:return 0 if inverse else b
 exponent=b>>52;mantissa=b&((1<<52)-1)
 if exponent:mantissa|=1<<52;e=int(exponent)-1075
 else:e=-1074
 top=mantissa.bit_length()-1+e
 if inverse:
  k=-(top//2)-1
  if top%2==0 and mantissa&(mantissa-1)==0:k+=1
  num=1<<(104-2*k-e);den=mantissa
 else:k=top//2;num=mantissa<<(e+104-2*k);den=1
 q=isqrt(num//den);mid=den*(2*q+1)**2
 if 4*num>mid or (4*num==mid and q&1):q+=1
 if q==1<<53:q>>=1;k+=1
 assert 1<<52<=q<1<<53
 return ((k+1023)<<52)|(q&((1<<52)-1))
