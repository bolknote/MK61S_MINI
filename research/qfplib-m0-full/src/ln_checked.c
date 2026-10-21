/* SPDX-License-Identifier: GPL-2.0-only */
/* MK61S independent research, 2026-10-21. Interval-certified logarithm.
 * No floating point arithmetic, libgcc, heap, or mutable static storage.
 * The finite Q245 fallback limit remains an explicit research limitation.
 */
#include <stdint.h>
#include "ln_constants.inc"

typedef union { double d; struct {uint32_t lo,hi;} w; } Binary64;
typedef struct {uint32_t v[8];} Big;
extern double qfp_dln(double);
#ifdef QFP_COMPENSATED_LN
extern void qfp_ln_comp96(uint32_t,uint32_t,uint32_t[4]);
#else
extern void qfp_ln_fast96(uint32_t,uint32_t,uint32_t[4]);
#endif

static uint32_t clz(uint32_t x) {
  uint32_t n=0;
  if(!(x>>16)){n=16;x<<=16;}
  if(!(x>>24)){n+=8;x<<=8;}
  if(!(x>>28)){n+=4;x<<=4;}
  if(!(x>>30)){n+=2;x<<=2;}
  return n+(!(x>>31));
}
static void zero(Big *a,unsigned w){for(unsigned i=0;i<w;++i)a->v[i]=0;}
static void copy(Big *a,const Big *b,unsigned w){for(unsigned i=0;i<w;++i)a->v[i]=b->v[i];}
static void neg(Big *a,unsigned w){
  uint32_t carry=1;
  for(unsigned i=0;i<w;++i){uint32_t x=~a->v[i],y=x+carry;a->v[i]=y;carry=y<x;}
}
static void add(Big *a,const Big *b,unsigned w){
  uint32_t carry=0;
  for(unsigned i=0;i<w;++i){uint32_t x=a->v[i]+carry,c=x<a->v[i],y=x+b->v[i];a->v[i]=y;carry=c|(y<x);}
}
static void sub(Big *a,const Big *b,unsigned w){
  uint32_t borrow=0;
  for(unsigned i=0;i<w;++i){uint32_t x=a->v[i]-borrow,c=x>a->v[i],y=x-b->v[i];a->v[i]=y;borrow=c|(y>x);}
}
static void small_add(Big *a,uint32_t n,unsigned w){
  for(unsigned i=0;i<w&&n;++i){uint32_t before=a->v[i];a->v[i]+=n;n=a->v[i]<before;}
}
static void small_sub(Big *a,uint32_t n,unsigned w){
  for(unsigned i=0;i<w&&n;++i){uint32_t before=a->v[i];a->v[i]-=n;n=a->v[i]>before;}
}
static int nonzero(const Big *a,unsigned w){for(unsigned i=0;i<w;++i)if(a->v[i])return 1;return 0;}
static void shift(Big *out,const Big *a,unsigned n,unsigned w){
  for(unsigned i=0;i<w;++i)out->v[i]=(a->v[i]>>n)|(i+1<w?a->v[i+1]<<(32-n):0);
}
static void constant(Big *a,unsigned index,unsigned w){for(unsigned i=0;i<w;++i)a->v[i]=ln245[index][i+8-w];}
static void multiply_small(Big *a,uint32_t n,unsigned w){
  uint32_t carry=0;
  for(unsigned i=0;i<w;++i){
    uint32_t lo=(a->v[i]&65535)*n,hi=(a->v[i]>>16)*n+(lo>>16);
    uint32_t x=(lo&65535)|(hi<<16),y=x+carry;
    a->v[i]=y;carry=(hi>>16)+(y<x);
  }
}
static uint32_t mul_hi(uint32_t a,uint32_t b,uint32_t *low){
  uint32_t al=a&65535,ah=a>>16,bl=b&65535,bh=b>>16;
  uint32_t p=al*bl,t=ah*bl+(p>>16),u=al*bh+(t&65535);
  *low=(p&65535)|(u<<16);
  return ah*bh+(t>>16)+(u>>16);
}
#ifdef QFP_NEAR_LN
/* uint64 operations below are only addition and constant shifts; products
 * use explicit 16-bit limbs, so Cortex-M0 needs no libgcc helpers. */
__attribute__((always_inline)) static inline uint64_t near_wide(uint32_t a,uint32_t b){
  uint32_t al=a&65535,ah=a>>16,bl=b&65535,bh=b>>16;
  uint32_t p=al*bl,t=ah*bl+(p>>16),u=al*bh+(t&65535);
  uint32_t lo=(p&65535)|(u<<16),hi=ah*bh+(t>>16)+(u>>16);
  return ((uint64_t)hi<<32)|lo;
}
static uint64_t near_square(uint64_t a){
  uint32_t lo=(uint32_t)a,hi=(uint32_t)(a>>32);
  uint64_t ll=near_wide(lo,lo),hl=near_wide(hi,lo),hh=near_wide(hi,hi);
  return ((((ll>>32)+(hl<<1))>>32)+hh)>>2;
}
static uint64_t near_third(uint64_t a){
  uint64_t q=near_wide((uint32_t)(a>>32),0x55555555u)+(near_wide((uint32_t)a,0x55555555u)>>32);
  uint32_t r=(uint32_t)(a-q-(q<<1));
  return q+((r*0xaaabu)>>17);
}
static uint32_t near_cube(uint64_t z,uint32_t a){
  uint64_t lo=near_wide((uint32_t)z,a),hi=near_wide((uint32_t)(z>>32),a);
  uint64_t mid=(lo>>32)+(uint32_t)hi;
  return ((uint32_t)mid>>12)|((uint32_t)((hi>>32)+(mid>>32))<<20);
}
static uint64_t near_product(uint64_t a,uint64_t b,uint32_t negative){
  /* The normalized difference from1 has at most42 significant input bits:
   * a.low is a multiple of2^21. Its two low-limb products need only four
   * narrow MULS instead of eight, preserving the exact high64. */
  uint32_t u=(uint32_t)a>>21,ah=(uint32_t)(a>>32),bl=(uint32_t)b,bh=(uint32_t)(b>>32);
  uint32_t ll=((u*(bl&65535))>>11)+((u*(bl>>16))<<5);
  uint32_t c0=u*(bh&65535),c1=u*(bh>>16);
  uint64_t cross=c0+((uint64_t)c1<<16); /* Explicit34-bit cross term. */
  uint64_t hl=near_wide(ah,bl),hh=near_wide(ah,bh);
  uint64_t mid=(uint64_t)ll+(uint32_t)(cross<<21)+(uint32_t)hl;
  uint64_t high=hh+(cross>>11)+(hl>>32)+(mid>>32);
  return (high+2+negative)>>2;   /* RN or3/4 bias at the Q66 product scale. */
}
static uint32_t near_divide5(uint32_t a){
  uint32_t hi=a>>16;
  return hi*13107+((((a&65535)+hi)*52429u)>>18);
}
/* Seed for x within1+-2^-11, x!=1: magnitude q, bit index of a=|x-1|Q66,
 * sign. True ln(x) lies within +-1 unit at precision(128-bit_index). */
__attribute__((noinline)) void qfp_ln_near_seed66(uint32_t lo,uint32_t hi,uint32_t out[4]){
  uint32_t negative=hi<0x3ff00000u,al,ah;
  if(negative){
    uint32_t dl=0u-lo,dh=0x3ff00000u-hi-(lo!=0);
    al=dl<<13;ah=(dh<<13)|(dl>>19);
  }else{al=lo<<14;ah=((hi-0x3ff00000u)<<14)|(lo>>18);}
  unsigned bit=ah?63-clz(ah):31-clz(al),s=62-bit;
  uint32_t ql,qh;
  if(s<32){ql=al<<s;qh=(ah<<s)|(al>>(32-s));}
  else{ql=0;qh=al<<(s-32);}
  uint64_t a=((uint64_t)ah<<32)|al;
  uint64_t z=near_square(a);
  uint32_t ar=(uint32_t)((a+(1u<<23))>>24),cube=near_cube(z,ar);
  uint32_t zr=(uint32_t)((z+(1u<<18))>>19);
  uint32_t fourth=(uint32_t)(near_wide(zr,zr)>>28);
  uint32_t fifth=(uint32_t)(near_wide(fourth,ar)>>42);
  uint64_t even=near_third(z)+near_divide5(fourth);
  uint64_t odd=(a>>1)+cube+((fifth*0xaaabu)>>18);
  uint64_t deviation=negative?odd+even:odd-even;
  uint64_t q=((uint64_t)qh<<32)|ql,change=near_product(q,deviation,negative);
  q=negative?q+change:q-change;
  out[0]=(uint32_t)q;out[1]=(uint32_t)(q>>32);out[2]=bit;out[3]=negative;
}
static int near_fast(uint32_t lo,uint32_t hi,Binary64 *out){
  uint32_t seed[4];qfp_ln_near_seed66(lo,hi,seed);
  lo=seed[0];hi=seed[1];unsigned s=hi>>31?11:hi>>30?10:9;
  uint32_t half=1u<<(s-1),tail=lo&((1u<<s)-1);
  if(tail-(half-1)<=2)return 0;
  uint32_t ql=(lo>>s)|(hi<<(32-s)),qh=hi>>s,before=ql;
  ql+=tail>half;qh+=ql<before;
  out->w.lo=ql;out->w.hi=(seed[3]<<31)+((s+seed[2]+946)<<20)+qh;
  return 1;
}
#endif
static void multiply(Big *out,const Big *a,const Big *b,unsigned w){
  uint32_t p[16];for(unsigned i=0;i<2*w;++i)p[i]=0;
  unsigned aw=w,bw=w;
  while(aw&&!a->v[aw-1])--aw;
  while(bw&&!b->v[bw-1])--bw;
  for(unsigned i=0;i<aw;++i)for(unsigned j=0;j<bw;++j){
    uint32_t lo,hi=mul_hi(a->v[i],b->v[j],&lo),old=p[i+j];
    p[i+j]+=lo;uint32_t carry=p[i+j]<old;
    unsigned k=i+j+1;old=p[k];p[k]+=hi;uint32_t c=p[k]<old;
    old=p[k];p[k]+=carry;carry=c|(p[k]<old);
    while(carry&&++k<2*w){old=p[k];++p[k];carry=p[k]<old;}
  }
  /* P=w*32-11 (Q117/Q245), so shift a full product by P. */
  for(unsigned i=0;i<w;++i)out->v[i]=(p[i+w-1]>>21)|(p[i+w]<<11);
}
static void divide_small(Big *a,uint32_t d,unsigned w){
  if(d==2||d==4||d==8){
    unsigned s=d==2?1:d==4?2:3;
    for(unsigned i=0;i<w;++i)a->v[i]=(a->v[i]>>s)|(i+1<w?a->v[i+1]<<(32-s):0);
    return;
  }
  uint32_t reciprocal;
  /* Only d=2..12. Floor reciprocal; quotient is corrected after MUL-high. */
  switch(d){
    case 2:reciprocal=0x80000000u;break;case 3:reciprocal=0x55555555u;break;
    case 4:reciprocal=0x40000000u;break;case 5:reciprocal=0x33333333u;break;
    case 6:reciprocal=0x2aaaaaaau;break;case 7:reciprocal=0x24924924u;break;
    case 8:reciprocal=0x20000000u;break;case 9:reciprocal=0x1c71c71cu;break;
    case 10:reciprocal=0x19999999u;break;case 11:reciprocal=0x1745d174u;break;
    default:reciprocal=0x15555555u;break;
  }
  uint32_t rem=0;
  unsigned digits=2*w;
  while(digits&&!((a->v[(digits-1)>>1]>>(((digits-1)&1)*16))&65535))--digits;
  for(unsigned j=digits;j;--j){
    unsigned i=(j-1)>>1,s=((j-1)&1)*16;
    uint32_t digit=(a->v[i]>>s)&65535,v=(rem<<16)|digit,unused;
    uint32_t q=mul_hi(v,reciprocal,&unused);
    rem=v-q*d;if(rem>=d){rem-=d;++q;}
    a->v[i]=(a->v[i]&~(65535u<<s))|(q<<s);
  }
}

/* Pack an exact signed fixed point integer. Input/result are always normal
 * in the logarithm domain, or zero; no floating point operations are used. */
static Binary64 pack(Big a,unsigned w,unsigned precision){
  Binary64 out;uint32_t sign=a.v[w-1]>>31;
  if(sign)neg(&a,w);
  unsigned top=w;while(top&&!a.v[top-1])--top;
  if(!top){out.w.lo=0;out.w.hi=sign<<31;return out;}
  unsigned width=32*top-clz(a.v[top-1]);
  int s=(int)width-53;
  uint32_t lo,hi,round=0;
  if(s>0){
    unsigned word=(unsigned)s>>5,bit=(unsigned)s&31;
    lo=a.v[word]>>bit;hi=word+1<w?a.v[word+1]>>bit:0;
    if(bit){if(word+1<w)lo|=a.v[word+1]<<(32-bit);if(word+2<w)hi|=a.v[word+2]<<(32-bit);}
    unsigned guard=(unsigned)(s-1),gi=guard>>5,gb=guard&31;
    uint32_t sticky=a.v[gi]&((1u<<gb)-1);
    for(unsigned i=0;i<gi;++i)sticky|=a.v[i];
    round=((a.v[gi]>>gb)&1)&&(sticky||(lo&1));
  }else{
    unsigned left=(unsigned)-s;
    lo=left<32?a.v[0]<<left:0;
    hi=left<32?(a.v[1]<<left)|(left?a.v[0]>>(32-left):0):a.v[0]<<(left-32);
  }
  uint32_t before=lo;lo+=round;hi+=lo<before;
  out.w.lo=lo;
  out.w.hi=(sign<<31)+((width-precision+1021)<<20)+hi;
  return out;
}

__attribute__((noinline)) static int pack_fast(const uint32_t in[4],Binary64 *out){
  uint32_t v[3],sign=in[2]>>31,carry=sign;
  for(unsigned i=0;i<3;++i){uint32_t x=in[i]^(0u-sign),y=x+carry;v[i]=y;carry=y<x;}
  unsigned width=v[2]?96-clz(v[2]):v[1]?64-clz(v[1]):v[0]?32-clz(v[0]):0;
  unsigned precision=62;uint32_t error=in[3];
#ifdef QFP_COMPENSATED_LN
  precision=82;
  /* All log magnitudes fit signed96 Q82. Reduce wide values by8 bits so
   * the complete rounding tail fits one word; include truncation in error. */
  if(width>84){
    v[0]=(v[0]>>8)|(v[1]<<24);v[1]=(v[1]>>8)|(v[2]<<24);v[2]>>=8;
    width-=8;precision-=8;error=(error>>8)+!!(error&255)+1;
  }
#endif
  if(width<=53)return 0;
  unsigned s=width-53;uint32_t half=1u<<(s-1);
  if(error>=half)return 0;
  uint32_t tail=v[0]&((1u<<s)-1);
  if(tail-(half-error)<=2*error)return 0;
  uint32_t lo=(v[0]>>s)|(v[1]<<(32-s));
  uint32_t hi=(v[1]>>s)|(v[2]<<(32-s)),before=lo;
  /* Below an exact power of two the adjacent binade has half the spacing.
   * Its rounding midpoint must also lie outside the certified interval. */
  if(hi==0x100000u&&!lo&&tail+(half>>1)<=error)return 0;
  lo+=tail>half;hi+=lo<before;
  out->w.lo=lo;out->w.hi=(sign<<31)+((width-precision+1021)<<20)+hi;
  return 1;
}

/* Higher precision repeats the same 24 greedy reductions. Constant floors,
 * rounded shifts, product floors and polynomial truncation are included in
 * the symmetric (96+|e+1|) interval, in Q117 or Q245 units. */
__attribute__((noinline)) static int refine(uint32_t lo,uint32_t hi,unsigned w,Binary64 *out){
  int exponent=(int)(hi>>20)-1023;
  hi=(hi&0xfffff)|0x100000;
  if(exponent==-1023){
    hi&=0xfffff;exponent=-1022;
    while(!(hi&0x100000)){hi=(hi<<1)|(lo>>31);lo<<=1;--exponent;}
  }
  unsigned precision=32*w-11;
  Big x,y,t,u,d,term,sum;
  zero(&x,w);zero(&y,w);
  /* m/2 at Q(P): mantissa's shift is P-53 = w*32-64. */
  x.v[w-2]=lo;x.v[w-1]=hi;
  for(unsigned i=1;i<=24;++i){
    shift(&t,&x,i,w);
    small_add(&t,(x.v[0]>>(i-1))&1,w);
    add(&t,&x,w);
    if(t.v[w-1]<(1u<<21)){
      copy(&x,&t,w);constant(&u,i,w);sub(&y,&u,w);
    }
  }
  zero(&d,w);d.v[w-1]=1u<<21;sub(&d,&x,w);
  copy(&term,&d,w);copy(&sum,&d,w);
  unsigned count=w==4?7:12;
  for(unsigned i=2;i<=count;++i){
    multiply(&t,&term,&d,w);copy(&term,&t,w);
    if(!nonzero(&term,w))break;
    copy(&u,&term,w);divide_small(&u,i,w);add(&sum,&u,w);
  }
  sub(&y,&sum,w);
  constant(&t,0,w);
  int n=exponent+1;uint32_t mag=n<0?(uint32_t)-n:(uint32_t)n;
  multiply_small(&t,mag,w);if(n<0)neg(&t,w);add(&y,&t,w);
  uint32_t error=96+mag;
  copy(&t,&y,w);copy(&u,&y,w);small_sub(&t,error,w);small_add(&u,error,w);
  Binary64 lower=pack(t,w,precision),upper=pack(u,w,precision);
  if(lower.w.lo!=upper.w.lo||lower.w.hi!=upper.w.hi)return 0;
  *out=lower;return 1;
}

double qfp_dln_checked(double argument){
  Binary64 input,out;input.d=argument;uint32_t lo=input.w.lo,hi=input.w.hi;
  /* Exact existing near-one path and corrected IEEE special paths. */
  if(hi>>31||hi>=0x7ff00000u||(!(hi|lo))||
     (hi==0x3ff00000u&&lo<32768)||
     (hi==0x3fefffffu&&lo>=0xffff0001u))return qfp_dln(argument);
#ifdef QFP_NEAR_LN
  if(hi>=0x3feffc00u&&(hi<0x3ff00200u||(hi==0x3ff00200u&&!lo))){
    if(near_fast(lo,hi,&out))return out.d;
    goto precise;
  }
#endif
  uint32_t fast[4];
#ifdef QFP_COMPENSATED_LN
  qfp_ln_comp96(lo,hi,fast);
#else
  qfp_ln_fast96(lo,hi,fast);
#endif
  if(pack_fast(fast,&out))return out.d;
#ifdef QFP_NEAR_LN
precise:
#endif
  if(refine(lo,hi,4,&out)||refine(lo,hi,8,&out))return out.d;
  /* Not certified as total: retain an explicit undecided status, never
   * silently return an unproved rounding. No production caller uses this. */
  __builtin_trap();
}
