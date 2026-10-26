// Project-owned ARMv6-M IEEE binary32/binary64 arithmetic.
// Integer algorithms: nearest-even, gradual underflow, signed zero and NaNs.
// No allocation, errno/fenv, division instructions, 64-bit multiply
// instructions, or dependency on compiler runtime archives.
#include "native_eabi_m0.hpp"
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI
#include <float.h>
#if defined(__arm__) || defined(__thumb__)
#include "compact_math_tables.hpp"
#endif
static_assert(sizeof(double)==8 && DBL_MANT_DIG==53 && sizeof(float)==4 && FLT_MANT_DIG==24,
              "M0 EABI requires IEEE binary64/binary32");
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
extern "C" MK61_SOFT_PCS double mk61_m0_ln_special(double);
extern "C" MK61_SOFT_PCS double mk61_m0_log10_special(double);
#define MK61_M0_EXP_CORE __attribute__((section(".m0_exp_core")))
#define MK61_M0_TRIG_REFINE_VALUES __attribute__((section(".m0_trig_refine_values_fixed")))
#define MK61_M0_TRIG_REFINE __attribute__((section(".m0_trig_refine_fixed")))
#define MK61_M0_TRIG_CACHE(name) __attribute__((section(".m0_trig_cache_" #name)))
#else
#define MK61_M0_EXP_CORE
#define MK61_M0_TRIG_REFINE_VALUES
#define MK61_M0_TRIG_REFINE
#define MK61_M0_TRIG_CACHE(name)
#endif
namespace m0_eabi {
using U = uint64_t;
template<class To, class From> inline To copy(From x) {
  static_assert(sizeof(To)==sizeof(From), "bit copy size");
  To y; __builtin_memcpy(&y,&x,sizeof(y)); return y;
}
MK61_M0_TRIG_CACHE(clz32) unsigned clz32(uint32_t x) {
  if(!x) return 32;
  unsigned n=0;
  if(!(x&0xFFFF0000U)) {n+=16;x<<=16;}
  if(!(x&0xFF000000U)) {n+=8;x<<=8;}
  if(!(x&0xF0000000U)) {n+=4;x<<=4;}
  if(!(x&0xC0000000U)) {n+=2;x<<=2;}
  return n+unsigned(!(x&0x80000000U));
}
MK61_M0_TRIG_CACHE(clz64) unsigned clz64(U x) {return uint32_t(x>>32)?clz32(uint32_t(x>>32)):32+clz32(uint32_t(x));}
// Four 16x16 products, each fitting in a 32-bit MULS result. In particular,
// do not express this as uint64_t(a)*b: that would call our own __aeabi_lmul.
__attribute__((always_inline)) inline U wide32(uint32_t a,uint32_t b) {
  const uint32_t al=a&0xFFFFU,ah=a>>16,bl=b&0xFFFFU,bh=b>>16;
  const uint32_t p=al*bl,t=ah*bl+(p>>16),v=al*bh+(t&0xFFFFU);
  return (U(ah*bh+(t>>16)+(v>>16))<<32)|(uint32_t(v<<16)|(p&0xFFFFU));
}
struct Product {U high,low;};
__attribute__((always_inline)) inline Product multiply(U a,U b) {
  const uint32_t al=uint32_t(a),ah=uint32_t(a>>32),bl=uint32_t(b),bh=uint32_t(b>>32);
  const U p=wide32(al,bl),t=wide32(ah,bl)+(p>>32),v=wide32(al,bh)+uint32_t(t);
  return {wide32(ah,bh)+(t>>32)+(v>>32),(v<<32)|uint32_t(p)};
}
U jam(U x,unsigned n) {
  if(!n) return x;
  if(n>=64) return x!=0;
  return (x>>n)|U((x<<(64-n))!=0);
}
U jam_product(Product p,unsigned n) {
  // Used for binary64 (49/50) and binary32 (20/21) product reductions.
  return (p.high<<(64-n))|(p.low>>n)|U((p.low<<(64-n))!=0);
}
// Exact rational seeds, evaluated at compile time. These are independently
// generated constants, not a table or code taken from another math library.
struct ReciprocalSeeds {
  uint16_t values[128]{};
  constexpr ReciprocalSeeds() {
    for(unsigned i=0;i<128;++i) values[i]=uint16_t((1U<<22)/(128+i));
  }
};
constexpr ReciprocalSeeds reciprocal_seeds;
#if defined(__arm__) || defined(__thumb__)
#include "native_eabi_m0_exp_table.inc"
#include "native_eabi_m0_trig_table.inc"
#include "native_eabi_m0_log_table.inc"
#include "native_eabi_m0_refine_table.inc"
#include "native_eabi_m0_log70_table.inc"
#include "native_eabi_m0_trig_checked_table.inc"
#endif
MK61_M0_TRIG_CACHE(low_product) inline U low_product(U a,U b) {
  return wide32(uint32_t(a),uint32_t(b))+
    (U(uint32_t(a)*uint32_t(b>>32)+uint32_t(a>>32)*uint32_t(b))<<32);
}
#if defined(__arm__) || defined(__thumb__)
// The omitted low partial product and cross-word carries contribute at
// most two units to the exact high word. exp retains ten guard bits, so
// this error is below 1/256 ULP even in its final table product.
__attribute__((always_inline)) inline U exp_high_product(U a,U b) {
  const uint32_t al=uint32_t(a),ah=uint32_t(a>>32),bl=uint32_t(b),bh=uint32_t(b>>32);
  return wide32(ah,bh)+(wide32(al,bh)>>32)+(wide32(ah,bl)>>32);
}
// Square uses one cross product instead of two separately truncated copies.
// The missing low square and the cross-product fraction sum to <2 units;
// adding1 gives absolute error <=1, including zero ->1.
__attribute__((always_inline)) inline U exp_high_square(U a) {
  const uint32_t lo=uint32_t(a),hi=uint32_t(a>>32);
  return wide32(hi,hi)+(wide32(lo,hi)>>31)+1;
}
#endif
// Quotient estimate for 1 <= a/b < 2, followed by an exact remainder.
// Refining 16 -> 32 -> 63 reciprocal bits avoids a 56-step restoring loop.
// Once the estimate is within a few units, its signed residual fits in 64
// bits: only the low product is needed to correct the full 106-bit quotient.
U divide_significands(U a,U b,U& remainder) {
  if(b==(U(1)<<52)) {remainder=0;return a;}
  const uint32_t d16=uint32_t(b>>37);
  uint32_t r16=reciprocal_seeds.values[(d16>>8)-128];
  uint32_t product=d16*r16;
  bool negative=product>(1U<<30);
  uint32_t error=negative?product-(1U<<30):(1U<<30)-product;
  uint32_t correction=(r16*(error>>7))>>23;
  r16=negative?r16-correction:r16+correction;
  product=d16*r16;negative=product>(1U<<30);
  error=negative?product-(1U<<30):(1U<<30)-product;
  correction=((r16>>2)*(error>>2))>>26;
  r16=negative?r16-correction:r16+correction;

  uint32_t r32=r16<<16;
  const U p32=wide32(uint32_t(b>>21),r32),one=U(1)<<62;
  negative=p32>one;
  const U e32=negative?p32-one:one-p32;
  correction=uint32_t(wide32(r32>>15,uint32_t(e32>>17))>>30);
  r32=negative?r32-correction:r32+correction;

  const U signed_error=U(0)-low_product(b,r32);
  negative=(signed_error>>63)!=0;
  const U e64=negative?U(0)-signed_error:signed_error;
  const U c54=wide32(r32,uint32_t(e64>>24))>>37;
  U reciprocal=U(r32)<<22;
  reciprocal=(negative?reciprocal-c54:reciprocal+c54)<<10;

  const uint32_t al=uint32_t(a),ah=uint32_t(a>>32),rl=uint32_t(reciprocal),rh=uint32_t(reciprocal>>32);
  const U cross1=wide32(al,rh),cross=cross1+wide32(ah,rl);
  const U high=wide32(ah,rh)+(cross>>32)+(cross<cross1?(U(1)<<32):0);
  U q=(high<<1)|(uint32_t(cross)>>31);
  remainder=(a<<52)-low_product(q,b);
  while(remainder>>63) {--q;remainder+=b;}
  while(remainder>=b) {++q;remainder-=b;}
  return q;
}

template<unsigned F,unsigned E> struct Binary {
  static constexpr U Hidden=U(1)<<F,Sign=U(1)<<(F+E),Magnitude=Sign-1;
  static constexpr U Fraction=Hidden-1,Infinity=((U(1)<<E)-1)<<F,Quiet=Hidden>>1;
  static constexpr int Bias=(1<<(E-1))-1,Min=1-Bias,Max=Bias;
  static bool is_nan(U x) {return (x&Magnitude)>Infinity;}
  static U nan(U a,U b) {return (is_nan(a)?a:b)|Quiet;}
  static U normalize(U a,int& e) {
    const unsigned raw=unsigned((a>>F)&((1U<<E)-1));
    U s=a&Fraction;
    if(raw) {e=int(raw)-Bias;return s|Hidden;}
    const unsigned shift=clz64(s)-(63-F);
    e=Min-int(shift);return s<<shift;
  }
  // s has F fraction bits plus guard/round/sticky, and its leading bit at F+3.
  static U pack(U sign,int e,U s) {
    if(e<Min) {s=jam(s,unsigned(Min-e));e=Min;}
    U q=s>>3;const unsigned tail=unsigned(s&7);
    q+=tail>4 || (tail==4 && (q&1));
    if(q>=Hidden+Hidden) {q>>=1;++e;}
    if(e>Max) return sign|Infinity;
    if(q<Hidden) return sign|q;
    return sign|(U(e+Bias)<<F)|(q&Fraction);
  }
  static U add(U a,U b) {
    U ma=a&Magnitude,mb=b&Magnitude;
    if(ma>Infinity || mb>Infinity) return nan(a,b);
    if(ma==Infinity || mb==Infinity) {
      if(ma==Infinity && mb==Infinity && ((a^b)&Sign)) return Infinity|Quiet;
      return ma==Infinity?a:b;
    }
    if(!ma && !mb) return (a&b)&Sign;
    if(!ma) return b;
    if(!mb) return a;
    if(ma<mb) {const U t=a;a=b;b=t;}
    int ea,eb;U sa=normalize(a,ea)<<3,sb=normalize(b,eb)<<3;
    sb=jam(sb,unsigned(ea-eb));
    if(!((a^b)&Sign)) {
      sa+=sb;
      if(sa&(Hidden<<4)) {sa=jam(sa,1);++ea;}
    } else {
      sa-=sb;
      if(!sa) return 0;
      const unsigned shift=clz64(sa)-(63-F-3);sa<<=shift;ea-=int(shift);
    }
    return pack(a&Sign,ea,sa);
  }
  static U mul(U a,U b) {
    const U ma=a&Magnitude,mb=b&Magnitude,sign=(a^b)&Sign;
    if(ma>Infinity || mb>Infinity) return nan(a,b);
    if(ma==Infinity || mb==Infinity) return !ma || !mb?Infinity|Quiet:sign|Infinity;
    if(!ma || !mb) return sign;
    int ea,eb;const U sa=normalize(a,ea),sb=normalize(b,eb);
    const Product p=multiply(sa,sb);
    const bool high=F==52 ? (p.high&(U(1)<<41))!=0:(p.low&(U(1)<<47))!=0;
    return pack(sign,ea+eb+int(high),jam_product(p,F-3+unsigned(high)));
  }
  static U div(U a,U b) {
    const U ma=a&Magnitude,mb=b&Magnitude,sign=(a^b)&Sign;
    if(ma>Infinity || mb>Infinity) return nan(a,b);
    if((ma==Infinity && mb==Infinity) || (!ma && !mb)) return Infinity|Quiet;
    if(ma==Infinity || !mb) return sign|Infinity;
    if(!ma || mb==Infinity) return sign;
    int ea,eb;U remainder=normalize(a,ea);const U denominator=normalize(b,eb);
    int e=ea-eb;
    if(remainder<denominator) {remainder<<=1;--e;}
    if constexpr(F==52) {
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
      // Finite nonzero operands, normalized quotient in [1,2). A true
      // exponent above1023 is already beyond the RNE overflow midpoint.
      // Preserve the exact significand division for the boundary exponent.
      if(e>Bias) return sign|Infinity;
      // A normalized quotient below the subnormal binade has only one
      // possible nonzero rounding: e=-1075 and exact ratio greater than1.
      if(e<Min-int(F))
        return sign|U(e==Min-int(F)-1 && remainder!=denominator);
#endif
      U residual;const U q=divide_significands(remainder,denominator,residual);
      const U twice=residual+residual;
      return pack(sign,e,(q<<3)|(twice>denominator?5:twice==denominator?4:residual?1:0));
    }
    // Exact restoring quotient, retaining three rounding bits and a sticky
    // remainder. All intermediate remainders fit in F+2 bits.
    U q=0;
    for(unsigned i=0;i<F+4;++i) {
      q<<=1;
      if(remainder>=denominator) {remainder-=denominator;q|=1;}
      if(i!=F+3) remainder<<=1;
    }
    return pack(sign,e,q|U(remainder!=0));
  }
  static int compare(U a,U b) {
    if(is_nan(a) || is_nan(b)) return 2;
    if(a==b || !((a|b)&Magnitude)) return 0;
    if((a^b)&Sign) return a&Sign?-1:1;
    return (a&Sign?a>b:a<b)?-1:1;
  }
  static U from_integer(U x,U sign=0) {
    if(!x) return 0;
    const unsigned top=63-clz64(x);
    return pack(sign,int(top),top>F+3?jam(x,top-F-3):x<<(F+3-top));
  }
  static U magnitude_integer(U a) {
    const U m=a&Magnitude;const int e=int(m>>F)-Bias;
    if(m>Infinity || e<0) return 0;
    if(e>=64) return UINT64_MAX;
    const U s=(a&Fraction)|Hidden;
    return e>=int(F)?s<<unsigned(e-F):s>>unsigned(F-e);
  }
  static int32_t signed32(U a) {
    const U m=magnitude_integer(a),limit=a&Sign?U(0x80000000):U(0x7FFFFFFF);
    const uint32_t q=uint32_t(m>limit?limit:m);
    return copy<int32_t>(a&Sign?uint32_t(0)-q:q);
  }
  static uint32_t unsigned32(U a) {
    if(a&Sign) return 0;
    const U m=magnitude_integer(a);return m>UINT32_MAX?UINT32_MAX:uint32_t(m);
  }
};
using D=Binary<52,11>;
using S=Binary<23,8>;
inline U bits(double x) {return copy<U>(x);}
inline U bits(float x) {return copy<uint32_t>(x);}
inline double real(U x) {return copy<double>(x);}
inline float single(U x) {return copy<float>(uint32_t(x));}
#include "native_eabi_m0_fma.inc"
U integer_magnitude(int64_t x) {const U u=copy<U>(x);return x<0?U(0)-u:u;}
U extend(U a) {
  const U sign=(a&S::Sign)<<32,m=a&S::Magnitude;
  if(m>=S::Infinity) return sign|D::Infinity|((a&S::Fraction)<<29)|(m>S::Infinity?D::Quiet:0);
  if(!m) return sign;
  int e;const U sig=S::normalize(a,e);return D::pack(sign,e,sig<<32);
}
U narrow(U a) {
  const U sign=(a&D::Sign)>>32,m=a&D::Magnitude;
  if(m>=D::Infinity) return sign|S::Infinity|((a&D::Fraction)>>29)|(m>D::Infinity?S::Quiet:0);
  if(!m) return sign;
  int e;const U sig=D::normalize(a,e);return S::pack(sign,e,jam(sig,26));
}
#if !defined(__arm__) && !defined(__thumb__)
U sqrt_single(U a) {
  const U magnitude=a&S::Magnitude;
  if(!magnitude) return a;
  if(S::is_nan(a)) return a|S::Quiet;
  if(a&S::Sign) return S::Infinity|S::Quiet;
  if(magnitude==S::Infinity) return a;
  int e;U sig=S::normalize(a,e);const unsigned odd=unsigned(e)&1;
  const U radicand=sig<<(23+odd);
  // Restoring integer square root, two radicand bits per iteration.
  U root=0,remainder=0;
  for(unsigned i=24;i--;) {
    remainder=(remainder<<2)|((radicand>>(i*2))&3);
    const U trial=(root<<2)|1;root<<=1;
    if(remainder>=trial) {remainder-=trial;root|=1;}
  }
  root+=remainder>root; // An integer radicand cannot be exactly (root+1/2)^2.
  int out=(e-int(odd))/2;
  if(root>=S::Hidden+S::Hidden) {root>>=1;++out;}
  return (U(out+S::Bias)<<23)|(root&S::Fraction);
}
#endif
} // namespace m0_eabi
using namespace m0_eabi;
extern "C" {
MK61_SOFT_PCS double mk61_m0_fma(double a,double b,double c) {return real(fused(bits(a),bits(b),bits(c)));}
#if defined(__arm__) || defined(__thumb__)
MK61_SOFT_PCS double mk61_m0_dadd_slow(double a,double b) {return real(D::add(bits(a),bits(b)));}
#else
MK61_SOFT_PCS double __aeabi_dadd(double a,double b) {return real(D::add(bits(a),bits(b)));}
MK61_SOFT_PCS double __aeabi_dsub(double a,double b) {return real(D::add(bits(a),bits(b)^D::Sign));}
#endif
MK61_SOFT_PCS double __aeabi_drsub(double a,double b) {return __aeabi_dsub(b,a);}
#if defined(__arm__) || defined(__thumb__)
MK61_SOFT_PCS double mk61_m0_dmul_slow(double a,double b) {return real(D::mul(bits(a),bits(b)));}
#else
MK61_SOFT_PCS double __aeabi_dmul(double a,double b) {return real(D::mul(bits(a),bits(b)));}
#endif
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
MK61_SOFT_PCS double mk61_m0_ddiv_slow(double a,double b) {return real(D::div(bits(a),bits(b)));}
#else
MK61_SOFT_PCS double __aeabi_ddiv(double a,double b) {return real(D::div(bits(a),bits(b)));}
#endif
MK61_SOFT_PCS float __aeabi_fadd(float a,float b) {return single(S::add(bits(a),bits(b)));}
MK61_SOFT_PCS float __aeabi_fsub(float a,float b) {return single(S::add(bits(a),bits(b)^S::Sign));}
MK61_SOFT_PCS float __aeabi_frsub(float a,float b) {return __aeabi_fsub(b,a);}
MK61_SOFT_PCS float __aeabi_fmul(float a,float b) {return single(S::mul(bits(a),bits(b)));}
MK61_SOFT_PCS float __aeabi_fdiv(float a,float b) {return single(S::div(bits(a),bits(b)));}
#define COMPARES(letter,type,format) \
MK61_SOFT_PCS int __aeabi_##letter##cmpeq(type a,type b) {return format::compare(bits(a),bits(b))==0;} \
MK61_SOFT_PCS int __aeabi_##letter##cmplt(type a,type b) {return format::compare(bits(a),bits(b))==-1;} \
MK61_SOFT_PCS int __aeabi_##letter##cmple(type a,type b) {return format::compare(bits(a),bits(b))<=0;} \
MK61_SOFT_PCS int __aeabi_##letter##cmpge(type a,type b) {const int c=format::compare(bits(a),bits(b));return c==0 || c==1;} \
MK61_SOFT_PCS int __aeabi_##letter##cmpgt(type a,type b) {return format::compare(bits(a),bits(b))==1;} \
MK61_SOFT_PCS int __aeabi_##letter##cmpun(type a,type b) {return format::compare(bits(a),bits(b))==2;}
#if !defined(__arm__) && !defined(__thumb__)
COMPARES(d,double,D)
#endif
COMPARES(f,float,S)
#undef COMPARES
#if !defined(__arm__) && !defined(__thumb__)
MK61_SOFT_PCS double __aeabi_i2d(int32_t x) {return real(D::from_integer(x<0?U(0)-U(int64_t(x)):U(x),x<0?D::Sign:0));}
MK61_SOFT_PCS double __aeabi_ui2d(uint32_t x) {return real(D::from_integer(x));}
MK61_SOFT_PCS double __aeabi_l2d(int64_t x) {return real(D::from_integer(integer_magnitude(x),x<0?D::Sign:0));}
MK61_SOFT_PCS double __aeabi_ul2d(U x) {return real(D::from_integer(x));}
#endif
MK61_SOFT_PCS float __aeabi_i2f(int32_t x) {return single(S::from_integer(x<0?U(0)-U(int64_t(x)):U(x),x<0?S::Sign:0));}
MK61_SOFT_PCS float __aeabi_ui2f(uint32_t x) {return single(S::from_integer(x));}
#if defined(__arm__) || defined(__thumb__)
MK61_SOFT_PCS int32_t mk61_m0_d2iz_slow(double x) {return D::signed32(bits(x));}
#else
MK61_SOFT_PCS int32_t __aeabi_d2iz(double x) {return D::signed32(bits(x));}
#endif
#if !((defined(__arm__) || defined(__thumb__)) && defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI)
MK61_SOFT_PCS uint32_t __aeabi_d2uiz(double x) {return D::unsigned32(bits(x));}
#endif
MK61_SOFT_PCS int32_t __aeabi_f2iz(float x) {return S::signed32(bits(x));}
MK61_SOFT_PCS uint32_t __aeabi_f2uiz(float x) {return S::unsigned32(bits(x));}
#if defined(__arm__) || defined(__thumb__)
MK61_SOFT_PCS int64_t mk61_m0_d2lz_slow(double x) {const U a=bits(x),m=D::magnitude_integer(a);return copy<int64_t>(a&D::Sign?U(0)-m:m);}
#else
MK61_SOFT_PCS int64_t __aeabi_d2lz(double x) {const U a=bits(x),m=D::magnitude_integer(a);return copy<int64_t>(a&D::Sign?U(0)-m:m);}
#endif
#if defined(__arm__) || defined(__thumb__)
MK61_SOFT_PCS U mk61_m0_d2ulz_slow(double x) {const U a=bits(x);return a&D::Sign?0:D::magnitude_integer(a);}
#else
MK61_SOFT_PCS U __aeabi_d2ulz(double x) {const U a=bits(x);return a&D::Sign?0:D::magnitude_integer(a);}
#endif
#if defined(__arm__) || defined(__thumb__)
MK61_SOFT_PCS float mk61_m0_d2f_slow(double x) {return single(narrow(bits(x)));}
MK61_SOFT_PCS double mk61_m0_f2d_slow(float x) {return real(extend(bits(x)));}
#else
MK61_SOFT_PCS float __aeabi_d2f(double x) {return single(narrow(bits(x)));}
MK61_SOFT_PCS double __aeabi_f2d(float x) {return real(extend(bits(x)));}
#endif
#if defined(__arm__) || defined(__thumb__)
#include "native_eabi_m0_kernels.inc"
#include "native_eabi_m0_refine.inc"
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
#define MK61_M0_LOG10_TABLE_INCLUDED 1
#include "native_eabi_m0_log10_table.inc"
#endif
#include "native_eabi_m0_log70_center.inc"
#include "native_eabi_m0_log70.inc"
#include "native_eabi_m0_log10.inc"
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
#include "native_eabi_m0_log_subnormal.inc"
#endif
#include "native_eabi_m0_atan_refine.inc"
#include "native_eabi_m0_atan.inc"
#include "native_eabi_m0_asin.inc"
struct Trig192 {U low,middle,high;};
__attribute__((always_inline)) inline Trig192 trig_negate(Trig192 a) {
  a.low=U(0)-a.low;
  a.middle=~a.middle+U(!a.low);
  a.high=~a.high+U(!a.low&&!a.middle);
  return a;
}
__attribute__((always_inline)) inline Trig192 trig_difference(Trig192 a,Trig192 b) {
  const U low=a.low-b.low;
  bool borrow=a.low<b.low;
  const U middle=a.middle-b.middle-U(borrow);
  borrow=a.middle<b.middle || (borrow && a.middle==b.middle);
  return {low,middle,a.high-b.high-U(borrow)};
}
__attribute__((always_inline)) inline U trig_relative(Trig192 a,int &e) {
  U first,second,third;unsigned leading;
  if(a.high) {first=a.high;second=a.middle;third=a.low;leading=0;}
  else if(a.middle) {first=a.middle;second=a.low;third=0;leading=64;}
  else {first=a.low;second=third=0;leading=128;}
  if(!first) {e=-192;return 0;}
  const unsigned shift=clz64(first);leading+=shift;e=1-int(leading);
  const U top=shift?(first<<shift)|(second>>(64-shift)):first;
  const bool sticky=(shift?second<<shift:second)||third;
  return (top>>1)+U((top&1) && (sticky||((top>>1)&1)));
}
__attribute__((optimize("Os"))) static int trig_small_relative(U relative,int e,unsigned flags,double* out) {
  const unsigned op=flags&3,n=(flags>>2)&3;
  const unsigned selected=op==0?(n&1):op==1?((n&1)^1U):0;
  U value;
  if(op==2) {
    const double t=math62_tan_small(relative,e,(flags&32)?D::Sign:0);
    value=bits(n&1?-1.0/t:t)^((flags&16)?D::Sign:0);
  }
  else {
    math62_sincos_small(relative,e,(flags&32)?D::Sign:0,out,1U<<selected);
    const unsigned flip=op==0?((n>>1)&1)^((flags>>4)&1):((n+1)>>1)&1;
    value=bits(out[selected])^(U(flip)<<63);
  }
  out[0]=real(value);return 1;
}
__attribute__((optimize("Os"))) static int trig_small_result(const Trig192* r,unsigned flags,double* out) {
  int e;const U relative=trig_relative(*r,e);
  return e<-99?0:trig_small_relative(relative,e,flags,out);
}
__attribute__((always_inline)) inline U trig_pack192(Trig192 a,U sign,unsigned &leading) {
  if(!(a.low|a.middle|a.high)) {leading=192;return sign;}
  U first,second,third;
  unsigned n;
  if(a.high) {first=a.high;second=a.middle;third=a.low;n=0;}
  else if(a.middle) {first=a.middle;second=a.low;third=0;n=64;}
  else {first=a.low;second=third=0;n=128;}
  const unsigned shift=clz64(first);
  leading=n+shift;
  const U q=shift?(first<<shift)|(second>>(64-shift)):first;
  const bool sticky=(shift?second<<shift:second)||third;
  const uint32_t tail=uint32_t(q)&2047;
  const U rounded=(q>>11)+(tail>1024 || (tail==1024 && (((q>>11)&1)||sticky)));
  return sign+(U(1022-leading)<<52)+rounded;
}
__attribute__((always_inline)) inline Trig192 trig_remainder(U b,uint32_t &n,bool &negative) {
  const U s=(b&D::Fraction)|D::Hidden;
  const int e=int((b>>52)&0x7FFU)-1023;
  const U estimate=wide32(uint32_t(s>>21),0xA2F9836EU);
  n=e==-1?uint32_t(estimate>=(U(1)<<63)):
    uint32_t((estimate+(U(1)<<(62-e)))>>unsigned(63-e));
  U words[3],carry=0;
  for(unsigned i=0;i<3;++i) {
    const U lo=wide32(trig_pi2[2*i],n)+carry;
    const U hi=wide32(trig_pi2[2*i+1],n)+(lo>>32);
    words[i]=(hi<<32)|uint32_t(lo);carry=hi>>32;
  }
  const unsigned shift=unsigned(e+11);
  Trig192 r=trig_difference({0,0,s<<shift},{words[0],words[1],words[2]});
  negative=(r.high>>63)!=0;
  if(negative) r=trig_negate(r);
  return r;
}
__attribute__((always_inline)) inline bool trig_remainder_pair(Trig192 r,U sign,double* output) {
  unsigned leading;
  const U first=trig_pack192(r,sign,leading);
  // Below this residual the original fdlibm cancellation refinements
  // retain the shared implementation's full precision margin.
  if(leading>100) return false;
  output[0]=real(first);
  const U significand=(first&D::Fraction)|D::Hidden;
  const int scale=int((first>>52)&0x7FFU)-1023+139;
  U expanded[3]={0,0,0};
  const unsigned word=unsigned(scale)/64,bit=unsigned(scale)%64;
  expanded[word]=significand<<bit;
  if(word<2 && bit) expanded[word+1]=significand>>(64-bit);
  Trig192 tail=trig_difference(r,{expanded[0],expanded[1],expanded[2]});
  const bool below=(tail.high>>63)!=0;
  if(below) tail=trig_negate(tail);
  output[1]=real(trig_pack192(tail,sign^(below?D::Sign:0),leading));
  return true;
}
__attribute__((optimize("Os"))) int mk61_m0_reduce_pio2(double x,double* output) {
  const U b=bits(x);uint32_t n;bool negative;
  const Trig192 r=trig_remainder(b,n,negative);
  if(!n || !trig_remainder_pair(r,(b&D::Sign)^(negative?D::Sign:0),output)) return 0;
  return b&D::Sign?-int(n):int(n);
}
U trig_fixed(U a) {
  const unsigned raw=unsigned((a>>52)&0x7FFU);
  if(!(a&D::Magnitude)) return 0;
  const int shift=int(raw)-1023+10;
  if(shift<=-54) return 0;
  const U s=(a&D::Fraction)|D::Hidden;
  U q;
  if(shift>=0) q=s<<unsigned(shift);
  else {
    const unsigned right=unsigned(-shift);
    if(right>32) {
      const unsigned n=right-32;
      const uint32_t high=uint32_t(s>>32),half=1U<<(n-1),tail=high&((half<<1)-1);
      q=(high>>n)+(tail>half || (tail==half && (((high>>n)&1)||uint32_t(s))));
    } else {
      const U half=U(1)<<(right-1),tail=s&((half<<1)-1);
      q=(s>>right)+(tail>half || (tail==half && ((s>>right)&1)));
    }
  }
  return a&D::Sign?U(0)-q:q;
}
// cos(h)-1 is below 2^-23. Round it to Q54 before its final product;
// the induced relative error in sin/cos stays below 2^-55.
__attribute__((always_inline)) inline U trig_small_product(U a,U delta) {
  const uint32_t d=uint32_t((delta+128)>>8);
  const U lo=wide32(uint32_t(a),d);
  const U hi=wide32(uint32_t(a>>32),d)+(lo>>32);
  const U rounded=(hi+((U(1)<<21)-1)+U(((hi>>22)&1)||uint32_t(lo)))>>22;
  const int32_t error=int32_t(uint32_t(delta)-(d<<8));
  const int32_t correction=(int32_t(a>>47)*error+16384)>>15;
  return rounded+U(int64_t(correction));
}
__attribute__((optimize("Os"))) void trig_sincos_fixed(U magnitude,U sign,double* out,unsigned mask) {
  const unsigned j=unsigned((magnitude+(U(1)<<51))>>52);
  const U h=magnitude-(U(j)<<52);
  if(!h) {
    if(mask&1) out[0]=mk61_m0_trig_pack(trig_table[j][0],sign);
    if(mask&2) out[1]=mk61_m0_trig_pack(trig_table[j][1],0);
    return;
  }
  const bool negative=(h>>63)!=0;
  const U a=negative?U(0)-h:h;
  const uint32_t t=uint32_t(a>>20); // Q42, |h| <= 1/2048, including endpoints
  const U square=wide32(t,t);
  // Two products recover the square to within 1+2^-22 Q62 units. The omitted
  // low-limb square contributes less than 2^-22 of such a unit.
  const U cross=wide32(t,uint32_t(a)&0xFFFFFU);
  const U z=(square>>22)+(cross>>41)+1;
  const U p=wide32(uint32_t(square),t);
  const uint32_t cube=uint32_t((wide32(uint32_t(square>>32),t)+(p>>32))>>32);
  const uint32_t third=uint32_t(wide32(cube+3,0xAAAAAAABU)>>34);
  const uint32_t fourth=uint32_t(wide32(uint32_t(wide32(cube,t)>>42)+12,0xAAAAAAABU)>>36);
  const U sh=a-third;
  const U ch=((z+1)>>1)-fourth;
  const U s=trig_table[j][0],c=trig_table[j][1];
  if(mask&1) {
    const U correction=mk61_m0_mul_q62(c,sh);
    const U q=s-trig_small_product(s,ch)+(negative?U(0)-correction:correction);
    out[0]=mk61_m0_trig_pack(q,sign);
  }
  if(mask&2) {
    const U correction=mk61_m0_mul_q62(s,sh);
    const U q=c-trig_small_product(c,ch)+(negative?correction:U(0)-correction);
    out[1]=mk61_m0_trig_pack(q,0);
  }
}
__attribute__((optimize("Os"))) void mk61_m0_sincos_reduced(double x,double tail,double* out,unsigned mask) {
  const U xb=bits(x);
  const U primary=((xb&D::Fraction)|D::Hidden)<<unsigned(int((xb>>52)&0x7FFU)-1013);
  const U raw=(xb&D::Sign?U(0)-primary:primary)+trig_fixed(bits(tail));
  const U sign=raw&D::Sign;
  trig_sincos_fixed(sign?U(0)-raw:raw,sign,out,mask);
}
__attribute__((optimize("Os"))) int mk61_m0_trig_medium(double x,double* out,unsigned op) {
  const U b=bits(x);uint32_t n;bool negative;
  const U s=(b&D::Fraction)|D::Hidden;
  const int e=int((b>>52)&0x7FFU)-1023;
  const U estimate=wide32(uint32_t(s>>21),0xA2F9836EU);
  n=e==-1?uint32_t(estimate>=(U(1)<<63)):
    uint32_t((estimate+(U(1)<<(62-e)))>>unsigned(63-e));
  if(!n) return 0;
  // Q95 needs only two wide products and one low product. Truncating pi/2
  // changes the signed remainder by less than n units in its low word.
  // A low word within n of either boundary may straddle a Q62 rounding
  // midpoint; certify the common path and recompute those cases in Q191.
  const U lo=wide32(trig_pi2[3],n);
  const U middle=wide32(trig_pi2[4],n)+(lo>>32);
  const uint32_t top=trig_pi2[5]*n+uint32_t(middle>>32);
  uint32_t low=0U-uint32_t(lo);
  U high=(s<<unsigned(e+11))-((U(top)<<32)|uint32_t(middle))-U(low!=0);
  negative=(high>>63)!=0;
  if(negative) {low=0U-low;high=~high+U(!low);}
  U q=(high>>1)+U((high&1) && (low||((high>>1)&1)));
  if(q<(U(1)<<56)) {
    const unsigned leading=clz64(high);
    if(leading<33) {
      const unsigned shift=33-leading;
      const uint32_t half=1U<<(shift-1),tail=low&((half<<1)-1);
      const uint32_t distance=tail>=half?tail-half:half-tail;
      if(distance>n) {
        // Certify the relative 63-bit rounding against the entire pi/2
        // truncation interval. This avoids the Q191 product for most small
        // residuals while retaining exactly the same normalized guard bits.
        const U truncated=(high<<(leading-1))|(low>>shift);
        const U relative=truncated+U(tail>half || (tail==half && (truncated&1)));
        return trig_small_relative(relative,1-int(leading),
          op|((n&3)<<2)|(unsigned(b>>63)<<4)|(unsigned(negative)<<5),out);
      }
    }
    const Trig192 r=trig_remainder(b,n,negative);
    return trig_small_result(&r,op|((n&3)<<2)|(unsigned(b>>63)<<4)|(unsigned(negative)<<5),out);
  }
  if(low<=n || uint32_t(~low)<=n) {
    const Trig192 r=trig_remainder(b,n,negative);
    q=(r.high>>1)+U((r.high&1) && ((r.low|r.middle)||((r.high>>1)&1)));
    if(q<(U(1)<<56)) {
      return trig_small_result(&r,op|((n&3)<<2)|(unsigned(b>>63)<<4)|(unsigned(negative)<<5),out);
    }
  }
  const unsigned selected=op==0?(n&1):op==1?((n&1)^1U):0;
  trig_sincos_fixed(q,negative?D::Sign:0,out,op==2?3:1U<<selected);
  U value;
  if(op==2) {
    value=bits(n&1?-out[1]/out[0]:out[0]/out[1])^(b&D::Sign);
  } else {
    const unsigned flip=op==0?((n>>1)&1)^unsigned(b>>63):((n+1)>>1)&1;
    value=bits(out[selected])^(U(flip)<<63);
  }
  out[0]=real(value);return 1;
}
#include "native_eabi_m0_trig_checked.inc"
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
#include "native_eabi_m0_trig_large.inc"
#endif
MK61_M0_TRIG_CACHE(mulq62) __attribute__((optimize("Os"))) U mk61_m0_mul_q62(U a,U b) {
  if(!uint32_t(b>>32)) {
    const uint32_t y=uint32_t(b);
    if(!y) return 0;
    const U low=wide32(uint32_t(a),y);
    const U upper=wide32(uint32_t(a>>32),y)+(low>>32);
    const U q=upper>>30;
    const uint32_t tail=uint32_t(upper)&0x3FFFFFFFU;
    return q+(tail>0x20000000U || (tail==0x20000000U && (uint32_t(low)||(q&1))));
  }
  const Product p=multiply(a,b);
  const U q=(p.high<<2)|(p.low>>62);
  const U tail=p.low&((U(1)<<62)-1),half=U(1)<<61;
  return q+(tail>half || (tail==half && (q&1)));
}
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
extern "C" MK61_SOFT_PCS U mk61_m0_exp_endpoint(U,int,unsigned);
#endif
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
extern "C" MK61_SOFT_PCS U mk61_m0_pow_exp_product_flash(U,U);
// Integer floor of the distance from a linear midpoint to its exact
// logarithmic input threshold, in input ulps. The full odd-square and
// odd-cube are exact. The source-bound certificate checks that the fourth
// and higher log terms cannot alter floor(cube/(3*2^(52+negative))).
__attribute__((always_inline)) inline uint32_t exp_tiny_log_floor(uint32_t odd,int e,bool negative) {
  const unsigned q=unsigned(e+55)+2U*unsigned(negative);
  // Here odd^3/(3*2^(52+negative))<1, so its certified floor is0.
  if(odd<65536U) return (odd*odd)>>q;
  const U square=wide32(odd,odd);
  const uint32_t low=uint32_t(square),high=uint32_t(square>>32);
  uint32_t result=(low>>q)|(high<<(32U-q));
  const uint32_t tail=low&((1U<<q)-1U);
  const U cube_low=wide32(low,odd);
  const U cube_high=wide32(high,odd)+(cube_low>>32);
  const uint32_t scaled20=uint32_t(cube_high>>20);
  const uint32_t scaled=scaled20>>unsigned(negative);
  const uint32_t cubic=(scaled*43691U)>>17; // exact /3, scaled<65536
  if(negative) result+=unsigned(tail+cubic>=(1U<<q));
  else result-=unsigned(tail<=cubic);
  return result;
}
// Called only for 2^-54 < |x| < 2^-32, hence s=-e-negative is32..54.
// The exact logarithmic correction is strictly between0 and1048577
// input ulps. Only the affected side of a linear midpoint needs products.
__attribute__((noinline,noipa,section(".m0_exp_tiny"))) static U exp_tiny_rne(U a) {
  const bool negative=bool(a>>63);
  const int e=int((a>>52)&0x7FFU)-1023;
  const unsigned s=unsigned(-e)-unsigned(negative);
  const uint32_t hi=(uint32_t(a>>32)&0xFFFFFU)|0x100000U,lo=uint32_t(a);
  uint32_t retained,distance=0;
  bool up,near=false;
  if(s==32) {
    retained=hi;
    const uint32_t half=0x80000000U;
    up=negative?lo>half:lo>=half;
    distance=negative?lo-half:half-lo;
    near=distance && distance<=1048576U;
  } else {
    const unsigned shift=s-32U;
    const uint32_t tail=hi&((1U<<shift)-1U),half=1U<<(shift-1U);
    retained=hi>>shift;
    if(negative) {
      up=tail>half || (tail==half && lo);
      distance=lo;
      near=tail==half && lo && lo<=1048576U;
    } else {
      up=tail>=half;
      distance=0U-lo;
      near=tail+1U==half && lo>0U-1048577U;
    }
  }
  if(near) {
    const uint32_t threshold=exp_tiny_log_floor((retained<<1)|1U,e,negative);
    up=negative?distance>threshold:distance<=threshold;
  }
  const uint32_t displacement=retained+unsigned(up);
  return negative?UINT64_C(0x3FF0000000000000)-displacement:
                  UINT64_C(0x3FF0000000000000)+displacement;
}
// Private prototype: |x| in[2^-32,2^-11). The correction exp(x)-1-x
// is evaluated in input-ulp Q16, retaining the exact linear significand.
// Source-bound error proof and ARM qualification are required before use.
// Both products require a<2^48,b<2^58. High64 retains six16-bit terms;
// bit48 retains nine. Their wider error intervals are certified below.
// product64 rounds the retained high word; product48 floors its bit48 word.
asm(R"asm(
.syntax unified
.cpu cortex-m0plus
.thumb
.section .m0_exp_small_products,"ax",%progbits
.align 2
.global mk61_m0_exp_small_product64
.type mk61_m0_exp_small_product64,%function
.thumb_func
mk61_m0_exp_small_product64:
 push {r0-r7,lr}
 lsrs r7,r3,#16
 mov r3,sp
 movs r1,#0
 movs r4,#0
 movs r0,#0
 ldrh r5,[r3,#0]
 muls r5,r7
 lsrs r6,r5,#16
 lsls r5,#16
 adds r4,r5
 adcs r0,r6
 ldrh r5,[r3,#2]
 ldrh r6,[r3,#12]
 muls r5,r6
 lsrs r6,r5,#16
 lsls r5,#16
 adds r4,r5
 adcs r0,r6
 ldrh r5,[r3,#4]
 ldrh r6,[r3,#10]
 muls r5,r6
 lsrs r6,r5,#16
 lsls r5,#16
 adds r4,r5
 adcs r0,r6
 lsls r4,#1
 adcs r0,r1
 ldrh r5,[r3,#2]
 muls r5,r7
 adds r0,r5
 movs r4,#0
 ldrh r5,[r3,#4]
 ldrh r6,[r3,#12]
 muls r5,r6
 adds r0,r5
 adcs r1,r4
 ldrh r5,[r3,#4]
 muls r5,r7
 lsrs r6,r5,#16
 lsls r5,#16
 adds r0,r5
 adcs r1,r6
 add sp,#16
 pop {r4-r7,pc}
.size mk61_m0_exp_small_product64,.-mk61_m0_exp_small_product64
.global mk61_m0_exp_small_product48
.type mk61_m0_exp_small_product48,%function
.thumb_func
mk61_m0_exp_small_product48:
 push {r0-r7,lr}
 lsrs r7,r3,#16
 mov r3,sp
 movs r1,#0
 ldrh r4,[r3,#0]
 ldrh r6,[r3,#12]
 muls r4,r6
 movs r0,#0
 ldrh r5,[r3,#2]
 ldrh r6,[r3,#10]
 muls r5,r6
 adds r4,r5
 adcs r0,r1
 ldrh r5,[r3,#4]
 ldrh r6,[r3,#8]
 muls r5,r6
 adds r4,r5
 adcs r0,r1
 ldrh r5,[r3,#0]
 muls r5,r7
 lsrs r6,r5,#16
 lsls r5,#16
 adds r4,r5
 adcs r0,r6
 ldrh r5,[r3,#2]
 ldrh r6,[r3,#12]
 muls r5,r6
 lsrs r6,r5,#16
 lsls r5,#16
 adds r4,r5
 adcs r0,r6
 ldrh r5,[r3,#4]
 ldrh r6,[r3,#10]
 muls r5,r6
 lsrs r6,r5,#16
 lsls r5,#16
 adds r4,r5
 adcs r0,r6
 mov r2,r4
 ldrh r5,[r3,#2]
 muls r5,r7
 adds r0,r5
 movs r4,#0
 ldrh r5,[r3,#4]
 ldrh r6,[r3,#12]
 muls r5,r6
 adds r0,r5
 adcs r1,r4
 ldrh r5,[r3,#4]
 muls r5,r7
 lsrs r6,r5,#16
 lsls r5,#16
 adds r0,r5
 adcs r1,r6
 lsrs r4,r0,#16
 lsls r1,#16
 orrs r1,r4
 lsls r0,#16
 lsrs r2,#16
 orrs r0,r2
 add sp,#16
 pop {r4-r7,pc}
.size mk61_m0_exp_small_product48,.-mk61_m0_exp_small_product48

.align 2
.global mk61_m0_exp_small_square48
.type mk61_m0_exp_small_square48,%function
.thumb_func
mk61_m0_exp_small_square48:
 push {r0-r7,lr}
 uxth r2,r1
 lsrs r1,r0,#16
 uxth r0,r0
 movs r3,#0
 mov r4,r0
 muls r4,r0
 mov r6,r0
 muls r6,r1
 lsrs r4,#16
 lsrs r7,r6,#15
 lsls r6,#17
 lsrs r6,#16
 adds r4,r6
 lsrs r4,#16
 adds r7,r4
 mov r4,r1
 muls r4,r1
 movs r5,#0
 adds r4,r7
 adcs r5,r3
 mov r6,r0
 muls r6,r2
 lsrs r7,r6,#31
 lsls r6,#1
 adds r4,r6
 adcs r5,r7
 mov r6,r1
 muls r6,r2
 lsrs r7,r6,#15
 lsls r6,#17
 adds r4,r6
 adcs r5,r7
 muls r2,r2
 adds r5,r2
 ldr r2,[sp,#8]
 subs r2,#32
 mov r0,r4
 mov r1,r5
 lsrs r0,r0,r2
 lsrs r1,r1,r2
 rsbs r2,#0
 adds r2,#32
 lsls r5,r5,r2
 orrs r0,r5
 add sp,#16
 pop {r4-r7,pc}
.size mk61_m0_exp_small_square48,.-mk61_m0_exp_small_square48
)asm");
extern "C" MK61_SOFT_PCS U mk61_m0_exp_small_product64(U,U);
extern "C" MK61_SOFT_PCS U mk61_m0_exp_small_product48(U,U);
extern "C" MK61_SOFT_PCS U mk61_m0_exp_small_square48(U,unsigned);
__attribute__((noinline,noipa,optimize("Os"),section(".m0_exp_small")))
static U exp_small_rne(U a) {
  const bool negative=bool(a>>63);
  const int e=int((a>>52)&0x7FFU)-1023;
  const uint32_t lo=uint32_t(a),hi=(uint32_t(a>>32)&0xFFFFFU)|0x100000U;
  const U m=(U(hi)<<32)|lo;
  const unsigned right=unsigned(-e-12);
  const U x64=right?((U(hi>>right)<<32)|((lo>>right)|(hi<<(32-right)))):m;
  U coefficient=UINT64_C(11728124029611);
  if(e==-12) {
    const U term=mk61_m0_exp_small_product64(UINT64_C(2345624805922),x64);
    coefficient=negative?coefficient-term:coefficient+term;
  }
  const U term2=mk61_m0_exp_small_product64(coefficient,x64);
  coefficient=negative?UINT64_C(46912496118443)-term2:
                       UINT64_C(46912496118443)+term2;
  const U tail=mk61_m0_exp_small_product64(coefficient,x64);
  const U square=mk61_m0_exp_small_square48(m>>5,unsigned(26-e));
  const U correction_tail=mk61_m0_exp_small_product48(tail,square);
  U correction=negative?(square>>1)-correction_tail:
                         (square>>1)+correction_tail;
  uint32_t fifth_error=0;
  if(e<=-13) {
    if(e>-15) {
      const uint32_t c=hi>>15,square6=c*c,fourth6=square6*square6,fifth6=fourth6*c;
      const unsigned s=unsigned(-4*e-48);
      const uint32_t u=fifth6>>(s+8),h=u>>16,v=(u&65535U)+h;
      const uint32_t q=(v*4369U)>>16;
      const uint32_t fifth=q+unsigned(v-15U*q>=15U)+h*4369U;
      correction=negative?correction-fifth:correction+fifth;
      fifth_error=(21174U>>s)+2U;
    } else fifth_error=e==-15?69U:e==-16?5U:1U;
  }
  const uint32_t extra=e>=-22?1U<<unsigned(e+22):0U;
  const uint32_t error=4U*uint32_t(square>>48)+32U+extra+fifth_error;
  const unsigned shift=unsigned(16-e)-unsigned(negative);
  const U bottom=m<<16;
  const U adjusted=negative?bottom-correction:bottom+correction;
  uint32_t high=(hi>>16)+(negative?0U-unsigned(bottom<correction):unsigned(adjusted<bottom));
  uint32_t low=uint32_t(adjusted),middle=uint32_t(adjusted>>32),qlo,qhi;
  bool unsafe;
  if(shift<32) {
    const uint32_t before=low;low+=1U<<(shift-1);
    const uint32_t old=middle;middle+=unsigned(low<before);high+=unsigned(middle<old);
    unsafe=((low+error)&((1U<<shift)-1U))<=2U*error;
    qlo=(low>>shift)|(middle<<(32-shift));
    qhi=(middle>>shift)|(high<<(32-shift));
  } else {
    const unsigned d=shift-32;
    if(d) {
      const uint32_t old=middle;middle+=1U<<(d-1);high+=unsigned(middle<old);
      const uint32_t expanded=low+error;
      const uint32_t remhigh=(middle+unsigned(expanded<low))&((1U<<d)-1U);
      unsafe=!remhigh && expanded<=2U*error;
      qlo=(middle>>d)|(high<<(32-d));qhi=high>>d;
    } else {
      const uint32_t before=low;low+=0x80000000U;
      const uint32_t old=middle;middle+=unsigned(low<before);high+=unsigned(middle<old);
      unsafe=uint32_t(low+error)<=2U*error;qlo=middle;qhi=high;
    }
  }
  if(unsafe) return bits(exp_refine(real(a),0));
  const U displacement=(U(qhi)<<32)|qlo;
  return negative?UINT64_C(0x3FF0000000000000)-displacement:
                  UINT64_C(0x3FF0000000000000)+displacement;
}

#endif
// On ARMv6-M, -O3 expands wide products into substantially more spills than
// -Os. Keep this kernel's measured register allocation in release builds.
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
extern "C" __attribute__((optimize("Os"),noinline,noipa,cold))
MK61_SOFT_PCS double mk61_m0_exp_positive_dispatch(double,uint32_t);
#endif
MK61_M0_EXP_CORE __attribute__((optimize("Os"))) MK61_SOFT_PCS double mk61_m0_exp(double x) {
  const U a=bits(x),m=a&D::Magnitude;
  if(m>=UINT64_C(0x4090000000000000)) {
    if(m>D::Infinity) return real(a|D::Quiet);
    return real(a&D::Sign?0:D::Infinity);
  }
  // At +/-2^-54 the exact exponential is still inside 1's RNE cell.
  // Larger tiny inputs must retain x*x/2: 1+x alone misrounds midpoint x.
  if(m<=UINT64_C(0x3C90000000000000)) return 1.0;
  const int e=int(m>>52)-1023;
  const U significand=(m&D::Fraction)|D::Hidden;
  uint32_t n=0;
  if(e>=-11) {
    const U p=wide32(uint32_t(significand>>21),0xB8AA3B29U);
    // -11 <= e <= 9: the rounding bit is in p's upper word. Round that
    // word directly, avoiding two variable 64-bit shifts on ARMv6-M.
    n=((uint32_t(p>>32)>>unsigned(20-e))+1U)>>1;
  }
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  else if(e<-32) {
    return real(exp_tiny_rne(a));
  } else if(e<-11) {
    return real(exp_small_rne(a));
  }
#endif
  const int shift=e+12;
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  // The preceding RP exits prove -11<=e<=9, hence 1<=shift<=21.
  // Reconstruct exactly the low64 bits with defined 32-bit limb shifts.
  const unsigned amount=unsigned(shift);
  const uint32_t scaled_low=uint32_t(significand)<<amount;
  const uint32_t scaled_high=(uint32_t(significand>>32)<<amount)|
                             (uint32_t(significand)>>(32U-amount));
  const U scaled=(U(scaled_high)<<32)|scaled_low;
#else
  const U scaled=shift<0?significand>>unsigned(-shift):significand<<unsigned(shift);
#endif
  const U reduction=wide32(uint32_t(exp_step_high),n)+
    (U(uint32_t(exp_step_high>>32)*n)<<32);
  U r=scaled-reduction-uint32_t(wide32(n,exp_step_low)>>32);
  int k=int(n);
  if(a&D::Sign) {r=U(0)-r;k=-k;}
  const bool negative=(r>>63)!=0;
  const U magnitude=negative?U(0)-r:r;
  // Protect the polynomial's certified domain independently of the segment
  // estimate. Opposing truncations keep split reduction error below
  // 1.001 Q64 units; certify_m0_exp_fast.py checks the complete interval.
  if(magnitude>UINT64_C(12912720851596686)) return mk61_m0_cr_exp(x); // 0.0007
  const U z=exp_high_square(magnitude)&((U(1)<<44)-1);
  const uint32_t t=uint32_t((magnitude+(1U<<21))>>22); // |r| in Q42
  // Evaluate r/6+r*r/24+r*r*r/120 in Q44; it still fits int32.
  // The combined coefficient error is <3 Q44 units. Including the fifth
  // term costs fewer wide products than the old Q40 fourth-degree path.
  const uint32_t linear=uint32_t((wide32(t,0xAAAAAAABU)+(U(1)<<31))>>32);
  const uint32_t square=uint32_t((z+(1U<<22))>>23);
  const uint32_t quadratic=uint32_t(wide32(square+1,0xAAAAAAABU)>>33);
  const uint32_t cubic=(uint32_t(z>>32)*(t>>16)+(1U<<16))>>17;
  const uint32_t fifth=((cubic+7)*2185U)>>15;
  const int32_t tail=(negative?-int32_t(linear):int32_t(linear))+int32_t(quadratic)+
    (negative?-int32_t(fifth):int32_t(fifth));
  const uint32_t tail_magnitude=tail<0?uint32_t(-tail):uint32_t(tail);
  const U p=wide32(uint32_t(z),tail_magnitude);
  const U c=(wide32(uint32_t(z>>32),tail_magnitude)+(p>>32))>>12;
  const U delta=r+(z>>1)+(tail<0?U(0)-c:c);
  const unsigned index=unsigned(k)&511U;
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  // index is k modulo512 in0..511: this is exact floor division.
  k>>=9;
#else
  k=(k-int(index))/512;
#endif
  U q=exp_table[index];
  const bool below=(delta>>63)!=0;
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  const U displacement=below?U(0)-delta:delta;
  // Row zero is exactly2^62. The rounded high product is a shift;
  // all three omitted partial products are identically zero.
  const U correction=index?mk61_m0_pow_exp_product_flash(q,displacement):
                           (displacement+2U)>>2;
  register uint32_t product_fraction __asm__("r12");
  // Private extra return inr12. This zero-byte marker binds the C++
  // value definition to the required post-build call-to-marker audit.
  __asm__ volatile(".global mk61_m0_exp_fraction_capture\n"
                   ".hidden mk61_m0_exp_fraction_capture\n"
                   "mk61_m0_exp_fraction_capture:"
                   : "=r"(product_fraction));
  unsigned error=4;
#else
  const U correction=exp_high_product(q,below?U(0)-delta:delta)+1;
  unsigned error=5;
#endif
  q=below?q-correction:q+correction;
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  // The certified polynomial/table/product bounds prove0<q<2^63.
  if(!(uint32_t(q>>32)&0x40000000U)) {
#else
  if(q<(U(1)<<62)) {
#endif
    q<<=1;--k;
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
    error=6;
#else
    error*=2;
#endif
  }
  if(k>=-1022 && k<=1023) {
    // The complete interval [q-error,q+error] must lie in one rounding
    // cell. Ambiguous results are evaluated by the correctly rounded path.
    const uint32_t tail=uint32_t(q)&1023U;
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
    const unsigned guard=error-1U;
    if(uint32_t(tail-(512U-guard))<=2U*guard) {
      const uint32_t distance=tail>512U?tail-512U:512U-tail;
      bool safe=false;
      if(error==4U && distance>=2U) {
        const unsigned i=index;
        const int32_t delta32=int32_t(refine_exp_table[i][0]);
        if(distance==3U)
          safe=tail>512U?delta32>=-0x58000000:delta32<=0x58000000;
        if(!safe) {
          // The original unnormalized table value A is strictly below
          // (floor(q/2^48)+24)*2^48. Its reduction/polynomial error
          // is <(275/64)*A/2^64 Q62 units. The129/256 remainder covers
          // the product, Q94 table and bias cross-term uncertainties.
          const uint32_t top=uint32_t(q>>48)+24U;
          const uint32_t bound=((top*275U+16383U)>>14)+129U;
          const int32_t bias=delta32>>24;
          const int32_t margin=int32_t(distance<<8)+(tail>512U?bias:-bias-1);
          safe=margin>int32_t(bound);
        }
      }
      if(!safe && error==4U && tail<=512U && !(a&D::Sign) && below) {
        // Directed polynomial/reduction upper bound, in1/256 Q64 units.
        // The retained product fraction makes its rounding error explicit.
        const uint32_t head=1U-uint32_t(delta>>32);
        const uint32_t g=(head+1023U)>>10;
        const uint32_t curvature=(3U*g*g+65535U)>>16;
        const uint32_t f=(n*exp_step_low)>>24;
        const uint32_t delta_upper=257U+curvature-(f?f-1U:0U);
        const uint32_t top=uint32_t(q>>48)+24U;
        const uint32_t effect=(delta_upper*top+65535U)>>16;
        const int32_t bias=int32_t(refine_exp_table[index][0])>>24;
        const int32_t product_upper=int32_t((product_fraction>>31)<<8)-
                                    int32_t(product_fraction>>24);
        // This is a strict upper bound: equality still excludes the
        // midpoint at q+(512-tail), including the exact tail512 case.
        safe=int32_t(effect)+bias+product_upper+2<=int32_t(distance<<8);
      }
      if(!safe) return mk61_m0_exp_positive_dispatch(x,n);
    }
#else
    if(uint32_t(tail-(512U-error))<=2*error) return exp_refine(x,n);
#endif
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
    // Every accepted interval is strictly on one side of its midpoint.
    return real((U(k+1022)<<52)+(q>>10)+U(tail>512U));
#else
    const U rounded=(q+511+((q>>10)&1))>>10;
    return real((U(k+1022)<<52)+rounded);
#endif
  }
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  const U endpoint=mk61_m0_exp_endpoint(q,k,error);
  if(endpoint!=(D::Infinity|D::Quiet)) return real(endpoint);
#endif
  return mk61_m0_cr_exp(x);
}
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
// Strict directed upper bound for positive x and nonnegative displacement.
extern "C" __attribute__((optimize("Os"),noinline,noipa,cold,used,section(".m0_exp_positive_upper")))
MK61_SOFT_PCS unsigned mk61_m0_exp_positive_upper(uint32_t qhead,uint32_t dhi,uint32_t n,uint32_t fraction,uint32_t distance) {
  const uint32_t g=(dhi+1024U)>>10;
  const uint32_t curvature=(3U*g*g+65535U)>>16;
  const uint32_t f=(n*exp_step_low)>>24;
  const uint32_t delta_upper=513U+curvature-(f?f-1U:0U);
  const uint32_t effect=(delta_upper*(qhead+1U)+65535U)>>16;
  const int32_t bias=int32_t(refine_exp_table[n&511U][0])>>24;
  const int32_t product_upper=int32_t(fraction>>24)-int32_t((fraction>>31)<<8)+2;
  return int32_t(effect)+bias+product_upper+2<=int32_t(distance<<8);
}
#endif
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
// Private entry: only the audited mk61_m0_exp refinement call may enter.
// Actual caller binding: q=R7:R6, delta_high=SP28, k=SP8, retainedF=R12
// on positive-displacement paths; x=R1:R0 and n=R2 use normal AAPCS.
__asm__(R"ASM(
.pushsection .m0_exp_positive_dispatch,"ax",%progbits
.syntax unified
.cpu cortex-m0plus
.thumb
.balign 4
.global mk61_m0_exp_positive_dispatch
.hidden mk61_m0_exp_positive_dispatch
.type mk61_m0_exp_positive_dispatch,%function
.thumb_func
mk61_m0_exp_positive_dispatch:
 cmp r1,#0
 bmi .Lexp_pos_negative_input
 lsls r3,r2,#23
 beq .Lexp_pos_row0
.Lexp_pos_general:
 ldr r3,[sp,#28]
 cmp r3,#0
 bmi .Lexp_pos_tail
 push {r0-r2,r4-r7,lr}
 sub sp,#8
 mov r1,r3
 ldr r0,[sp,#28]
 lsls r0,r0,#22
 lsrs r0,r0,#22
 movs r4,#128
 lsls r4,r4,#2
 subs r4,r4,r0
 cmp r4,#3
 bhi .Lexp_pos_restore
 str r4,[sp,#0]
 ldr r0,[sp,#32]
 lsrs r0,r0,#16
 mov r3,r12
 bl mk61_m0_exp_positive_upper
 cmp r0,#0
 beq .Lexp_pos_restore
 ldr r0,[sp,#28]
 ldr r1,[sp,#32]
 lsrs r0,r0,#10
 lsls r3,r1,#22
 orrs r0,r3
 lsrs r1,r1,#10
 ldr r3,[sp,#48]
 ldr r4,=1022
 adds r3,r3,r4
 lsls r3,r3,#20
 adds r1,r1,r3
 add sp,#20
 pop {r4-r7,pc}
.Lexp_pos_restore:
 add sp,#8
 pop {r0-r2,r4-r7}
 pop {r3}
 mov lr,r3
.Lexp_pos_tail:
 ldr r3,=exp_refine
 bx r3
.Lexp_pos_row0:
 ldr r3,[sp,#28]
 lsrs r3,r3,#21
 bne .Lexp_pos_row0_slow
 lsls r3,r6,#22
 bmi .Lexp_pos_row0_slow
 mov r0,r6
 mov r1,r7
 lsrs r0,r0,#10
 lsls r3,r1,#22
 orrs r0,r3
 lsrs r1,r1,#10
 ldr r3,[sp,#8]
 ldr r2,=1022
 adds r3,r3,r2
 lsls r3,r3,#20
 adds r1,r1,r3
 bx lr
.Lexp_pos_row0_slow:
 ldr r3,[sp,#28]
 cmp r3,#0
 bmi .Lexp_row0_normalized
 movs r3,#128
 lsls r3,r3,#23
 mov r12,r3
 b .Lexp_pos_general
.Lexp_pos_negative_input:
 lsls r3,r2,#23
 bne .Lexp_pos_tail
 ldr r3,[sp,#28]
 cmp r3,#0
 bpl .Lexp_pos_tail
.Lexp_row0_normalized:
 adds r3,r6,#4
 lsls r3,r3,#29
 bne .Lexp_row0_small
.Lexp_row0_pack:
 mov r0,r6
 mov r1,r7
 movs r2,#0
 movs r3,#128
 lsls r3,r3,#2
 adds r0,r0,r3
 adcs r1,r2
 lsrs r0,r0,#10
 lsls r3,r1,#22
 orrs r0,r3
 lsrs r1,r1,#10
 ldr r3,[sp,#8]
 ldr r2,=1022
 adds r3,r3,r2
 lsls r3,r3,#20
 adds r1,r1,r3
 bx lr
.Lexp_row0_small:
 adds r3,r6,#2
 lsls r3,r3,#30
 bne .Lexp_row0_midpoint
 ldr r3,[sp,#28]
 adds r3,#1
 bne .Lexp_pos_tail
 ldr r3,[sp,#24]
 cmp r3,#2
 blo .Lexp_pos_tail
 b .Lexp_row0_pack
.Lexp_row0_midpoint:
 ldr r3,[sp,#28]
 adds r3,#1
 bne .Lexp_pos_tail
 ldr r3,[sp,#24]
 adds r3,#2
 lsls r3,r3,#30
 bne .Lexp_pos_tail
 b .Lexp_row0_pack
 .ltorg
.size mk61_m0_exp_positive_dispatch,.-mk61_m0_exp_positive_dispatch
.popsection
)ASM");
#endif
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
// The existing Q62 interval already encloses exp(x), including gradual
// underflow. Round its entire interval to the uniform subnormal grid.
extern "C" __attribute__((optimize("Os"),noinline,noipa,cold,section(".m0_exp_endpoints")))
MK61_SOFT_PCS U mk61_m0_exp_endpoint(U q,int k,unsigned error) {
  const U decline=D::Infinity|D::Quiet;
  if(k>1023) {
    // At binade1024 the overflow midpoint is Q62(2^62-256).
    if(k>1024 || q-(U(1)<<62)+256>error) return D::Infinity;
    return decline;
  }
  if(k>=-1022) return decline;
  if(k<-1075) {
    if(k<-1076 || ((U(1)<<63)-q>error && q<(U(1)<<63))) return 0;
    return decline;
  }
  const unsigned shift=unsigned(-k-1012); //11..63
  const uint32_t lo=uint32_t(q),hi=uint32_t(q>>32);
  U retained,tail,half;
  if(shift<32) {
    const uint32_t mask=(1U<<shift)-1;
    tail=lo&mask;half=1U<<(shift-1);
    retained=(U(hi>>shift)<<32)|(lo>>shift)|(hi<<(32-shift));
  } else {
    const unsigned s=shift-32;
    const uint32_t mask=s?(1U<<s)-1:0;
    tail=(U(hi&mask)<<32)|lo;
    half=s?U(1U<<(s-1))<<32:U(1U<<31);
    retained=s?hi>>s:hi;
  }
  const U distance=tail>half?tail-half:half-tail;
  if(distance<=error) return decline;
  return retained+U(tail>half);
}
#endif
#include "native_eabi_m0_pow_fast.inc"
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
asm(".global mk61_m0_pow_negative_integer_dispatch\n.hidden mk61_m0_pow_negative_integer_dispatch\n"
    ".thumb_set mk61_m0_pow_negative_integer_dispatch,pow_negative_integer\n"
    ".global mk61_m0_pow_positive_checked_dispatch\n.hidden mk61_m0_pow_positive_checked_dispatch\n"
    ".thumb_set mk61_m0_pow_positive_checked_dispatch,pow_positive_checked\n"
    ".global mk61_m0_pow_near_one_binomial_dispatch\n.hidden mk61_m0_pow_near_one_binomial_dispatch\n"
    ".thumb_set mk61_m0_pow_near_one_binomial_dispatch,pow_near_one_binomial\n"
    ".global mk61_m0_pow_rsqrt_boundary\n.hidden mk61_m0_pow_rsqrt_boundary\n"
    ".thumb_set mk61_m0_pow_rsqrt_boundary,pow_rsqrt_boundary\n");
#endif
#include "native_eabi_m0_pow_ordinary.inc"

MK61_SOFT_PCS double mk61_m0_sqrt_slow(double x) {
  const U a=bits(x),m=a&D::Magnitude;
  if(!m) return x;
  if(m>=D::Infinity) return m==D::Infinity && !(a&D::Sign)?x:real(a|D::Infinity|D::Quiet);
  if(a&D::Sign) return real(D::Infinity|D::Quiet);
  int e;const U s=D::normalize(a,e);const unsigned odd=unsigned(e)&1U;
  const U root=bits(mk61_m0_sqrt(real((s&D::Fraction)|(U(D::Bias+odd)<<52))));
  return real(root-(U(-(e-int(odd))/2)<<52));
}
#endif
#if !defined(__arm__) && !defined(__thumb__)
MK61_SOFT_PCS float mk61_m0_sqrtf(float x) {return single(sqrt_single(bits(x)));}
#endif
MK61_SOFT_PCS U __aeabi_lmul(U a,U b) {
  return low_product(a,b);
}
int __clzsi2(uint32_t x) {return int(clz32(x));}
int __clzdi2(U x) {return int(clz64(x));}
void mk61_m0_divmod64(U n,U d,mk61_eabi_divmod* result) {
  if(!d) {*result={n?UINT64_MAX:0,0};return;}
  U q=0;
  if(n>=d) {
    unsigned shift=clz64(d)-clz64(n);U divisor=d<<shift;
    do {
      if(n>=divisor) {n-=divisor;q|=U(1)<<shift;}
      divisor>>=1;
    } while(shift--);
  }
  *result={q,n};
}
// The generic ARMv6-M fallback is useful outside RP2040 as well. PicoCalc
// keeps the Pico SDK's interrupt-safe SIO wrappers for integer division.
U mk61_m0_udiv32(uint32_t n,uint32_t d) {
  if(!d) return n?UINT32_MAX:0;
  uint32_t q=0;
  if(n>=d) {
    unsigned shift=clz32(d)-clz32(n);uint32_t divisor=d<<shift;
    do {if(n>=divisor) {n-=divisor;q|=1U<<shift;}divisor>>=1;} while(shift--);
  }
  return (U(n)<<32)|q;
}
U mk61_m0_sdiv32(int32_t n,int32_t d) {
  if(!d) return n<0?0x80000000U:n?0x7FFFFFFFU:0;
  const uint32_t un=uint32_t(n),ud=uint32_t(d);
  const U qr=mk61_m0_udiv32(n<0?0U-un:un,d<0?0U-ud:ud);
  uint32_t q=uint32_t(qr),r=uint32_t(qr>>32);
  if((n<0)!=(d<0)) q=0U-q;
  if(n<0) r=0U-r;
  return (U(r)<<32)|q;
}
void mk61_m0_sdivmod64(U n,U d,mk61_eabi_divmod* result) {
  const bool negative_n=(n>>63)!=0,negative_d=(d>>63)!=0;
  if(!d) {*result={negative_n?U(1)<<63:n?(U(1)<<63)-1:0,0};return;}
  mk61_m0_divmod64(negative_n?U(0)-n:n,negative_d?U(0)-d:d,result);
  if(negative_n!=negative_d) result->quotient=U(0)-result->quotient;
  if(negative_n) result->remainder=U(0)-result->remainder;
}
}
#endif

// Share the checked native entry points without an extra RP2040 forwarding call.
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI && (defined(__arm__) || defined(__thumb__))
__asm__(
  ".global _ZN12compact_math4atanEd\n"
  ".thumb_set _ZN12compact_math4atanEd,mk61_m0_atan\n"
  ".global _ZN12compact_math4asinEd\n"
  ".thumb_set _ZN12compact_math4asinEd,mk61_m0_asin\n"
  ".global _ZN12compact_math4acosEd\n"
  ".thumb_set _ZN12compact_math4acosEd,mk61_m0_acos\n"
  ".global _ZN12compact_math2lnEd\n"
  ".thumb_set _ZN12compact_math2lnEd,mk61_m0_ln\n"
  ".global _ZN12compact_math5log10Ed\n"
  ".thumb_set _ZN12compact_math5log10Ed,mk61_m0_log10\n"
  ".global _ZN12compact_math3expEd\n"
  ".thumb_set _ZN12compact_math3expEd,mk61_m0_exp\n"
);
#endif
