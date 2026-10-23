// Exact last-stage midpoint comparison for y=p/q, |p|<=32, q<=32.
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
enum {N=216};
struct B {uint16_t w[N]{};unsigned used=1;};

// Multiplying the two coefficient powers needs at most (53+54)*32=3424
// bits. There are 3456 bits available; every multiply includes an overflow
// check so even a call outside the supported domain cannot corrupt memory.
static M0_POW_EXACT bool multiply(B& a,U factor) {
  uint16_t t[N+4]{};
  for(unsigned j=0;j<4;++j) {
    const uint32_t limb=uint16_t(factor>>(16*j));uint32_t carry=0;
    for(unsigned i=0;i<a.used;++i) {
      const uint32_t v=uint32_t(a.w[i])*limb+t[i+j]+carry;
      t[i+j]=uint16_t(v);carry=v>>16;
    }
    t[a.used+j]=uint16_t(carry);
  }
  for(unsigned i=N;i<N+4;++i) if(t[i]) return false;
  for(unsigned i=0;i<N;++i) a.w[i]=t[i];
  a.used=N;while(a.used>1 && !a.w[a.used-1]) --a.used;
  return true;
}

static M0_POW_EXACT unsigned width(const B& a) {
  uint32_t head=a.w[a.used-1];unsigned bits=16*(a.used-1);
  while(head) {head>>=1;++bits;}
  return bits;
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
    if(exponent>=6 || coefficient>(U(32)>>unsigned(exponent))) return false;
    p=unsigned(coefficient)<<unsigned(exponent);q=1;
  } else {
    if(exponent < -5 || coefficient>32) return false;
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
  B other;other.w[0]=1;
  if(inverse) {
    B combined=power;
    // x^(-p/q) < midpoint iff x^p * midpoint^q >1.
    for(unsigned i=0;i<q;++i) if(!multiply(combined,m)) return 2;
    return -compare(combined,scale+me*int(q),other,0);
  }
  for(unsigned i=0;i<q;++i) if(!multiply(other,m)) return 2;
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
  B power;power.w[0]=1;
  for(unsigned i=0;i<p;++i) if(!multiply(power,a)) return 0;
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
