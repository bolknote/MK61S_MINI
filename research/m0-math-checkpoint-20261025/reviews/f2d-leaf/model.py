"""Independent exact binary32 lattice decoder and actual-source reduction."""
MASK=(1<<32)-1;F23=(1<<23)-1
def exact(x):
 s=(x>>31)<<63;e=(x>>23)&255;f=x&F23
 if e==255:return s|0x7ff0000000000000|(f<<29)|((1<<51) if f else 0)
 n=((1<<23)|f) if e else f;power=e-150 if e else -149
 if not n:return s
 k=n.bit_length();biased=k-1+power+1023
 assert 0<biased<2047 and k<=24
 return s|(biased<<52)|((n-(1<<(k-1)))<<(53-k))
def source_model(x):
 shifted=(x<<1)&MASK
 if not shifted:return x<<32,'zero',5,0
 signed=x-(1<<32) if x>>31 else x
 field=((signed>>23)+255) if x>>31 else (x>>23)-1
 if 0<=field<=253:
  high=((signed>>3)+0xc8000000)&MASK if x>>31 else (x>>3)+0x38000000
  return (((x<<29)&MASK)|(high<<32)),'normal',12,0
 fraction=(x<<9)&MASK
 if not fraction:return ((0xfff00000 if x>>31 else 0x7ff00000)<<32),'infinity',12,0
 if field>=0:
  high=((x>>31)<<31)|(fraction>>12)|0x7ff80000
  return ((x<<29)&MASK)|(high<<32),'NaN',19,0
 high=(x>>31)<<31;exp=895;shift=0;choices=[]
 for boundary,amount in [(16,16),(24,8),(28,4),(30,2)]:
  take=not(fraction>>boundary);choices.append(int(take))
  if take:fraction<<=amount;exp-=amount;shift+=amount
 take=not(fraction&(1<<31));choices.append(int(take))
 if take:fraction<<=1;exp-=1;shift+=1
 assert fraction<=MASK and fraction.bit_length()==32
 high+=fraction>>11;high+=(exp<<20)
 return ((fraction<<21)&MASK)|(high<<32),'subnormal',30+2*sum(choices),shift
def reference_partition(x):
 e=(x>>23)&255;f=x&F23
 if 0<e<255:return 'normal',True,13
 if not(e or f):return 'zero',True,8
 if e==255:return ('NaN',False,12) if f else ('infinity',True,12)
 return 'subnormal',False,8
