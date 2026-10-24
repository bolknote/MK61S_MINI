"""Independent integer-cell oracle and source-path/cost reduction; no author oracle."""
MASK=(1<<32)-1;F52=(1<<52)-1
def rne(n,shift):
 if shift<=0:return n<<(-shift)
 q,r=divmod(n,1<<shift);half=1<<(shift-1)
 return q+int(r>half or(r==half and q&1))
def exact(x):
 """Round a signed integer times a power of two onto the binary32 grid."""
 s=(x>>32)&0x80000000;e=(x>>52)&2047;f=x&F52
 if e==2047:return s|0x7f800000|((f>>29)|0x400000 if f else 0)
 n=(1<<52)|f if e else f;power=e-1075 if e else -1074
 if not n:return s
 top=n.bit_length()-1+power;unit=max(top-23,-149);q=rne(n,unit-power)
 if unit==-149 and q<(1<<23):return s|q
 if q==(1<<24):q>>=1;unit+=1
 out_exp=unit+23+127
 if out_exp>=255:return s|0x7f800000
 assert (1<<23)<=q<(1<<24) and 1<=out_exp<255
 return s|(out_exp<<23)|(q-(1<<23))
def source_model(x):
 """32-bit modular algebra of the actual source, with explicit branch costs."""
 hi=x>>32;lo=x&MASK;e=(x>>52)&2047;f=x&F52;sign=(hi>>31)<<31
 shifted=(hi<<2)&MASK
 if not((hi>>30)&1):
  # SUBS lo-1, LDR-preserved C, then SBCS: exact unsigned borrow.
  borrow=int(lo==0);base=873<<22
  if shifted<base+borrow:return sign,'zero',9
  g=(shifted-base-borrow)&MASK
  if g<((24<<22)-1):
   if g==((24<<22)-4) and lo>>29==7:
    return ((((hi>>23)-111)<<23)&MASK),'subnormal_to_normal',19
   prefix=15 if g==((24<<22)-4) else 12
   shift=905-(((hi<<1)&MASK)>>21);assert 9<=shift<=32
   top=(((hi<<11)&MASK)|(1<<31)|(lo>>21))&MASK
   sticky21=(lo<<11)&MASK
   quotient=top>>shift;guard=(top>>(shift-1))&1
   if not guard:return sign|quotient,'subnormal_full_down',prefix+20
   below=(((top<<(33-shift))&MASK)|sticky21)
   quotient+=int(bool(below) or(quotient&1))
   return sign|quotient,'subnormal_full_up' if below else 'subnormal_full_tie',prefix+27
  lower=True
 else:
  if shifted>=(127<<22):
   total=shifted+(1<<22)
   if total<1<<32:return sign|0x7f800000,'overflow',13
   residue=total&MASK
   changed_lo=lo|residue
   if not changed_lo:return ((hi>>23)<<23)&MASK,'infinity',13
   payload=(changed_lo>>29)|(((hi<<12)&MASK)>>9)
   return payload|(((hi>>23)<<23)&MASK)|(1<<22),'NaN',19
  lower=False
 guard=(lo>>28)&1;sticky=((lo<<4)&MASK)!=0;retained=lo>>29
 tie=guard and not sticky
 rounded=retained+int(guard and(sticky or retained&1))
 signed_hi=hi-(1<<32) if hi>>31 else hi
 factor=(signed_hi>>30)+int(lower)
 got=((hi<<3)+(factor<<30)+rounded)&MASK
 mode='truncate' if not guard else ('up' if sticky else 'tie_odd' if retained&1 else 'tie_even')
 return got,('normal_low_' if lower else 'normal_high_')+mode,19+3*guard if lower else 14+3*guard
def reference_partition(x):
 e=(x>>52)&2047;f=x&F52
 if e<873 or(e==873 and f==0):return 'zero',True,9
 if e==896 and f>=F52-(1<<29)+1:return 'subnormal_to_normal',True,20
 if 897<=e<=1150:
  tail=f&((1<<29)-1)
  if tail<(1<<28):mode='truncate';cost=20
  elif tail>(1<<28):mode='up';cost=22
  elif(f>>29)&1:mode='tie_odd';cost=24
  else:mode='tie_even';cost=23
  return ('normal_low_' if e<1024 else 'normal_high_')+mode,True,cost
 if e<897:
  cost=9 if e<896 else 13 if f>>32!=0xfffff else 16
  return 'wrong_subnormal',False,cost
 if e<2047:return 'overflow',True,13
 return ('infinity',True,13) if not f else ('NaN',False,13)
