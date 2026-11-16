// Exact last-stage midpoint comparison for y=p/q. Each integer
// coefficient is limited to 432 16-bit words after removing powers of two.
// Called only after the 1024-bit enclosure could not decide rounding.
// No floating-point operations, tables, allocation or global RAM are used.
#pragma once
#include <stdint.h>

#if defined(__arm__) || defined(__thumb__)
#define M0_POW_EXACT __attribute__((noinline,cold,section(".m0_pow_exact_extension")))
#else
#define M0_POW_EXACT
#endif

namespace m0_pow_exact {
using U=uint64_t;
enum {N=432, Capacity=16*N, MaxDenominatorShift=12};
struct B {uint16_t w[N]{};unsigned used=1;};

// Every multiply also checks for overflow. Copy back only the limbs in
// use; the cost is proportional to the actual exponent.
static M0_POW_EXACT bool multiply(B& a,U factor,unsigned words) {
  uint16_t t[N+4];
  const unsigned length=a.used+words;
  for(unsigned i=0;i<length;++i) t[i]=0;
  for(unsigned j=0;j<words;++j) {
    const uint32_t limb=uint16_t(factor>>(16*j));uint32_t carry=0;
    for(unsigned i=0;i<a.used;++i) {
      const uint32_t v=uint32_t(a.w[i])*limb+t[i+j]+carry;
      t[i+j]=uint16_t(v);carry=v>>16;
    }
    t[a.used+j]=uint16_t(carry);
  }
  for(unsigned i=N;i<length;++i) if(t[i]) return false;
  unsigned used=length;
  if(used>N) used=N;
  while(used>1 && !t[used-1]) --used;
  for(unsigned i=0;i<used;++i) a.w[i]=t[i];
  a.used=used;
  return true;
}

static M0_POW_EXACT unsigned width(const B& a) {
  uint32_t head=a.w[a.used-1];unsigned bits=16*(a.used-1);
  while(head) {head>>=1;++bits;}
  return bits;
}

static M0_POW_EXACT bool multiply_power(B& a,U factor,unsigned exponent) {
  if(factor==1) return true;
  unsigned bits=0;
  for(U n=factor;n;n>>=1) ++bits;
  // Each multiplication gains at least floor(log2(factor)) bits. If
  // that lower bound fits, the product still checks each actual carry.
  if(exponent*(bits-1)>Capacity-width(a)) return false;
  const unsigned words=(bits+15)/16;
  for(unsigned i=0;i<exponent;++i) if(!multiply(a,factor,words)) return false;
  return true;
}

static M0_POW_EXACT int compare(const B& a,int ae,const B& b,int be) {
  const unsigned aw=width(a),bw=width(b);
  const int at=int(aw)+ae,bt=int(bw)+be;
  if(at!=bt) return at<bt?-1:1;
  const unsigned length=aw>bw?aw:bw;
  for(unsigned i=0;i<length;++i) {
    const unsigned ai=aw>i?aw-1-i:0,bi=bw>i?bw-1-i:0;
    const unsigned av=aw>i?((a.w[ai/16]>>(ai%16))&1U):0;
    const unsigned bv=bw>i?((b.w[bi/16]>>(bi%16))&1U):0;
    if(av!=bv) return av<bv?-1:1;
  }
  return 0;
}

static M0_POW_EXACT void decode(U bits,U& coefficient,int& exponent) {
  const unsigned field=unsigned(bits>>52);
  coefficient=bits&UINT64_C(0x000FFFFFFFFFFFFF);
  exponent=-1074;
  if(field) {coefficient|=U(1)<<52;exponent=int(field)-1075;}
}

static M0_POW_EXACT bool parameters(U y,unsigned& p,unsigned& q) {
  const U magnitude=y&UINT64_C(0x7FFFFFFFFFFFFFFF);
  if(!magnitude || magnitude>=UINT64_C(0x7FF0000000000000)) return false;
  U coefficient;int exponent;decode(magnitude,coefficient,exponent);
  while(!(coefficient&1)) {coefficient>>=1;++exponent;}
  if(exponent>=0) {
    if(exponent>=32 || coefficient>(unsigned(Capacity)>>unsigned(exponent))) return false;
    p=unsigned(coefficient)<<unsigned(exponent);q=1;
  } else {
    if(exponent < -MaxDenominatorShift || coefficient>Capacity) return false;
    p=unsigned(coefficient);q=1U<<unsigned(-exponent);
  }
  return true;
}

static M0_POW_EXACT bool midpoint(U lower,U upper,U& coefficient,int& exponent) {
  const U infinity=UINT64_C(0x7FF0000000000000);
  if(upper>infinity || upper!=lower+1) return false;
  if(upper==infinity) {coefficient=(U(1)<<54)-1;exponent=970;return true;}
  U a,b;int ae,be;decode(lower,a,ae);decode(upper,b,be);
  if(be<ae || be-ae>1) return false;
  coefficient=a+(b<<unsigned(be-ae));exponent=ae-1;
  return true;
}

static M0_POW_EXACT int relation(const B& power,int scale,unsigned q,bool inverse,U m,int me) {
  if(inverse) {
    B combined=power;
    // x^(-p/q) < midpoint iff x^p * midpoint^q >1.
    if(!multiply_power(combined,m,q)) return 2;
    const int high=int(width(combined))-1+scale+me*int(q);
    if(high) return high>0?-1:1;
    // Both factors are odd. The product is a power of two only if it is one.
    return combined.used==1 && combined.w[0]==1?0:-1;
  }
  B other;other.w[0]=1;
  if(!multiply_power(other,m,q)) return 2;
  return compare(power,scale,other,me*int(q));
}

// -1 means that the correctly rounded encoding is <=cell, +1 means that
// it is >=cell+1. Midpoint ties are decided here by the encoding parity.
static M0_POW_EXACT int rounding_side(const B& power,int scale,unsigned q,bool inverse,U cell) {
  U m;int me;if(!midpoint(cell,cell+1,m,me)) return 2;
  const int order=relation(power,scale,q,inverse,m,me);
  return order?order:((cell&1)?1:-1);
}
}

// The caller initializes *result with any unsigned word as a search hint.
// Two exact boundary checks usually finish a hint near the answer. An invalid
// or distant hint retains a bounded binary search over positive encodings:
// at most 65 exact comparisons, including subnormal and overflow boundaries.
// No approximation or enclosure assumption is needed to accept the hint.
extern "C" M0_POW_EXACT int mk61_m0_pow_exact_small(uint64_t x,uint64_t y,uint64_t* result) {
  using namespace m0_pow_exact;
  const U infinity=UINT64_C(0x7FF0000000000000);
  if(!x || x>=infinity) return 0;
  unsigned p,q;if(!parameters(y,p,q)) return 0;
  U a;int ae;decode(x,a,ae);
  while(!(a&1)) {a>>=1;++ae;}
  B power;power.w[0]=1;
  if(!multiply_power(power,a,p)) return 0;
  U lower=0,upper=infinity;
  const U hint=*result;
  if(hint<infinity) {
    const int side=rounding_side(power,ae*int(p),q,bool(y>>63),hint);
    if(side==2) return 0;
    if(side<0) {
      upper=hint;
      if(hint) {
        const int previous=rounding_side(power,ae*int(p),q,bool(y>>63),hint-1);
        if(previous==2) return 0;
        if(previous>0) lower=hint;
        else upper=hint-1;
      }
    } else {
      lower=hint+1;
      if(lower<infinity) {
        const int next=rounding_side(power,ae*int(p),q,bool(y>>63),lower);
        if(next==2) return 0;
        if(next<0) upper=lower;
        else ++lower;
      }
    }
  }
  while(lower<upper) {
    const U cell=lower+((upper-lower)>>1);
    const int side=rounding_side(power,ae*int(p),q,bool(y>>63),cell);
    if(side==2) return 0;
    if(side<0) upper=cell;
    else lower=cell+1;
  }
  *result=lower;
  return 1;
}
#undef M0_POW_EXACT
