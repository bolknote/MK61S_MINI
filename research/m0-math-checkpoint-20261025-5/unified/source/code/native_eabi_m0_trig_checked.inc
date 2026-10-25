#include "native_eabi_m0_trig_refine.inc"
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
#define MK61_M0_TRIG_SECTION(name) __attribute__((section(".m0_trig_" name)))
#else
#define MK61_M0_TRIG_SECTION(name)
#endif
struct CheckedTrigArgument {U q;int e;unsigned n,error;bool negative;int16_t tail;};
static_assert(sizeof(CheckedTrigArgument)==24,"Trig argument tail uses existing padding");
struct CheckedTrigValue {U q;int e;unsigned error;};
MK61_M0_TRIG_SECTION("inverse")
__attribute__((optimize("Os"),noinline)) static U checked_trig_inverse(U denominator) {
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  const U d=denominator<<1;
  const uint32_t high=uint32_t(d>>32),low=uint32_t(d);
  // y0=seed*2^31. The high==2^31 endpoint has seed==2^32.
  if(high==0x80000000U) return (U(1)<<63)-U(low&~1U);
  const uint32_t seed=atan_div64_32(U(1)<<63,high);
  const uint32_t remainder=0U-high*seed;
  const uint32_t cross=uint32_t(wide32(low,seed)>>32);
  // floor(d*y0/2^64)-2^62 == floor((cross-remainder)/2).
  // Its magnitude is <2^31, so the Newton correction needs one32x32
  // product, rather than a general64x64 Q62 multiplication.
  const bool subtract=cross>=remainder;
  const uint32_t magnitude=subtract?(cross-remainder)>>1:(remainder-cross+1U)>>1;
  const U product=wide32(seed,magnitude);
  const uint32_t tail=uint32_t(product)&0x7FFFFFFFU;
  uint32_t correction=(uint32_t(product>>32)<<1)|uint32_t(product>>31&1U);
  correction+=tail>0x40000000U || (tail==0x40000000U && (correction&1));
  const U y=U(seed)<<31;
  // Exact floor in the residual and RNE in the correction give |error|<2.5
  // Q62 units. Existing callers retain their more conservative five units.
  return subtract?y-correction:y+correction;
#else
  const U d=denominator<<1,one=U(1)<<62;
  const uint32_t high=uint32_t(d>>32);
  U y=high==0x80000000U?U(1)<<63:U(atan_div64_32(U(1)<<63,high))<<31;
  {
    const U product=multiply(d,y).high;
    const bool negative=product>one;
    const U correction=mk61_m0_mul_q62(y,negative?product-one:one-product);
    y=negative?y-correction:y+correction;
  }
  // The quotient seed has relative error <2^-31. The integer Newton step
  // adds <2.5 Q62 units; its final absolute error is strictly below five.
  return y;
#endif
}
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
// Only used with 4<=shift<=30. Keep the carry between the two words
// explicit, avoiding a call to the general EABI 64-bit shift helper.
__attribute__((always_inline)) inline U checked_trig_left(U value,unsigned shift) {
  const uint32_t lo=uint32_t(value),hi=uint32_t(value>>32);
  return (U((hi<<shift)|(lo>>(32-shift)))<<32)|uint32_t(lo<<shift);
}
#endif
#if !defined(MK61_M0_RP2040_EABI) || !MK61_M0_RP2040_EABI
#define checked_trig_left(value,shift) ((value)<<(shift))
#endif
MK61_M0_TRIG_SECTION("argument")
__attribute__((optimize("Os"),noinline)) static void checked_trig_argument(U m,CheckedTrigArgument* a) {
  a->n=0;a->negative=false;a->error=0;a->tail=0;
  const U s=(m&D::Fraction)|D::Hidden;const int e=int(m>>52)-1023;
  if(m<=UINT64_C(0x3FE921FB54442D18)) {
    if(m>=UINT64_C(0x3F90000000000000)) {a->q=checked_trig_left(s,unsigned(e+10));a->e=1;}
    else {a->q=s<<10;a->e=e+1;}
    return;
  }
  const U estimate=wide32(uint32_t(s>>21),0xA2F9836EU);
  uint32_t n=e==-1?uint32_t(estimate>=(U(1)<<63)):uint32_t((estimate+(U(1)<<(62-e)))>>unsigned(63-e));
  if(!n) {a->q=checked_trig_left(s,unsigned(e+10));a->e=1;return;}
  const U lo=wide32(trig_pi2[3],n),middle=wide32(trig_pi2[4],n)+(lo>>32);
  const uint32_t top=trig_pi2[5]*n+uint32_t(middle>>32);
  uint32_t low=0U-uint32_t(lo);
  U high=(checked_trig_left(s,unsigned(e+11)))-((U(top)<<32)|uint32_t(middle))-U(low!=0);
  bool negative=bool(high>>63);
  if(negative) {low=0U-low;high=~high+U(!low);}
  const bool upward=(high&1) && (low||((high>>1)&1));
  U q=(high>>1)+U(upward);
  int exponent=1;
  if(q>=(U(1)<<56)) {
    const unsigned tail=unsigned(high&1)*128+(low>>25);
    const uint32_t fine=low&0x1FFFFFFU;
    a->tail=int16_t(int(tail)+int(fine>0x1000000U || (fine==0x1000000U && (tail&1)))-int(upward)*256);
    // Q95 pi/2 truncation contributes <1/32 Q70 unit for n<2^20.
    // Keeping its eight low bits and rounding once to Q70 bounds the
    // argument error below one Q70 unit, including negative remainders.
  }
  if(q<(U(1)<<56)) {
    // Extend the existing Q95 subtraction by one pi/2 limb. This reuses
    // the three completed products instead of recomputing all six Q191
    // products for ordinary small remainders.
    const U extension=wide32(trig_pi2[2],n);
    U lower=U(low)<<32;
    if(negative) {const U old=lower;lower+=extension;high+=U(lower<old);}
    else {
      const U old=lower;lower-=extension;high-=U(old<extension);
      if(high>>63) {lower=U(0)-lower;high=~high+U(!lower);negative=true;}
    }
    if(high>=(U(1)<<19)) {
      const unsigned leading=clz64(high);exponent=1-int(leading);
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
      const uint32_t hh=uint32_t(high>>32),hl=uint32_t(high);
      const uint32_t lh=uint32_t(lower>>32),ll=uint32_t(lower);
      uint32_t th,tl;bool sticky;
      // high is in [2^19,2^57), hence 7<=leading<=44. These two
      // branches exactly form the top64 bits and nonzero discarded tail
      // of (high:lower)<<leading. No numerical approximation is added.
      if(leading<32) {
        th=(hh<<leading)|(hl>>(32-leading));
        tl=(hl<<leading)|(lh>>(32-leading));
        sticky=ll || uint32_t(lh<<leading);
      } else {
        const unsigned shift=leading-32;
        th=shift?(hl<<shift)|(lh>>(32-shift)):hl;
        tl=shift?(lh<<shift)|(ll>>(32-shift)):lh;
        sticky=uint32_t(ll<<shift);
      }
      const U retained=(U(th>>1)<<32)|((tl>>1)|(th<<31));
      q=retained+U((tl&1) && (sticky||(tl&2)));
#else
      const U top=(high<<leading)|(lower>>(64-leading));
      q=(top>>1)+U((top&1) && ((lower<<leading)||((top>>1)&1)));
#endif
      // n<2^20 and e>=-43: pi/2 truncation contributes <2^-1
      // relative Q63 unit; nearest-even contributes at most another half.
    } else {
      const Trig192 r=trig_remainder(m,n,negative);
      q=trig_relative(r,exponent);
      if(exponent<-99) q=0;
    }
  }
  // Q95 pi/2 truncation plus final rounding is <1 Q62 unit. Small
  // remainders use Q127/Q191 before relative normalization to retain it.
  a->q=q;a->e=exponent;a->n=n;a->negative=negative;a->error=1;
}
#if !defined(MK61_M0_RP2040_EABI) || !MK61_M0_RP2040_EABI
#undef checked_trig_left
#endif
__attribute__((always_inline)) inline bool checked_trig_pack(CheckedTrigValue a,U sign,U &result) {
  if(!a.q) return false;
  const unsigned width=64-clz64(a.q),shift=width-53;
  const uint32_t half=1U<<(shift-1),lo=uint32_t(a.q),hi=uint32_t(a.q>>32),tail=lo&((half<<1)-1);
  if(tail>=half?tail-half<=a.error:half-tail<=a.error) return false;
  const U retained=(U(hi>>shift)<<32)|uint32_t((lo>>shift)|(hi<<(32-shift)));
  const U q=retained+U(tail>half || (tail==half && (retained&1)));
  result=sign+(U(a.e+int(width)+958)<<52)+q;return true;
}
__attribute__((always_inline)) inline U checked_trig_small_square(U q,int e) {
  if(e<=-32) return 0;
  if(e>-18) return math62_square(q,e);
  const U square=wide32(uint32_t(q>>32),uint32_t(q>>32));
  const unsigned shift=unsigned(-2*e-32);
  const uint32_t high=uint32_t(square>>32),half=1U<<(shift-1),tail=high&((half<<1)-1);
  // The two omitted low-limb terms contribute <1/16 Q62 unit.
  return (high>>shift)+U(tail>half || (tail==half && (uint32_t(square)||((high>>shift)&1))));
}
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
static U checked_trig_sin_tiny(U q,int e);
#endif
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
__attribute__((optimize("Os"),always_inline)) inline
#else
MK61_M0_TRIG_SECTION("small")
__attribute__((optimize("Os"),noinline))
#endif
static CheckedTrigValue checked_trig_small(CheckedTrigArgument a,unsigned op) {
  const U one=U(1)<<62;
  if(op==1 && a.e<=-27) return {one,1,0};
  if(op==0 && a.e<=-27) {
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
    if(a.e>=-30) return {checked_trig_sin_tiny(a.q,a.e),a.e,1+a.error};
#endif
    const int power=2*a.e+63;
    const unsigned error=power<0?1:((1U<<unsigned(power))+5)/6;
    return {a.q,a.e,error+a.error};
  }
  const U z=checked_trig_small_square(a.q,a.e);
  if(!op && a.e<=-18) {
    const U sixth=(uint32_t(wide32(uint32_t(z)+1,0xAAAAAAABU)>>33)+1)>>1;
    return {a.q-mk61_m0_mul_q62(a.q,sixth),a.e,3+2*a.error};
  }
  if(a.e<=-13) {
    if(!op) return {math62_product(a.q,one-((math62_third(z)+1)>>1)),a.e,(a.e==-13?24U:8U)+2*a.error};
    return {one-((z+1)>>1),1,(a.e==-13?44U:a.e==-14?4U:1U)+a.error};
  }
  const U z2=math62_product(z,z);
  if(!op) {
    const uint32_t c=0x22222222U-uint32_t(wide32(uint32_t(z>>22),852176U)>>32);
    const U factor=one-((math62_third(z)+1)>>1)+math62_scale40(z2,c,2);
    return {math62_product(a.q,factor),a.e,8+2*a.error};
  }
  const uint32_t c=0xAAAAAAABU-uint32_t(wide32(uint32_t(z>>22),5965232U)>>32);
  return {one-((z+1)>>1)+math62_scale40(z2,c,10),1,8+a.error};
}
#include "native_eabi_m0_trig_small_refine.inc"
#include "native_eabi_m0_trig_tan.inc"
// Try the cheaper Q62 evaluation before Q70. Both passes use the same
// Q94 table, so this does not enlarge the data working set. The Q62
// truncations (instead of rounded table entries) fit a seven-unit bound.
MK61_M0_TRIG_SECTION("fast_table")
__attribute__((optimize("Os"),noinline)) static U checked_trig_fast_table(CheckedTrigArgument a,unsigned op,U sign) {
  const unsigned j=unsigned((a.q+(U(1)<<51))>>52);
  const uint32_t* row=trig94_table[j];
  const U s=(U(row[2])<<32)|row[1],c=(U(row[5])<<32)|row[4];
  U value=op?c:s;unsigned error=1+a.error;
  const U h=a.q-(U(j)<<52);
  if(h) {
    const bool negative=bool(h>>63);const U magnitude=negative?U(0)-h:h;
    const uint32_t t=uint32_t(magnitude>>20);
    const U square=wide32(t,t),cross=wide32(t,uint32_t(magnitude)&0xFFFFFU);
    const U z=(square>>22)+(cross>>41)+1;
    const U p=wide32(uint32_t(square),t);
    const uint32_t cube=uint32_t((wide32(uint32_t(square>>32),t)+(p>>32))>>32);
    const uint32_t third=uint32_t(wide32(cube+3,0xAAAAAAABU)>>34);
    const uint32_t fourth=uint32_t(wide32(uint32_t(wide32(cube,t)>>42)+12,0xAAAAAAABU)>>36);
    const U sh=magnitude-third,ch=((z+1)>>1)-fourth;
    const U odd=mk61_m0_mul_q62(op?s:c,sh);
    value-=trig_small_product(value,ch);
    value+=negative!=bool(op)?U(0)-odd:odd;
    error=7+a.error;
  }
  unsigned shift=9;uint32_t high=uint32_t(value>>32);
  if(high<(1U<<26)) {high<<=4;shift-=4;}
  if(high<(1U<<28)) {high<<=2;shift-=2;}
  if(high<(1U<<29)) --shift;
  const uint32_t half=1U<<(shift-1),lo=uint32_t(value),hi=uint32_t(value>>32),tail=lo&((half<<1)-1);
  if(tail>=half?tail-half<=error:half-tail<=error) return 0;
  const U retained=(U(hi>>shift)<<32)|uint32_t((lo>>shift)|(hi<<(32-shift)));
  return sign+(U(shift+1012)<<52)+retained+U(tail>half || (tail==half && (retained&1)));
}
// Evaluate the ordinary sin/cos cells in Q70. The Q94 refinement table
// supplies both the Q70 base and Q62 coefficients without another table.
// Retaining these eight guard bits avoids most calls to the middle pass.
MK61_M0_TRIG_SECTION("table")
__attribute__((optimize("Os"),noinline)) static U checked_trig_table(CheckedTrigArgument a,unsigned op,U sign) {
  const unsigned j=unsigned((a.q+(U(1)<<51))>>52);
  const U h=((a.q-(U(j)<<52))<<8)+U(int64_t(a.tail));
  const uint32_t* row=trig94_table[j];
  const U s=(U(row[2])<<32)|row[1],c=(U(row[5])<<32)|row[4];
  const U base=op?c:s;
  Refine96 value={(base<<8)|(row[op?3:0]>>24),uint32_t(base>>56)};
  unsigned error=1+a.error;
  if(h) {
    const bool negative=bool(h>>63);const U linear=negative?U(0)-h:h,magnitude=linear>>8;
    const uint32_t t=uint32_t(magnitude>>20);
    const U square=wide32(t,t),cross=wide32(t,uint32_t(magnitude)&0xFFFFFU);
    const uint32_t fraction=((uint32_t(square)&0x3FFFU)<<10)+(uint32_t(cross>>9)&0xFFFFFFU);
    const U z=(square>>14)+(cross>>33)+((fraction+(1U<<23))>>24);
    const U cube=math62_product(z,magnitude);
    const uint32_t zr=uint32_t((z+(1U<<17))>>18);
    const uint32_t fourth=uint32_t((wide32(zr,zr)+(U(1)<<33))>>34);
    const uint32_t fifth=uint32_t((wide32(fourth,t)+(U(1)<<41))>>42);
    const U sh=linear-((math62_third(cube)+1)>>1)+
      (wide32(fifth+60,0x88888889U)>>38);
    const U ch=((z+1)>>1)-(wide32(fourth+12,0xAAAAAAABU)>>36);
    const U even=math62_product(base,ch),odd=math62_product(op?s:c,sh);
    value=r96_sub_low(value,even);
    value=negative!=bool(op)?r96_sub_low(value,odd):r96_add_low(value,odd);
    // Square <0.751, cube <2.501, fourth <0.563, fifth <0.501
    // Q70 units; the complete evaluation error is below twelve units.
    // |sin'|,|cos'| <= 1 adds at most the Q70 argument error.
    error=12+a.error;
  }
  // On this path |r| >= 1/64; sin(r) can be just below 1/64,
  // giving a 64-bit value, and all other results have 65..71 bits.
  unsigned shift=value.high?12:11;uint32_t high=value.high;
  if(high>=16) {high>>=4;shift+=4;}
  if(high>=4) {high>>=2;shift+=2;}
  if(high>=2) ++shift;
  const uint32_t half=1U<<(shift-1),lo=uint32_t(value.low),hi=uint32_t(value.low>>32),tail=lo&((half<<1)-1);
  if(tail>=half?tail-half<=error:half-tail<=error) return 0;
  const U retained=(U((hi>>shift)|(value.high<<(32-shift)))<<32)|uint32_t((lo>>shift)|(hi<<(32-shift)));
  return sign+(U(shift+1004)<<52)+retained+U(tail>half || (tail==half && (retained&1)));
}
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
extern "C" __attribute__((cold)) MK61_SOFT_PCS double mk61_m0_trig_large(double,unsigned);
#define MK61_M0_TRIG_COLD mk61_m0_trig_large
#else
#define MK61_M0_TRIG_COLD checked_trig_backend
#endif
MK61_M0_TRIG_SECTION("dispatch")
__attribute__((optimize("Os"))) MK61_SOFT_PCS double mk61_m0_trig(double x,unsigned op) {
  const U b=bits(x),m=b&D::Magnitude;
  if(m<UINT64_C(0x3E40000000000000)) return op==1?1.:x;
  if(m>=UINT64_C(0x4130000000000000)) return MK61_M0_TRIG_COLD(x,op);
  CheckedTrigArgument a;checked_trig_argument(m,&a);
  if(!a.q) return MK61_M0_TRIG_COLD(x,op);
  const unsigned selected=op==0?(a.n&1):op==1?((a.n&1)^1):2;
  U result;
  if(op==2) {
    const unsigned flip=unsigned(b>>63)^unsigned(a.negative)^(a.n&1);
    if(a.e==1) {
      result=checked_trig_tan_table(a,U(flip)<<63);
      if(result) return real(result);
    } else {
      CheckedTrigValue f=checked_trig_tan_small(a);
      if(a.n&1) {
        if(f.q>>63) {f.q>>=1;++f.e;f.error=(f.error+1)/2+1;}
        f={checked_trig_inverse(f.q),1-f.e,2*f.error+6};
      }
      if(atan_pack(f.q,f.e,U(flip)<<63,f.error,result)) return real(result);
    }
  } else {
    const unsigned flip=(op==0?((a.n>>1)&1)^unsigned(b>>63):((a.n+1)>>1)&1)^(selected?0:unsigned(a.negative));
    if(a.e==1) {
      // Very small sine values have narrow Q62 rounding cells; go
      // directly to Q70 there instead of paying for a rejected pass.
      result=selected || a.q>=(U(1)<<59)?checked_trig_fast_table(a,selected,U(flip)<<63):0;
      if(!result) result=checked_trig_table(a,selected,U(flip)<<63);
      if(result) return real(result);
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
    } else {
      result=checked_trig_small_packed(a,selected,U(flip)<<63);
      if(result) return real(result);
    }
#else
    } else if(checked_trig_pack(checked_trig_small(a,selected),U(flip)<<63,result)) return real(result);
#endif
  }
  return checked_trig_refine(x,op);
}

#undef MK61_M0_TRIG_SECTION

#undef MK61_M0_TRIG_COLD
