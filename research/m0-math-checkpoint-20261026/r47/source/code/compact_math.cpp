/*
 * Compact binary64 math for the calculator's standalone STM32 runtime.
 *
 * Numerical kernels adapted from fdlibm / OpenLibm, pinned upstream:
 * https://github.com/JuliaMath/openlibm/tree/5fe399749f9276eaa0b8403e507470da05cbbb3f
 *
 * Copyright (C) 1993, 2004 by Sun Microsystems, Inc. All rights reserved.
 * Developed at SunSoft / SunPro, a Sun Microsystems, Inc. business.
 * Permission to use, copy, modify, and distribute this software is freely
 * granted, provided that this notice is preserved.
 * Argument reduction optimized by Bruce D. Evans.
 *
 * Project adaptation: binary64 only, shared log2/exp2 and asin/acos kernels,
 * independent Q62 sin/cos/atan/exp, integer Payne-Hanek argument reduction,
 * and float-seeded, exactly corrected
 * square root; no long-double, fenv or errno ABI.
 * Round-to-nearest-even is the STM32 software-double arithmetic contract.
 * See doc/design/STM32-standalone-runtime.md for provenance and accuracy checks.
 */

#include "mk_math.hpp"
#include "compact_math.hpp"
#include "compact_math_tables.hpp"
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI
#include "native_eabi_m0.hpp"
#endif

#if MK61_USE_COMPACT_LIBM && MK61_MATH_BACKEND == MK61_MATH_BACKEND_BINARY64

static_assert(DBL_MANT_DIG == 53 && DBL_MAX_EXP == 1024,
              "compact math requires IEEE binary64");

// RP2040 public entry points alias their native kernels below. The legacy
// implementations remain available to the other targets.
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI && (defined(__arm__) || defined(__thumb__))
#define MK61_M0_UNUSED_FALLBACK __attribute__((unused))
#else
#define MK61_M0_UNUSED_FALLBACK
#endif

namespace compact_math {
namespace {
inline uint64_t bits(double x) { return mk_math::binary64_bits(x); }
inline double value(uint64_t x) { return mk_math::binary64_value(x); }
inline uint32_t hi_word(double x) { return uint32_t(bits(x) >> 32); }
inline uint32_t lo_word(double x) { return uint32_t(bits(x)); }
inline double set_high(double x, uint32_t h) {
  return value((uint64_t(h) << 32) | lo_word(x));
}
inline double set_low(double x, uint32_t l) {
  return value((bits(x) & UINT64_C(0xFFFFFFFF00000000)) | l);
}
inline double absolute(double x) {
  return value(bits(x) & UINT64_C(0x7FFFFFFFFFFFFFFF));
}
inline double infinity() { return __builtin_huge_val(); }
inline double nan(double x) { return (x-x)/(x-x); }

// Bit casts use memcpy semantics, independent of host/device endianness and
// strict-aliasing rules. These macros keep the audited fdlibm expressions.
#define GET_HIGH_WORD(h,x) ((h) = hi_word(x))
#define GET_LOW_WORD(l,x) ((l) = lo_word(x))
#define EXTRACT_WORDS(h,l,x) do { (h) = hi_word(x); (l) = lo_word(x); } while (0)
#define SET_HIGH_WORD(x,h) ((x) = set_high((x), uint32_t(h)))
#define SET_LOW_WORD(x,l) ((x) = set_low((x), uint32_t(l)))
#define INSERT_WORDS(x,h,l) ((x) = value((uint64_t(uint32_t(h)) << 32) | uint32_t(l)))
#define STRICT_ASSIGN(type,dst,src) ((dst) = static_cast<type>(src))

// Independent integer Taylor kernels; constants rounded from exact 1/n!.
// No Qfplib or proprietary emFloat source is incorporated here.
namespace fixed_kernel {
struct Product { uint64_t high, low; };
// Four exact 32x32 -> 64 products map to UMULL on Cortex-M4.
__attribute__((always_inline)) inline Product multiply(uint64_t a, uint64_t b) {
  const uint32_t a0=uint32_t(a), a1=uint32_t(a>>32);
  const uint32_t b0=uint32_t(b), b1=uint32_t(b>>32);
  const uint64_t p0=uint64_t(a0)*b0;
  const uint64_t p1=uint64_t(a1)*b0+(p0>>32);
  const uint64_t p2=uint64_t(a0)*b1+uint32_t(p1);
  return {uint64_t(a1)*b1+(p1>>32)+(p2>>32),
          (p2<<32)|uint32_t(p0)};
}
// Passing a 128-bit Product out of line introduces a stack copy under AAPCS.
// Keep this rounding step with its UMULL producer in every size/LTO profile.
__attribute__((always_inline)) inline uint64_t rounded_shift62(Product p) {
  uint64_t q=(p.high<<2)|(p.low>>62);
  const uint64_t tail=p.low&((UINT64_C(1)<<62)-1);
  const uint64_t half=UINT64_C(1)<<61;
  return q+(tail>half || (tail==half && (q&1)));
}
inline uint64_t rounded_right(uint64_t q,unsigned shift) {
  if (!shift) return q;
  if (shift>64) return 0;
  if (shift==64) return q>(UINT64_C(1)<<63);
  const uint64_t half=UINT64_C(1)<<(shift-1);
  const uint64_t tail=q&((half<<1)-1);
  return (q>>shift)+(tail>half || (tail==half && ((q>>shift)&1)));
}
inline int64_t scaled_product(uint64_t z,int64_t coefficient) {
  const bool negative=coefficient<0;
  const uint64_t magnitude=negative?uint64_t(-coefficient):uint64_t(coefficient);
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && (defined(__arm__) || defined(__thumb__))
  const int64_t p=int64_t(mk61_m0_mul_q62(z,magnitude));
#else
  const int64_t p=int64_t(rounded_shift62(multiply(z,magnitude)));
#endif
  return negative?-p:p;
}
inline uint64_t normalized(double x,double tail,int &e) {
  const uint64_t b=bits(x),t=bits(tail);
  e=int((b>>52)&0x7FFU)-1022;
  uint64_t q=((b&UINT64_C(0xFFFFFFFFFFFFF))|(UINT64_C(1)<<52))<<10;
  if ((t<<1)!=0) {
    const int te=int((t>>52)&0x7FFU);
    const uint64_t m=(t&UINT64_C(0xFFFFFFFFFFFFF))|(te?(UINT64_C(1)<<52):0);
    const int shift=(te?te-1023:-1022)-e+11;
    const uint64_t correction=shift<0?rounded_right(m,unsigned(-shift)):m<<unsigned(shift);
    q=(b^t)>>63?q-correction:q+correction;
  }
  return q;
}
inline double pack(uint64_t q,int e,uint64_t sign) {
  const int top=63-__builtin_clzll(q);
  int exponent=top+e-63;
  uint64_t m=rounded_right(q,unsigned(top-52));
  if (m==(UINT64_C(1)<<53)) { m>>=1; ++exponent; }
  if (exponent>1023) return value(sign|UINT64_C(0x7FF0000000000000));
  if (exponent < -1022) {
    // Round once, directly from the guard bits into a subnormal result.
    const int shift=-e-1011;
    return value(sign|rounded_right(q,unsigned(shift)));
  }
  return value(sign|(uint64_t(exponent+1023)<<52)|(m&UINT64_C(0xFFFFFFFFFFFFF)));
}
inline uint64_t square(uint64_t q,int exponent) {
  const Product p=multiply(q,q);
  // x=q*2^(exponent-63), so x*x in Q62 is q*q*2^(2*exponent-64).
  // Reduction bounds |x| <= pi/4 and hence exponent <= 0.
  return rounded_right(p.high,unsigned(-2*exponent));
}
using tables::sine_coefficients;
using tables::cosine_coefficients;
inline uint64_t polynomial(uint64_t z,const int64_t *coefficients,unsigned count) {
  int64_t result=coefficients[count-1];
  while (--count) result=coefficients[count-1]+scaled_product(z,result);
  return uint64_t(result);
}
double sine(double x,double tail) {
  const uint64_t b=bits(x);
  if ((hi_word(x)&0x7FFFFFFFU)<0x3E400000U) return x+tail;
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && (defined(__arm__) || defined(__thumb__))
  if((hi_word(x)&0x7FFFFFFFU)>=0x3F900000U) {
    double output[2];mk61_m0_sincos_reduced(x,tail,output,1);return output[0];
  }
  double output[2];mk61_m0_sincos_small(x,tail,output,1);return output[0];
#endif
  int exponent;const uint64_t q=normalized(x,tail,exponent);
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && (defined(__arm__) || defined(__thumb__))
  const uint64_t factor=polynomial(square(q,exponent),sine_coefficients,4);
#else
  const uint64_t factor=polynomial(square(q,exponent),sine_coefficients,9);
#endif
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && (defined(__arm__) || defined(__thumb__))
  return pack(mk61_m0_mul_q62(q,factor),exponent,b&UINT64_C(0x8000000000000000));
#else
  return pack(rounded_shift62(multiply(q,factor)),exponent,b&UINT64_C(0x8000000000000000));
#endif
}
double cosine(double x,double tail) {
  if ((hi_word(x)&0x7FFFFFFFU)<0x3E400000U) return 1.0;
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && (defined(__arm__) || defined(__thumb__))
  if((hi_word(x)&0x7FFFFFFFU)>=0x3F900000U) {
    double output[2];mk61_m0_sincos_reduced(x,tail,output,2);return output[1];
  }
  double output[2];mk61_m0_sincos_small(x,tail,output,2);return output[1];
#endif
  int exponent;const uint64_t q=normalized(x,tail,exponent);
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && (defined(__arm__) || defined(__thumb__))
  return pack(polynomial(square(q,exponent),cosine_coefficients,4),1,0);
#else
  return pack(polynomial(square(q,exponent),cosine_coefficients,10),1,0);
#endif
}
using tables::exponential_coefficients;
inline int64_t fixed_argument(double x) {
  const uint64_t b=bits(x);
  const int e=int((b>>52)&0x7FFU);
  const uint64_t m=(b&UINT64_C(0xFFFFFFFFFFFFF))|(e?(UINT64_C(1)<<52):0);
  const int shift=(e?e-1023:-1022)+10;
  const uint64_t q=shift>=0?m<<unsigned(shift):rounded_right(m,unsigned(-shift));
  return b>>63?-int64_t(q):int64_t(q);
}
double exponential(double x,double tail,int exponent) {
  const int64_t q=fixed_argument(x)+fixed_argument(tail);
  int64_t p=exponential_coefficients[15];
  for (unsigned i=15;i--;)
    p=exponential_coefficients[i]+(q<0?-scaled_product(uint64_t(-q),p):scaled_product(uint64_t(q),p));
  return pack(uint64_t(p),exponent+1,0);
}

}
namespace sine {
double evaluate(double x,double y,int) {return fixed_kernel::sine(x,y);}
}
namespace cosine {
double evaluate(double x,double y) {return fixed_kernel::cosine(x,y);}
}

namespace arctangent {
using tables::angle_table;
using tables::atan_coefficients;
using tables::half_pi;
inline uint64_t reduced(double x,int &e) {
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && (defined(__arm__) || defined(__thumb__))
  return mk61_m0_atan_reduced(x,&e);
#else
  const uint64_t q=fixed_kernel::normalized(x,0.0,e);
  const uint64_t factor=fixed_kernel::polynomial(fixed_kernel::square(q,e),atan_coefficients,5);
  return fixed_kernel::rounded_shift62(fixed_kernel::multiply(q,factor));
#endif
}
MK61_M0_UNUSED_FALLBACK double evaluate(double x) {
  const uint64_t b=bits(x),sign=b&UINT64_C(0x8000000000000000);
  const uint32_t h=hi_word(x)&0x7FFFFFFFU;
  if (h<0x3E400000U) return x;
  if (h>=0x7FF00000U) {
    if ((b&UINT64_C(0x7FFFFFFFFFFFFFFF))>UINT64_C(0x7FF0000000000000)) return x+x;
    return fixed_kernel::pack(half_pi,1,sign);
  }
  x=absolute(x);
  const bool invert=x>1.0;
  if (invert) x=1.0/x;
  if (x<0x1p-6) {
    int e;const uint64_t q=reduced(x,e);
    if (!invert) return fixed_kernel::pack(q,e,sign);
    return fixed_kernel::pack(half_pi-fixed_kernel::rounded_right(q,unsigned(1-e)),1,sign);
  }
  const uint64_t bx=bits(x),m=(bx&UINT64_C(0xFFFFFFFFFFFFF))|(UINT64_C(1)<<52);
  const int e=int(bx>>52)-1023;
  const unsigned index=(unsigned(m>>unsigned(45-e))+1)/2;
  const unsigned top=31-__builtin_clz(index);
  const double a=value((uint64_t(1017+top)<<52)|((uint64_t(index)<<(52-top))&UINT64_C(0xFFFFFFFFFFFFF)));
  const double r=(x-a)/(1.0+a*x);
  int64_t correction=0;
  if ((bits(r)<<1)!=0) {
    int re;const uint64_t q=reduced(r,re);
    correction=int64_t(fixed_kernel::rounded_right(q,unsigned(1-re)));
    if (bits(r)>>63) correction=-correction;
  }
  uint64_t result=uint64_t(int64_t(angle_table[index])+correction);
  if (invert) result=half_pi-result;
  return fixed_kernel::pack(result,1,sign);
}
}

namespace square_root {
inline bool greater(fixed_kernel::Product a,fixed_kernel::Product b) {
  return a.high>b.high || (a.high==b.high && a.low>b.low);
}
// Denominator has its top bit set; the quotient fits in 32 bits. Two
// radix-2^16 digits use only the M4's native 32-bit UDIV instruction.
inline uint32_t short_divide(uint64_t numerator,uint32_t denominator) {
  const uint32_t high=denominator>>16,low=denominator&0xFFFFU;
  const uint32_t a=uint32_t(numerator>>32),b=uint32_t(numerator);
  uint32_t q1=a/high,r=a-q1*high;
  while (q1>=0x10000U || q1*low>(r<<16)+(b>>16)) {
    --q1;r+=high;if (r>=0x10000U) break;
  }
  const uint32_t remaining=(a<<16)+(b>>16)-q1*denominator;
  uint32_t q0=remaining/high;r=remaining-q0*high;
  while (q0>=0x10000U || q0*low>(r<<16)+(b&0xFFFFU)) {
    --q0;r+=high;if (r>=0x10000U) break;
  }
  return (q1<<16)|q0;
}
MK61_M0_UNUSED_FALLBACK double evaluate(double x) {
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && (defined(__arm__) || defined(__thumb__))
  return mk61_m0_sqrt(x);
#else
  const uint64_t b=bits(x),magnitude=b&UINT64_C(0x7FFFFFFFFFFFFFFF);
  if (!magnitude) return x;
  unsigned exponent=unsigned(magnitude>>52);
  if (exponent==0x7FFU) {
    if (b==UINT64_C(0x7FF0000000000000)) return x;
    return value(b|UINT64_C(0x7FF8000000000000));
  }
  if (b>>63) return value(UINT64_C(0x7FF8000000000000));
  uint64_t significand=magnitude&UINT64_C(0xFFFFFFFFFFFFF);
  int e=int(exponent)-1023;
  if (!exponent) {
    const unsigned shift=unsigned(__builtin_clzll(significand)-11);
    significand<<=shift;
    e=-1022-int(shift);
  } else significand|=UINT64_C(1)<<52;
  // Normalize to [1,4) before the float seed. No input/output precision is
  // reduced: integer refinements and an exact 106-bit residual decide
  // the final nearest-even binary64 result.
  const unsigned odd=unsigned(e)&1U;
  const double m=value((significand&UINT64_C(0xFFFFFFFFFFFFF))|((uint64_t(1023+odd))<<52));
  const float fm=float(m);
  float fs;
#if defined(__arm__) && defined(__ARM_FP) && (__ARM_FP & 4)
  __asm__("vsqrt.f32 %0, %1" : "=t"(fs) : "t"(fm));
#elif defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI
  fs=mk61_m0_sqrtf(fm);
#else
  fs=__builtin_sqrtf(fm);
#endif
  const uint32_t seed=fs>=2.0f?UINT32_MAX:uint32_t(fs*0x1p31f);
  significand<<=odd;
  const uint64_t normalized_radicand=significand<<10;
  const uint64_t square_seed=uint64_t(seed)*seed;
  const bool subtract=normalized_radicand<square_seed;
  const uint64_t residual=subtract?square_seed-normalized_radicand:normalized_radicand-square_seed;
  const uint64_t delta=short_divide(residual<<20,seed);
  uint64_t q=(uint64_t(seed)<<21);
  q=subtract?q-delta:q+delta;
  const fixed_kernel::Product radicand={significand>>12,significand<<52};
  // One fixed-point Newton step gives at least 46 accurate bits. Estimate
  // the remaining (small) correction with a native 32-bit division, then
  // bound the root by exact 106-bit products before final rounding.
  const fixed_kernel::Product candidate=fixed_kernel::multiply(q,q);
  const bool below=greater(candidate,radicand);
  const uint64_t difference=below?candidate.low-radicand.low:radicand.low-candidate.low;
  const uint32_t correction=uint32_t(difference>>32)/uint32_t((q+q)>>32);
  q=below?q-correction:q+correction;
  fixed_kernel::Product squared=fixed_kernel::multiply(q,q);
  while (greater(squared,radicand)) { --q;squared=fixed_kernel::multiply(q,q); }
  for (;;) {
    const fixed_kernel::Product next=fixed_kernel::multiply(q+1,q+1);
    if (greater(next,radicand)) break;
    ++q;squared=next;
  }
  // The integer radicand cannot equal (q+1/2)^2. Comparing the exact
  // remainder to q selects the nearest root without a double rounding.
  const uint64_t remainder=radicand.low-squared.low;
  if (remainder>q) ++q;
  int output_e=(e-int(odd))/2;
  if (q==(UINT64_C(1)<<53)) {q>>=1;++output_e;}
  return value((uint64_t(output_e+1023)<<52)|(q&UINT64_C(0xFFFFFFFFFFFFF)));
#endif
}
}

namespace integer_reduction {
using tables::two_over_pi;
inline uint32_t read32(const uint32_t* p,int bit) {
  if (bit<0) return bit<=-32?0:p[0]<<unsigned(-bit);
  const unsigned word=unsigned(bit)/32,shift=unsigned(bit)%32;
  uint32_t result=word<52?p[word]>>shift:0;
  if (shift && word+1<52) result|=p[word+1]<<(32-shift);
  return result;
}
inline double pack_tail(uint64_t q,int e,uint64_t sign) {
  if (!q) return value(sign);
  const int top=63-__builtin_clzll(q),exponent=top+e-63;
  if (top>=52) return fixed_kernel::pack(q,e,sign);
  if (exponent < -1022) {
    const int shift=e+1011;
    return value(sign|(shift<0?fixed_kernel::rounded_right(q,unsigned(-shift)):q<<unsigned(shift)));
  }
  return value(sign|(uint64_t(exponent+1023)<<52)|((q<<(52-top))&UINT64_C(0xFFFFFFFFFFFFF)));
}
int reduce_large(double x,double* output) {
  const uint64_t b=bits(x),mantissa=(b&UINT64_C(0xFFFFFFFFFFFFF))|(UINT64_C(1)<<52);
  const int e=int((b>>52)&0x7FFU)-1023;
  const unsigned point=unsigned(1600-e+52),last=(point+2)/32;
  uint32_t product[52];
  if (last+1<52) product[last+1]=0; // read32 may inspect one guard word.
  uint64_t carry=0;
  const uint32_t ml=uint32_t(mantissa),mh=uint32_t(mantissa>>32);
  for (unsigned i=0;i<=last;++i) {
    const uint64_t a=uint64_t(ml)*(i<50?two_over_pi[i]:0);
    const uint64_t c=uint64_t(mh)*(i && i<=50?two_over_pi[i-1]:0);
    const uint64_t low=uint64_t(uint32_t(a))+uint32_t(c)+uint32_t(carry);
    product[i]=uint32_t(low);
    carry=(a>>32)+(c>>32)+(carry>>32)+(low>>32);
  }
  unsigned quadrant=read32(product,int(point))&3U;
  const bool negative=(read32(product,int(point)-1)&1U)!=0;
  const unsigned end=point/32,remaining=point%32;
  product[end]&=(UINT32_C(1)<<remaining)-1;
  if (negative) {
    uint64_t bit=1;
    for (unsigned i=0;i<=end;++i) {
      bit+=~product[i];product[i]=uint32_t(bit);bit>>=32;
    }
    product[end]&=(UINT32_C(1)<<remaining)-1;
    quadrant=(quadrant+1)&3U;
  }
  unsigned top=end;while (!product[top]) --top;
  const int leading=int(top*32)+31-__builtin_clz(product[top]);
  const uint64_t fraction=uint64_t(read32(product,leading-62))|
                          (uint64_t(read32(product,leading-30))<<32);
  const uint64_t reduced=fixed_kernel::rounded_shift62(fixed_kernel::multiply(fraction,tables::half_pi));
  const int exponent=leading-int(point)+1;
  const uint64_t sign=(b&UINT64_C(0x8000000000000000))^(negative?UINT64_C(0x8000000000000000):0);
  output[0]=fixed_kernel::pack(reduced,exponent,sign);
  const uint64_t high=bits(output[0])&UINT64_C(0x7FFFFFFFFFFFFFFF);
  if ((high>>52)==0) output[1]=0.0;
  else {
    const int shift=int(high>>52)-1023-exponent+11;
    const uint64_t rounded=((high&UINT64_C(0xFFFFFFFFFFFFF))|(UINT64_C(1)<<52))<<unsigned(shift);
    const bool minus=reduced<rounded;
    const uint64_t difference=minus?rounded-reduced:reduced-rounded;
    output[1]=pack_tail(difference,exponent,sign^(minus?UINT64_C(0x8000000000000000):0));
  }
  return b>>63?-int(quadrant):int(quadrant);
}
}

namespace argument {
static const double
invpio2 =  6.36619772367581382433e-01,
pio2_1  =  1.57079632673412561417e+00,
pio2_1t =  6.07710050650619224932e-11,
pio2_2  =  6.07710050630396597660e-11,
pio2_2t =  2.02226624879595063154e-21,
pio2_3  =  2.02226624871116645580e-21,
pio2_3t =  8.47842766036889956997e-32;


int reduce(double x, double *y)
{
        double z,w,t,r,fn;
        int32_t i,j,n,ix,hx;

        GET_HIGH_WORD(hx,x);		/* high word of x */
        ix = hx&0x7fffffff;
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && (defined(__arm__) || defined(__thumb__))
        if(ix<0x41300000) {
            const int reduced=mk61_m0_reduce_pio2(x,y);
            if(reduced) return reduced;
        }
#endif
if (ix <= 0x400f6a7a) {		/* |x| ~<= 5pi/4 */
            if ((ix & 0xfffff) == 0x921fb)  /* |x| ~= pi/2 or 2pi/2 */
                goto medium;		/* cancellation -- use medium case */
            if (ix <= 0x4002d97c) {	/* |x| ~<= 3pi/4 */
                if (hx > 0) {
                    z = x - pio2_1;	/* one round good to 85 bits */
                    y[0] = z - pio2_1t;
                    y[1] = (z-y[0])-pio2_1t;
                    return 1;
                } else {
                    z = x + pio2_1;
                    y[0] = z + pio2_1t;
                    y[1] = (z-y[0])+pio2_1t;
                    return -1;
                }
            } else {
                if (hx > 0) {
                    z = x - 2*pio2_1;
                    y[0] = z - 2*pio2_1t;
                    y[1] = (z-y[0])-2*pio2_1t;
                    return 2;
                } else {
                    z = x + 2*pio2_1;
                    y[0] = z + 2*pio2_1t;
                    y[1] = (z-y[0])+2*pio2_1t;
                    return -2;
                }
            }
        }
        if (ix <= 0x401c463b) {		/* |x| ~<= 9pi/4 */
            if (ix <= 0x4015fdbc) {	/* |x| ~<= 7pi/4 */
                if (ix == 0x4012d97c)	/* |x| ~= 3pi/2 */
                    goto medium;
                if (hx > 0) {
                    z = x - 3*pio2_1;
                    y[0] = z - 3*pio2_1t;
                    y[1] = (z-y[0])-3*pio2_1t;
                    return 3;
                } else {
                    z = x + 3*pio2_1;
                    y[0] = z + 3*pio2_1t;
                    y[1] = (z-y[0])+3*pio2_1t;
                    return -3;
                }
            } else {
                if (ix == 0x401921fb)	/* |x| ~= 4pi/2 */
                    goto medium;
                if (hx > 0) {
                    z = x - 4*pio2_1;
                    y[0] = z - 4*pio2_1t;
                    y[1] = (z-y[0])-4*pio2_1t;
                    return 4;
                } else {
                    z = x + 4*pio2_1;
                    y[0] = z + 4*pio2_1t;
                    y[1] = (z-y[0])+4*pio2_1t;
                    return -4;
                }
            }
        }
        if(ix<0x413921fb) {	/* |x| ~< 2^20*(pi/2), medium size */
medium:
            /* Use a specialized rint() to get fn.  Assume round-to-nearest. */
            STRICT_ASSIGN(double,fn,x*invpio2+0x1.8p52);
            fn = fn-0x1.8p52;
n  = (int32_t)fn;

            r  = x-fn*pio2_1;
            w  = fn*pio2_1t;	/* 1st round good to 85 bit */
            {
                uint32_t high;
                j  = ix>>20;
                y[0] = r-w;
                GET_HIGH_WORD(high,y[0]);
                i = j-((high>>20)&0x7ff);
                if(i>16) {  /* 2nd iteration needed, good to 118 */
                    t  = r;
                    w  = fn*pio2_2;
                    r  = t-w;
                    w  = fn*pio2_2t-((t-r)-w);
                    y[0] = r-w;
                    GET_HIGH_WORD(high,y[0]);
                    i = j-((high>>20)&0x7ff);
                    if(i>49)  {	/* 3rd iteration need, 151 bits acc */
                        t  = r;	/* will cover all possible cases */
                        w  = fn*pio2_3;
                        r  = t-w;
                        w  = fn*pio2_3t-((t-r)-w);
                        y[0] = r-w;
                    }
                }
            }
            y[1] = (r-y[0])-w;
            return n;
        }
    /*
     * all other (large) arguments
     */
        if(ix>=0x7ff00000) {		/* x is inf or NaN */
            y[0]=y[1]=x-x; return 0;
        }
    return integer_reduction::reduce_large(x,y);
}
}

namespace arcsine {
static const double
one =  1.00000000000000000000e+00,
huge =  1.000e+300,
pio2_hi =  1.57079632679489655800e+00,
pio2_lo =  6.12323399573676603587e-17,
pio4_hi =  7.85398163397448278999e-01,
        /* coefficient for R(x^2) */
pS0 =  1.66666666666666657415e-01,
pS1 = -3.25565818622400915405e-01,
pS2 =  2.01212532134862925881e-01,
pS3 = -4.00555345006794114027e-02,
pS4 =  7.91534994289814532176e-04,
pS5 =  3.47933107596021167570e-05,
qS1 = -2.40339491173441421878e+00,
qS2 =  2.02094576023350569471e+00,
qS3 = -6.88283971605453293030e-01,
qS4 =  7.70381505559019352791e-02;



__attribute__((noinline)) double ratio(double z) {
  const double p = z*(pS0+z*(pS1+z*(pS2+z*(pS3+z*(pS4+z*pS5)))));
  const double q = one+z*(qS1+z*(qS2+z*(qS3+z*qS4)));
  return p/q;
}
MK61_M0_UNUSED_FALLBACK double evaluate(double x)
{
        double t=0.0,w,p,q,c,r,s;
        int32_t hx,ix;
        GET_HIGH_WORD(hx,x);
        ix = hx&0x7fffffff;
        if(ix>= 0x3ff00000) {		/* |x|>= 1 */
            uint32_t lx;
            GET_LOW_WORD(lx,x);
            if(((ix-0x3ff00000)|lx)==0)
                    /* asin(1)=+-pi/2 with inexact */
                return x*pio2_hi+x*pio2_lo;
            return (x-x)/(x-x);		/* asin(|x|>1) is NaN */
        } else if (ix<0x3fe00000) {	/* |x|<0.5 */
            if(ix<0x3e500000) {		/* if |x| < 2**-26 */
                if(huge+x>one) return x;/* return x with inexact if x!=0*/
            }
            t = x*x;
            r = ratio(t);
            w = r;
            return x+x*w;
        }
        /* 1> |x|>= 0.5 */
        w = one-absolute(x);
        t = w*0.5;
        r = ratio(t);
        s = sqrt(t);
        if(ix>=0x3FEF3333) { 	/* if |x| > 0.975 */
            w = r;
            t = pio2_hi-(2.0*(s+s*w)-pio2_lo);
        } else {
            w  = s;
            SET_LOW_WORD(w,0);
            c  = (t-w*w)/(s+w);

            p  = 2.0*s*r-(pio2_lo-2.0*c);
            q  = pio4_hi-2.0*w;
            t  = pio4_hi-(p-q);
        }
        if(hx>0) return t; else return -t;
}
MK61_M0_UNUSED_FALLBACK double complement(double x)
{
        double z,r,w,s,c,df;
        int32_t hx,ix;
        GET_HIGH_WORD(hx,x);
        ix = hx&0x7fffffff;
        if(ix>=0x3ff00000) {	/* |x| >= 1 */
            uint32_t lx;
            GET_LOW_WORD(lx,x);
            if(((ix-0x3ff00000)|lx)==0) {	/* |x|==1 */
                if(hx>0) return 0.0;		/* acos(1) = 0  */
                else return (2.0*pio2_hi)+2.0*pio2_lo;	/* acos(-1)= (2.0*pio2_hi) */
            }
            return (x-x)/(x-x);		/* acos(|x|>1) is NaN */
        }
        if(ix<0x3fe00000) {	/* |x| < 0.5 */
            if(ix<=0x3c600000) return pio2_hi+pio2_lo;/*if|x|<2**-57*/
            z = x*x;
            r = ratio(z);

            return pio2_hi - (x - (pio2_lo-x*r));
        } else  if (hx<0) {		/* x < -0.5 */
            z = (one+x)*0.5;
            r = ratio(z);
            s = sqrt(z);

            w = r*s-pio2_lo;
            return (2.0*pio2_hi) - 2.0*(s+w);
        } else {			/* x > 0.5 */
            z = (one-x)*0.5;
            s = sqrt(z);
            df = s;
            SET_LOW_WORD(df,0);
            c  = (z-df*df)/(s+df);
            r = ratio(z);

            w = r*s+c;
            return 2.0*(df+w);
        }
}
}

namespace natural_log {
static const double
ln2_hi  =  6.93147180369123816490e-01,	/* 3fe62e42 fee00000 */
ln2_lo  =  1.90821492927058770002e-10,	/* 3dea39ef 35793c76 */
two54   =  1.80143985094819840000e+16,  /* 43500000 00000000 */
Lg1 = 6.666666666666735130e-01,  /* 3FE55555 55555593 */
Lg2 = 3.999999999940941908e-01,  /* 3FD99999 9997FA04 */
Lg3 = 2.857142874366239149e-01,  /* 3FD24924 94229359 */
Lg4 = 2.222219843214978396e-01,  /* 3FCC71C5 1D8E78AF */
Lg5 = 1.818357216161805012e-01,  /* 3FC74664 96CB03DE */
Lg6 = 1.531383769920937332e-01,  /* 3FC39A09 D078C69F */
Lg7 = 1.479819860511658591e-01;  /* 3FC2F112 DF3E5244 */

static const double zero   =  0.0;



__attribute__((noinline)) double polynomial(double z) {
  const double w = z*z;
  return w*(Lg2+w*(Lg4+w*Lg6)) + z*(Lg1+w*(Lg3+w*(Lg5+w*Lg7)));
}
MK61_M0_UNUSED_FALLBACK double evaluate(double x)
{
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && (defined(__arm__) || defined(__thumb__))
        const uint32_t high=hi_word(x);
        if(high>=0x00100000U && high<0x7FF00000U) return mk61_m0_ln(x);
#endif
        double hfsq,f,s,z,R,dk;
        int32_t k,hx,i,j;
        uint32_t lx;

        EXTRACT_WORDS(hx,lx,x);

        k=0;
        if (hx < 0x00100000) {			/* x < 2**-1022  */
            if (((hx&0x7fffffff)|lx)==0)
                return -two54/zero;		/* log(+-0)=-inf */
            if (hx<0) return (x-x)/zero;	/* log(-#) = NaN */
            k -= 54; x *= two54; /* subnormal number, scale up x */
            GET_HIGH_WORD(hx,x);
        }
        if (hx >= 0x7ff00000) return x+x;
        k += (hx>>20)-1023;
        hx &= 0x000fffff;
        i = (hx+0x95f64)&0x100000;
        SET_HIGH_WORD(x,hx|(i^0x3ff00000));	/* normalize x or x/2 */
        k += (i>>20);
        f = x-1.0;
        if((0x000fffff&(2+hx))<3) {	/* -2**-20 <= f < 2**-20 */
            if(f==zero) {
                if(k==0) {
                    return zero;
                } else {
                    dk=(double)k;
                    return dk*ln2_hi+dk*ln2_lo;
                }
            }
            R = f*f*(0.5-0.33333333333333333*f);
            if(k==0) return f-R; else {dk=(double)k;
                     return dk*ln2_hi-((R-dk*ln2_lo)-f);}
        }
        s = f/(2.0+f);
        dk = (double)k;
        z = s*s;
        i = hx-0x6147a;

        j = 0x6b851-hx;

        i |= j;
        R = polynomial(z);
        if(i>0) {
            hfsq=0.5*f*f;
            if(k==0) return f-(hfsq-s*(hfsq+R)); else
                     return dk*ln2_hi-((hfsq-(s*(hfsq+R)+dk*ln2_lo))-f);
        } else {
            if(k==0) return f-s*(f-R); else
                     return dk*ln2_hi-((s*(f-R)-dk*ln2_lo)-f);
        }
}
}

namespace power {
static const double
bp[] = {1.0, 1.5,},
dp_h[] = { 0.0, 5.84962487220764160156e-01,},
dp_l[] = { 0.0, 1.35003920212974897128e-08,},
zero    =  0.0,
one	=  1.0,
two53	=  9007199254740992.0,
        /* poly coefs for (3/2)*(log(x)-2s-2/3*s**3 */
L1  =  5.99999999999994648725e-01,
L2  =  4.28571428578550184252e-01,
L3  =  3.33333329818377432918e-01,
L4  =  2.72728123808534006489e-01,
L5  =  2.30660745775561754067e-01,
L6  =  2.06975017800338417784e-01,
lg2  =  6.93147180559945286227e-01,
lg2_h  =  6.93147182464599609375e-01,
lg2_l  = -1.90465429995776804525e-09,
ovt =  8.0085662595372944372e-0017, /* -(1024-log2(ovfl+.5ulp)) */
cp    =  9.61796693925975554329e-01,
cp_h  =  9.61796700954437255859e-01,
cp_l  = -7.02846165095275826516e-09;


void logarithm_pair(double ax, double& t1, double& t2) {
    int32_t ix = int32_t(hi_word(ax)), n, j, k;
    double u,v,r,p_h,p_l,z_h,z_l,t;
            double ss,s2,s_h,s_l,t_h,t_l;
            n = 0;
        /* take care subnormal number */
            if(ix<0x00100000)
                {ax *= two53; n -= 53; GET_HIGH_WORD(ix,ax); }
            n  += ((ix)>>20)-0x3ff;
            j  = ix&0x000fffff;
        /* determine interval */
            ix = j|0x3ff00000;		/* normalize ix */
            if(j<=0x3988E) k=0;		/* |x|<sqrt(3/2) */
            else if(j<0xBB67A) k=1;	/* |x|<sqrt(3)   */
            else {k=0;n+=1;ix -= 0x00100000;}
            SET_HIGH_WORD(ax,ix);

        /* compute ss = s_h+s_l = (x-1)/(x+1) or (x-1.5)/(x+1.5) */
            u = ax-bp[k];		/* bp[0]=1.0, bp[1]=1.5 */
            v = one/(ax+bp[k]);
            ss = u*v;
            s_h = ss;
            SET_LOW_WORD(s_h,0);
        /* t_h=ax+bp[k] High */
            t_h = zero;
            SET_HIGH_WORD(t_h,((ix>>1)|0x20000000)+0x00080000+(k<<18));
            t_l = ax - (t_h-bp[k]);
            s_l = v*((u-s_h*t_h)-s_h*t_l);
        /* compute log(ax) */
            s2 = ss*ss;
            r = s2*s2*(L1+s2*(L2+s2*(L3+s2*(L4+s2*(L5+s2*L6)))));
            r += s_l*(s_h+ss);
            s2  = s_h*s_h;
            t_h = 3.0+s2+r;
            SET_LOW_WORD(t_h,0);
            t_l = r-((t_h-3.0)-s2);
        /* u+v = ss*(1+...) */
            u = s_h*t_h;
            v = s_l*t_h+t_l*ss;
        /* 2/(3log2)*(ss+...) */
            p_h = u+v;
            SET_LOW_WORD(p_h,0);
            p_l = v-(p_h-u);
            z_h = cp_h*p_h;		/* cp_h+cp_l = 2/(3*log2) */
            z_l = cp_l*p_h+p_l*cp+dp_l[k];
        /* log2(ax) = (ss+..)*2/(3*log2) = n + dp_h + z_h + z_l */
            t = (double)n;
            t1 = (((z_h+z_l)+dp_h[k])+t);
            SET_LOW_WORD(t1,0);
            t2 = z_l-(((t1-t)-dp_h[k])-z_h);
}
double exponential_reduced(double z, double w, int n) {
    return fixed_kernel::exponential(z,w,n);
}
double exponential_pair(double p_h, double p_l) {
    double z,t,u,v,w;
    int32_t i,j,k,n;
        z = p_l+p_h;
    if (z >= 1024.0) {
      if (z > 1024.0 || p_l + ovt > z-p_h) return infinity();
    } else if (z <= -1075.0) {
      if (z < -1075.0 || p_l <= z-p_h) return 0.0;
    }
    EXTRACT_WORDS(j,i,z);
    /*
     * compute 2**(p_h+p_l)
     */
        i = j&0x7fffffff;
        k = (i>>20)-0x3ff;
        n = 0;
        if(i>0x3fe00000) {		/* if |z| > 0.5, set n = [z+0.5] */
            n = int32_t(uint32_t(j)+(0x00100000U>>(k+1)));
            k = ((n&0x7fffffff)>>20)-0x3ff;	/* new k for n */
            t = zero;
            SET_HIGH_WORD(t,n&~(0x000fffff>>k));
            n = ((n&0x000fffff)|0x00100000)>>(20-k);
            if(j<0) n = -n;
            p_h -= t;
        }
        t = p_l+p_h;
        SET_LOW_WORD(t,0);
        u = t*lg2_h;
        v = (p_l-(t-p_h))*lg2+t*lg2_l;
        z = u+v;
        w = v-(z-u);
        return exponential_reduced(z,w,n);

}
MK61_M0_UNUSED_FALLBACK double evaluate(double x, double y)
{
        double z,ax,p_h,p_l;
        double y1,t1,t2,s,u;
        int32_t k,yisint,n; uint32_t j;
        int32_t hx,hy,ix,iy;
        uint32_t lx,ly;

        EXTRACT_WORDS(hx,lx,x);
        EXTRACT_WORDS(hy,ly,y);
        ix = hx&0x7fffffff;  iy = hy&0x7fffffff;

    /* y==zero: x**0 = 1 */
        if((iy|ly)==0) return one;

    /* x==1: 1**y = 1, even if y is NaN */
        if (hx==0x3ff00000 && lx == 0) return one;

    /* y!=zero: result is NaN if either arg is NaN */
        if(ix > 0x7ff00000 || ((ix==0x7ff00000)&&(lx!=0)) ||
           iy > 0x7ff00000 || ((iy==0x7ff00000)&&(ly!=0)))
                return (x+0.0)+(y+0.0);

    /* determine if y is an odd int when x < 0
     * yisint = 0	... y is not an integer
     * yisint = 1	... y is an odd int
     * yisint = 2	... y is an even int
     */
        yisint  = 0;
        if(hx<0) {
            if(iy>=0x43400000) yisint = 2; /* even integer y */
            else if(iy>=0x3ff00000) {
                k = (iy>>20)-0x3ff;	   /* exponent */
                if(k>20) {
                    j = ly>>(52-k);
                    if((j<<(52-k))==ly) yisint = 2-(j&1);
                } else if(ly==0) {
                    j = iy>>(20-k);
                    if((j<<(20-k))==uint32_t(iy)) yisint = 2-(j&1);
                }
            }
        }

    /* special value of y */
        if(ly==0) {
            if (iy==0x7ff00000) {	/* y is +-inf */
                if(((ix-0x3ff00000)|lx)==0)
                    return  one;	/* (-1)**+-inf is NaN */
                else if (ix >= 0x3ff00000)/* (|x|>1)**+-inf = inf,0 */
                    return (hy>=0)? y: zero;
                else			/* (|x|<1)**-,+inf = inf,0 */
                    return (hy<0)?-y: zero;
            }
            if(iy==0x3ff00000) {	/* y is  +-1 */
                if(hy<0) return one/x; else return x;
            }
            if(hy==0x40000000) return x*x;   /* y is  2 */
            if(hy==0x40080000) return x*x*x; /* y is  3 */
            if(hy==0x40100000) {             /* y is  4 */
                u = x*x;
                return u*u;
            }
            if(hy==0x3fe00000) {             /* y is  0.5 */
                if(hx>=0)	/* x >= +0 */
                    return sqrt(x);
            }
        }

        ax   = absolute(x);
    /* special value of x */
        if(lx==0) {
            if(ix==0x7ff00000||ix==0||ix==0x3ff00000){
                z = ax;			/*x is +-0,+-inf,+-1*/
                if(hy<0) z = one/z;	/* z = (1/|x|) */
                if(hx<0) {
                    if(((ix-0x3ff00000)|yisint)==0) {
                        z = (z-z)/(z-z); /* (-1)**non-int is NaN */
                    } else if(yisint==1)
                        z = -z;		/* (x<0)**odd = -(|x|**odd) */
                }
                return z;
            }
        }

    /* CYGNUS LOCAL + fdlibm-5.3 fix: This used to be
        n = (hx>>31)+1;
       but ANSI C says a right shift of a signed negative quantity is
       implementation defined.  */
        n = ((uint32_t)hx>>31)-1;

    /* (x<0)**(non-int) is NaN */
        if((n|yisint)==0) return (x-x)/(x-x);

        s = one; /* s (sign of result -ve**odd) = -1 else = 1 */
        if((n|(yisint-1))==0) s = -one;/* (-ve)**(odd int) */


    // One logarithm kernel serves pow, ln and log10. Its split result keeps
    // enough low bits for very large exponents near x=1.

    if (absolute(y) >= 0x1p64) {
      const bool grows = (ax > 1.0) == (y > 0.0);
      return s * (grows ? infinity() : 0.0);
    }
    logarithm_pair(ax,t1,t2);
    y1 = y;
    SET_LOW_WORD(y1,0);
    p_l = (y-y1)*t1+y*t2;
    p_h = y1*t1;
    // Avoid NaN from inf + -inf if a finite huge y overflows the product.
    if (!mk_math::is_finite(p_h)) {
      const bool grows = (ax > 1.0) == (y > 0.0);
      return s * (grows ? infinity() : 0.0);
    }
    return s * exponential_pair(p_h,p_l);
}

}

} // private kernels

#if !(defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI && (defined(__arm__) || defined(__thumb__)))
double sqrt(double x) { return square_root::evaluate(x); }
#endif

#if !(defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI && (defined(__arm__) || defined(__thumb__)))
double atan(double x) {
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && (defined(__arm__) || defined(__thumb__))
  return mk61_m0_atan(x);
#endif
  return arctangent::evaluate(x);
}
#endif

#if !(defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI && (defined(__arm__) || defined(__thumb__)))
double asin(double x) {
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && (defined(__arm__) || defined(__thumb__))
  return mk61_m0_asin(x);
#endif
  return arcsine::evaluate(x);
}
#endif

#if !(defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI && (defined(__arm__) || defined(__thumb__)))
double acos(double x) {
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && (defined(__arm__) || defined(__thumb__))
  return mk61_m0_acos(x);
#endif
  return arcsine::complement(x);
}
#endif

#if !(defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI && (defined(__arm__) || defined(__thumb__)))
double pow(double x, double y) {
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && (defined(__arm__) || defined(__thumb__))
  return mk61_m0_pow_fast(x,y);
#endif
  return power::evaluate(x,y);
}
#endif


double sin(double x) {
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && (defined(__arm__) || defined(__thumb__))
  return mk61_m0_trig(x,0);
#endif
  const uint32_t h = hi_word(x) & 0x7FFFFFFFU;
  if (h < 0x3E400000U) return x;
  if (h >= 0x7FF00000U) return x-x;
  if (h <= 0x3FE921FBU) return sine::evaluate(x,0.0,0);
  double r[2];
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && (defined(__arm__) || defined(__thumb__))
  const int mode=h<0x41300000U?mk61_m0_trig_medium(x,r,0):0;
  if(mode==1) return r[0];
  const int n=mode?mode>>2:argument::reduce(x,r);
#else
  const int n = argument::reduce(x,r);
#endif
  switch (n & 3) {
    case 0: return sine::evaluate(r[0],r[1],1);
    case 1: return cosine::evaluate(r[0],r[1]);
    case 2: return -sine::evaluate(r[0],r[1],1);
    default: return -cosine::evaluate(r[0],r[1]);
  }
}
double cos(double x) {
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && (defined(__arm__) || defined(__thumb__))
  return mk61_m0_trig(x,1);
#endif
  const uint32_t h = hi_word(x) & 0x7FFFFFFFU;
  if (h < 0x3E400000U) return 1.0;
  if (h >= 0x7FF00000U) return x-x;
  if (h <= 0x3FE921FBU) return cosine::evaluate(x,0.0);
  double r[2];
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && (defined(__arm__) || defined(__thumb__))
  const int mode=h<0x41300000U?mk61_m0_trig_medium(x,r,1):0;
  if(mode==1) return r[0];
  const int n=mode?mode>>2:argument::reduce(x,r);
#else
  const int n = argument::reduce(x,r);
#endif
  switch (n & 3) {
    case 0: return cosine::evaluate(r[0],r[1]);
    case 1: return -sine::evaluate(r[0],r[1],1);
    case 2: return -cosine::evaluate(r[0],r[1]);
    default: return sine::evaluate(r[0],r[1],1);
  }
}
double tan(double x) {
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && (defined(__arm__) || defined(__thumb__))
  return mk61_m0_trig(x,2);
#endif
  const uint32_t h = hi_word(x) & 0x7FFFFFFFU;
  if (h < 0x3E400000U) return x;
  if (h >= 0x7FF00000U) return x-x;
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && (defined(__arm__) || defined(__thumb__))
  double r[2]; r[0]=x; r[1]=0.0;
#else
  double r[2] = {x,0.0};
#endif
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && (defined(__arm__) || defined(__thumb__))
  const int mode=h>0x3FE921FBU && h<0x41300000U?mk61_m0_trig_medium(x,r,2):0;
  if(mode==1) return r[0];
  const int n=mode?mode>>2:h<=0x3FE921FBU?0:argument::reduce(x,r);
  double s,c;
  if((hi_word(r[0])&0x7FFFFFFFU)>=0x3F900000U) {
    double output[2];mk61_m0_sincos_reduced(r[0],r[1],output,3);s=output[0];c=output[1];
  } else {
    const double t=mk61_m0_tan_small(r[0],r[1]);return n&1?-1.0/t:t;
  }
#else
  const int n = h <= 0x3FE921FBU ? 0 : argument::reduce(x,r);
  const double s = sine::evaluate(r[0],r[1],r[1]!=0.0);
  const double c = cosine::evaluate(r[0],r[1]);
#endif
  return n & 1 ? -c/s : s/c;
}
#if !(defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI && (defined(__arm__) || defined(__thumb__)))
double ln(double x) {
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && (defined(__arm__) || defined(__thumb__))
  return mk61_m0_ln(x);
#else
  return natural_log::evaluate(x);
#endif
}
#endif

#if !(defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI && (defined(__arm__) || defined(__thumb__)))
double log10(double x) {
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && (defined(__arm__) || defined(__thumb__))
  return mk61_m0_log10(x);
#endif
  if (x == 0.0) return -infinity();
  if (x < 0.0) return nan(x);
  if (!mk_math::is_finite(x)) return x+x;
  uint32_t h = hi_word(x);
  if (h >= 0x3FE00000U && h < 0x40000000U)
    return 0x1.BCB7B1526E50Ep-2*natural_log::evaluate(x);
  int exponent = 0;
  if (h < 0x00100000U) {
    x *= 0x1p54;
    exponent = -54;
    h = hi_word(x);
  }
  exponent += int(h >> 20)-1023;
  const unsigned below_one = exponent < 0;
  x = set_high(x,(h & 0xFFFFFU) | ((1023U-below_one) << 20));
  const double k = double(exponent+int(below_one));
  return k*0x1.34413509F6000p-2 +
    (k*3.69423907715893078616e-13 +
     0x1.BCB7B1526E50Ep-2*natural_log::evaluate(x));
}
#endif

#if !(defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI && (defined(__arm__) || defined(__thumb__)))
double exp(double x) {
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && (defined(__arm__) || defined(__thumb__))
  return mk61_m0_exp(x);
#else
  if (!mk_math::is_finite(x)) return x < 0.0 ? 0.0 : x+x;
  if (x > 1024.0) return infinity();
  if (x < -1024.0) return 0.0;
  if (absolute(x) < 0x1p-28) return 1.0+x;
  int n = 0;
  double r = x, tail = 0.0;
  if (absolute(x) > 0.5*natural_log::ln2_hi) {
    n = int(x*0x1.71547652B82FEp0 + (x < 0.0 ? -0.5 : 0.5));
    const double h = x-n*natural_log::ln2_hi;
    const double l = n*natural_log::ln2_lo;
    r = h-l;
    tail = (h-r)-l;
  }
  return power::exponential_reduced(r,tail,n);
#endif
}
#endif

} // namespace compact_math
#undef MK61_M0_UNUSED_FALLBACK
#undef GET_HIGH_WORD
#undef GET_LOW_WORD
#undef EXTRACT_WORDS
#undef SET_HIGH_WORD
#undef SET_LOW_WORD
#undef INSERT_WORDS
#undef STRICT_ASSIGN
#endif
