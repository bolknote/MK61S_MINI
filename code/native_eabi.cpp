// Narrow nearest-even IEEE binary64 and unsigned division for Cortex-M4.
// Integer algorithms; no floating arithmetic, heap, errno or fenv side effects.
#include "native_eabi.hpp"
#if MK61_USE_NATIVE_EABI
#include <float.h>
static_assert(sizeof(double) == 8 && DBL_MANT_DIG == 53 && FLT_MANT_DIG == 24,
              "owned EABI requires IEEE binary64/binary32");
#define EABI_INLINE __attribute__((always_inline)) inline
namespace native_eabi {
using U64 = uint64_t;
constexpr U64 Sign = UINT64_C(0x8000000000000000);
constexpr U64 Fraction = UINT64_C(0x000FFFFFFFFFFFFF);
constexpr U64 Infinity = UINT64_C(0x7FF0000000000000);
constexpr U64 Quiet = UINT64_C(0x0008000000000000);
constexpr U64 Magnitude = ~Sign;
EABI_INLINE U64 bits(double x) { U64 u; __builtin_memcpy(&u, &x, 8); return u; }
EABI_INLINE double value(U64 u) { double x; __builtin_memcpy(&x, &u, 8); return x; }
EABI_INLINE uint32_t sign_high(U64 u) { return uint32_t(u >> 32) & 0x80000000U; }
EABI_INLINE U64 sign_bits(uint32_t s) { return U64(s) << 32; }
EABI_INLINE U64 quiet(U64 a, U64 b) {
  return ((a & Magnitude) > Infinity ? a : b) | Quiet;
}
EABI_INLINE U64 normalized(U64 b, int& exponent) {
  const unsigned raw = unsigned((b >> 52) & 0x7FFU);
  U64 sig = b & Fraction;
  if(raw) { exponent = int(raw)-1023; return sig | (UINT64_C(1) << 52); }
  const unsigned shift = unsigned(__builtin_clzll(sig)-11);
  exponent = -1022-int(shift);
  return sig << shift;
}
struct Product { U64 high, low; };
EABI_INLINE Product multiply(U64 a, U64 b) {
  const uint32_t a0=uint32_t(a), a1=uint32_t(a>>32), b0=uint32_t(b), b1=uint32_t(b>>32);
  const U64 p0=U64(a0)*b0;
  const U64 p1=U64(a1)*b0+(p0>>32);
  const U64 p2=U64(a0)*b1+uint32_t(p1);
  return {U64(a1)*b1+(p1>>32)+(p2>>32), (p2<<32)|uint32_t(p0)};
}
EABI_INLINE bool greater(Product a, Product b) {
  return a.high>b.high || (a.high==b.high && a.low>b.low);
}
EABI_INLINE Product plus(Product p, U64 b) {
  const U64 low=p.low+b; return {p.high+(low<p.low),low};
}
EABI_INLINE Product minus(Product p, U64 b) {
  const U64 low=p.low-b; return {p.high-(p.low<b),low};
}
EABI_INLINE U64 shift63(Product p) { return (p.high<<1)|(p.low>>63); }
// Called only for a finite normal power-of-two divisor. Keeping uncommon
// subnormal packing separate avoids spilling the hot reciprocal state.
U64 scale_power2(U64 a,U64 b) {
  const U64 ma=a&Magnitude;const uint32_t sign=sign_high(a^b);
  if(ma>Infinity) return a|Quiet;
  if(ma==Infinity || !ma) return sign_bits(sign)|ma;
  int ea;const U64 sa=normalized(a,ea);
  const int exponent=ea-(int((b>>52)&0x7FF)-1023);
  if(exponent>1023) return sign_bits(sign)|Infinity;
  if(exponent>=-1022) return sign_bits(sign)|(U64(exponent+1023)<<52)|(sa&Fraction);
  const unsigned shift=unsigned(-1022-exponent);
  if(shift>53) return sign_bits(sign);
  const U64 half=UINT64_C(1)<<(shift-1),tail=sa&((half<<1)-1),q=sa>>shift;
  return sign_bits(sign)|(q+(tail>half || (tail==half && (q&1))));
}
U64 div(U64 a, U64 b) {
  const U64 ma=a&Magnitude, mb=b&Magnitude;
  const uint32_t sign=sign_high(a^b);
  if(ma>Infinity || mb>Infinity) return quiet(a,b);
  if((ma==Infinity && mb==Infinity) || (!ma && !mb)) return Infinity|Quiet;
  if(ma==Infinity || !mb) return sign_bits(sign)|Infinity;
  if(!ma || mb==Infinity) return sign_bits(sign);
  int ea,eb;U64 sa=normalized(a,ea);const U64 sb=normalized(b,eb);
  int exponent=ea-eb;
  if(sa<sb) {sa<<=1;--exponent;}
  // One native UDIV yields >=15 useful reciprocal bits. Two Q63 Newton
  // steps give >=60: sufficient for a quotient estimate within one unit.
  // Exact 106-bit products/remainder below decide every final rounding bit.
  U64 reciprocal=U64(UINT32_MAX/uint32_t(sb>>37))<<46;
  const U64 denominator=sb<<11, one=UINT64_C(1)<<63;
  for(unsigned i=0;i<2;++i) {
    const U64 p=shift63(multiply(denominator,reciprocal));
    const bool subtract=p>one;
    const U64 error=subtract?p-one:one-p;
    const U64 correction=shift63(multiply(reciprocal,error));
    reciprocal=subtract?reciprocal-correction:reciprocal+correction;
  }
  U64 q=shift63(multiply(sa,reciprocal));
  const Product numerator={sa>>12,sa<<52};
  Product product=multiply(q,sb);
  while(greater(product,numerator)) {--q;product=minus(product,sb);}
  while(!greater(plus(product,sb),numerator)) {++q;product=plus(product,sb);}
  const U64 remainder=numerator.low-product.low;
  if(exponent < -1022) {
    const unsigned shift=unsigned(-1022-exponent);
    if(shift>53) return sign_bits(sign);
    const U64 half=UINT64_C(1)<<(shift-1), tail=q&((half<<1)-1), integer=q>>shift;
    q=integer+(tail>half || (tail==half && (remainder || (integer&1))));
    return sign_bits(sign)|q;
  }
  if(exponent>1023) return sign_bits(sign)|Infinity;
  q+=(remainder+remainder>sb || (remainder+remainder==sb && (q&1)));
  if(q==(UINT64_C(1)<<53)) {q>>=1;++exponent;}
  if(exponent>1023) return sign_bits(sign)|Infinity;
  return sign_bits(sign)|(U64(exponent+1023)<<52)|(q&Fraction);
}
int compare(U64 a,U64 b) {
  if((a&Magnitude)>Infinity || (b&Magnitude)>Infinity) return 2;
  if(a==b || !((a|b)&Magnitude)) return 0;
  if((a^b)&Sign) return a&Sign ? -1:1;
  return ((a&Sign) ? a>b : a<b) ? -1:1;
}
U64 trunc_magnitude(U64 a) {
  const U64 magnitude=a&Magnitude;
  const int exponent=int(magnitude>>52)-1023;
  if(magnitude>Infinity || exponent<0) return 0;
  if(exponent>=64) return UINT64_MAX;
  const U64 sig=(a&Fraction)|(UINT64_C(1)<<52);
  return exponent>=52 ? sig<<unsigned(exponent-52):sig>>unsigned(52-exponent);
}
// Quotient fits in 32 bits and denominator's top bit is set. Two radix-2^16
// digits need only native 32-bit UDIV; no 64-bit division libcall is used.
EABI_INLINE uint32_t divide_short(U64 numerator,uint32_t denominator) {
  const uint32_t high=denominator>>16,low=denominator&0xFFFFU;
  const uint32_t a=uint32_t(numerator>>32),b=uint32_t(numerator);
  uint32_t q1=a/high,r=a-q1*high;
  while(q1>=0x10000U || q1*low>(r<<16)+(b>>16)) {
    --q1;r+=high;if(r>=0x10000U) break;
  }
  const uint32_t remaining=(a<<16)+(b>>16)-q1*denominator;
  uint32_t q0=remaining/high;r=remaining-q0*high;
  while(q0>=0x10000U || q0*low>(r<<16)+(b&0xFFFFU)) {
    --q0;r+=high;if(r>=0x10000U) break;
  }
  return (q1<<16)|q0;
}
} // namespace native_eabi
using namespace native_eabi;
extern "C" {
MK61_SOFT_PCS double mk61_eabi_ddiv_scale(double a,double b) {return value(scale_power2(bits(a),bits(b)));}
#if defined(__arm__) || defined(__thumb__)
MK61_SOFT_PCS double mk61_eabi_ddiv_slow(double a,double b) {return value(div(bits(a),bits(b)));}
#else
MK61_SOFT_PCS double __aeabi_ddiv(double a,double b) {return value(div(bits(a),bits(b)));}
#endif
MK61_SOFT_PCS int __aeabi_dcmpeq(double a,double b) {return compare(bits(a),bits(b))==0;}
MK61_SOFT_PCS int __aeabi_dcmplt(double a,double b) {return compare(bits(a),bits(b))==-1;}
MK61_SOFT_PCS int __aeabi_dcmple(double a,double b) {return compare(bits(a),bits(b))<=0;}
MK61_SOFT_PCS int __aeabi_dcmpge(double a,double b) {const int c=compare(bits(a),bits(b));return c==0 || c==1;}
MK61_SOFT_PCS int __aeabi_dcmpgt(double a,double b) {return compare(bits(a),bits(b))==1;}
MK61_SOFT_PCS int64_t __aeabi_d2lz(double a) {
  const U64 b=bits(a),m=trunc_magnitude(b),u=b&Sign ? U64(0)-m:m;
  int64_t result;__builtin_memcpy(&result,&u,8);return result;
}
MK61_SOFT_PCS uint64_t __aeabi_d2ulz(double a) {const U64 b=bits(a);return b&Sign ? 0:trunc_magnitude(b);}
void mk61_eabi_divmod64(uint64_t n,uint64_t d,mk61_eabi_divmod* result) {
  if(!d) {*result={n ? UINT64_MAX:0,0};return;}
  if(n<d) {*result={0,n};return;}
  const uint32_t nh=uint32_t(n>>32),nl=uint32_t(n),dh=uint32_t(d>>32),dl=uint32_t(d);
  if(!dh) {
    const uint32_t qh=nh/dl,rh=nh-qh*dl;
    const unsigned shift=unsigned(__builtin_clz(dl));
    const U64 remainder_input=(U64(rh)<<32)|nl;
    const uint32_t ql=divide_short(remainder_input<<shift,dl<<shift);
    *result={(U64(qh)<<32)|ql,remainder_input-U64(dl)*ql};return;
  }
  const unsigned shift=unsigned(__builtin_clz(dh));
  const uint32_t top=shift ? nh>>(32-shift):0;
  const uint32_t next=shift ? (nh<<shift)|(nl>>(32-shift)):nh;
  const uint32_t divisor=shift ? (dh<<shift)|(dl>>(32-shift)):dh;
  uint32_t q=divide_short((U64(top)<<32)|next,divisor);
  U64 lo,hi,p;
  for(;;) {
    lo=U64(dl)*q;hi=U64(dh)*q+(lo>>32);p=(hi<<32)|uint32_t(lo);
    if(!(hi>>32) && p<=n) break;
    --q;
  }
  *result={q,n-p};
}
#if defined(__arm__) || defined(__thumb__)
// GCC compiler spellings for our remaining C++ primitives.
MK61_SOFT_PCS int64_t __fixdfdi(double) __attribute__((alias("__aeabi_d2lz"), nothrow));
MK61_SOFT_PCS uint64_t __fixunsdfdi(double) __attribute__((alias("__aeabi_d2ulz"), nothrow));
#endif
}
#endif
