// Last-stage directed fixed-point refinement of the positive pow magnitude.
// The caller handles special values/domain/sign. Each return requires an
// exact dyadic result or a complete interval inside one binary64 RNE cell.
#pragma once
#include <stdint.h>
#include <stddef.h>

namespace m0_pow_interval {
using U=uint64_t;
// Exact floor(ln(2)*2^1024); certify_m0_pow_interval.py checks the enclosure.
#include "native_eabi_m0_pow_interval_table.inc"

template<unsigned P> struct Fixed {
  static_assert(P==512 || P==1024,"certified ln2 slices");
  enum {F=P/16,N=F+4};
  struct B {uint16_t w[N]{};};
  struct I {B lo,hi;};
  struct S {B mag;bool negative=false;};
  static B integer(uint32_t x) {B a;a.w[F]=uint16_t(x);a.w[F+1]=uint16_t(x>>16);return a;}
  static B ulp() {B a;a.w[0]=1;return a;}
  static int compare(const B& a,const B& b) {
    for(unsigned i=N;i--;) if(a.w[i]!=b.w[i]) return a.w[i]>b.w[i]?1:-1;
    return 0;
  }
  static bool zero(const B& a) {for(unsigned i=0;i<N;++i) if(a.w[i]) return false;return true;}
  static B add(const B& a,const B& b) {
    B r;uint32_t carry=0;
    for(unsigned i=0;i<N;++i) {const uint32_t s=uint32_t(a.w[i])+b.w[i]+carry;r.w[i]=uint16_t(s);carry=s>>16;}
    if(carry) __builtin_trap();
    return r;
  }
  static B subtract(const B& a,const B& b) {
    if(compare(a,b)<0) __builtin_trap();
    B r;uint32_t borrow=0;
    for(unsigned i=0;i<N;++i) {const uint32_t t=uint32_t(b.w[i])+borrow;r.w[i]=uint16_t(a.w[i]-t);borrow=a.w[i]<t;}
    return r;
  }
  static B increment(const B& a) {return add(a,ulp());}
  static B product(const B& a,const B& b,bool upward) {
    uint16_t t[2*N]{};
    for(unsigned i=0;i<N;++i) {
      uint32_t carry=0;
      for(unsigned j=0;j<N;++j) {
        // (2^16-1)^2 + two 16-bit carries <=2^32-1.
        const uint32_t p=uint32_t(a.w[i])*b.w[j]+t[i+j]+carry;
        t[i+j]=uint16_t(p);carry=p>>16;
      }
      t[i+N]=uint16_t(carry);
    }
    B r;bool lost=false;
    for(unsigned i=0;i<F;++i) lost|=t[i]!=0;
    for(unsigned i=0;i<N;++i) r.w[i]=t[i+F];
    for(unsigned i=N+F;i<2*N;++i) if(t[i]) __builtin_trap();
    return upward&&lost?increment(r):r;
  }
  static B times(const B& a,U m) {
    uint16_t t[N+4]{};
    for(unsigned j=0;j<4;++j) {
      const uint32_t v=uint16_t(m>>(16*j));uint32_t carry=0;
      for(unsigned i=0;i<N;++i) {
        const uint32_t p=uint32_t(a.w[i])*v+t[i+j]+carry;
        t[i+j]=uint16_t(p);carry=p>>16;
      }
      t[N+j]=uint16_t(carry);
    }
    B r;for(unsigned i=0;i<N;++i) r.w[i]=t[i];
    for(unsigned i=N;i<N+4;++i) if(t[i]) __builtin_trap();
    return r;
  }
  static B divide(const B& a,uint32_t d,bool upward) {
    if(!d || d>=65536) __builtin_trap();
    B r;uint32_t rem=0;
    for(unsigned i=N;i--;) {
      const uint32_t n=(rem<<16)|a.w[i],q=n/d;
      r.w[i]=uint16_t(q);rem=n-q*d;
    }
    return upward&&rem?increment(r):r;
  }
  static bool bit(const B& a,unsigned b) {return b<16*N && ((a.w[b/16]>>(b%16))&1);}
  static bool any_below(const B& a,unsigned b) {
    const unsigned whole=b/16,part=b%16;
    for(unsigned i=0;i<N && i<whole;++i) if(a.w[i]) return true;
    return whole<N && part && (a.w[whole]&((1U<<part)-1));
  }
  static U shifted64(const B& a,unsigned shift) {
    const unsigned base=shift/16,bits=shift%16;U v=0;
    for(unsigned i=0;i<4 && base+i<N;++i) v|=U(a.w[base+i])<<(16*i);
    v>>=bits;
    if(bits && base+4<N) v|=U(a.w[base+4])<<(64-bits);
    return v;
  }
  static B shift(const B& a,int count,bool upward) {
    if(!count) return a;
    B r;
    if(count<0) {
      const unsigned s=unsigned(-count),whole=s/16,part=s%16;
      for(unsigned i=0;i<N && i+whole<N;++i) {
        uint32_t v=a.w[i+whole]>>part;
        if(part && i+whole+1<N) v|=uint32_t(a.w[i+whole+1])<<(16-part);
        r.w[i]=uint16_t(v);
      }
      return upward&&any_below(a,s)?increment(r):r;
    }
    const unsigned whole=unsigned(count)/16,part=unsigned(count)%16;
    if(count>=16*N) {if(!zero(a)) __builtin_trap();return r;}
    for(unsigned i=0;i<N;++i) {
      if(i+whole>=N) {if(a.w[i]) __builtin_trap();continue;}
      const uint32_t v=uint32_t(a.w[i])<<part;
      r.w[i+whole]|=uint16_t(v);
      if(part && i+whole+1<N) r.w[i+whole+1]|=uint16_t(v>>16);
      else if(v>>16) __builtin_trap();
    }
    return r;
  }
  static I ratio(U numerator,U denominator) {
    B r;U rem=numerator;
    for(unsigned i=P;i--;) {rem<<=1;if(rem>=denominator) {rem-=denominator;r.w[i/16]|=uint16_t(1U<<(i%16));}}
    return {r,rem?increment(r):r};
  }
  static I ln2() {
    B lo;for(unsigned i=0;i<F;++i) lo.w[i]=ln2_1024[(1024-P)/16+i];return {lo,increment(lo)};
  }
  static I log_mantissa(U significand) {
    const U hidden=U(1)<<52;
    const I t=ratio(significand-hidden,significand+hidden);
    const I square={product(t.lo,t.lo,false),product(t.hi,t.hi,true)};
    I power=t,sum{};
    for(unsigned n=0;n<P+16;++n) {
      sum.lo=add(sum.lo,divide(power.lo,2*n+1,false));
      sum.hi=add(sum.hi,divide(power.hi,2*n+1,true));
      power={product(power.lo,square.lo,false),product(power.hi,square.hi,true)};
      if(compare(power.hi,ulp())<=0) {
        // 2*sum omitted powers/(odd) <= (9/4)*next_power <4*next_power.
        return {times(sum.lo,2),add(times(sum.hi,2),times(power.hi,4))};
      }
    }
    __builtin_trap();
  }
  static void normalize(U a,U& significand,int& exponent) {
    significand=a&((U(1)<<52)-1);exponent=int(a>>52)-1023;
    if(a>>52) significand|=U(1)<<52;
    else {exponent=-1022;while(significand && significand<(U(1)<<52)) {significand<<=1;--exponent;}}
  }
  static S difference(const B& a,const B& b) {
    const bool negative=compare(a,b)<0;return {negative?subtract(b,a):subtract(a,b),negative};
  }
  static S negate(S a) {if(!zero(a.mag)) a.negative=!a.negative;return a;}
  static I exp_endpoint(const S& x) {
    const B one=integer(1);I term={one,one},sum=term;
    for(unsigned n=1;n<P+16;++n) {
      term={divide(product(term.lo,x.mag,false),n,false),divide(product(term.hi,x.mag,true),n,true)};
      if(x.negative && (n&1)) {sum.lo=subtract(sum.lo,term.hi);sum.hi=subtract(sum.hi,term.lo);}
      else {sum.lo=add(sum.lo,term.lo);sum.hi=add(sum.hi,term.hi);}
      if(compare(term.hi,ulp())<=0) {
        // |x|<1/2. The remaining positive Taylor tail is <2*term;
        // the alternating tail is bounded by term in both directions.
        if(x.negative) return {subtract(sum.lo,term.hi),add(sum.hi,term.hi)};
        return {sum.lo,add(sum.hi,times(term.hi,2))};
      }
    }
    __builtin_trap();
  }
  static U rounded(const B& a,int scale) {
    unsigned width=0;
    for(unsigned i=N;i--;) if(a.w[i]) {uint32_t v=a.w[i];width=16*i;while(v) {++width;v>>=1;}break;}
    if(!width) return 0;
    const int exponent=int(width)-1-int(P)+scale;
    if(exponent>1023) return UINT64_C(0x7FF0000000000000);
    const unsigned discarded=exponent < -1022?unsigned(int(P)-scale-1074):width-53;
    U retained=shifted64(a,discarded);
    if(discarded && bit(a,discarded-1) && (any_below(a,discarded-1) || (retained&1))) ++retained;
    if(exponent < -1022) return retained;
    const U result=(U(exponent+1022)<<52)+retained;
    return result>UINT64_C(0x7FF0000000000000)?UINT64_C(0x7FF0000000000000):result;
  }
  static U word_product(uint32_t a,uint32_t b) {
    const uint32_t al=a&65535,ah=a>>16,bl=b&65535,bh=b>>16;
    const uint32_t p=al*bl,t=ah*bl+(p>>16),v=al*bh+(t&65535);
    return (U(ah*bh+(t>>16)+(v>>16))<<32)|(uint32_t(v<<16)|(p&65535));
  }
  static B integer64(U a) {
    B r;for(unsigned i=0;i<4;++i) r.w[F+i]=uint16_t(a>>(16*i));return r;
  }
  static U square_root(U a) {
    U root=0,step=U(1)<<62;
    while(step>a) step>>=2;
    while(step) {
      if(a>=root+step) {a-=root+step;root=(root>>1)+step;}
      else root>>=1;
      step>>=2;
    }
    return root;
  }
  static bool capped_product(U a,U b,U& out) {
    uint16_t t[8]{};
    for(unsigned i=0;i<4;++i) {
      uint32_t carry=0;
      for(unsigned j=0;j<4;++j) {
        const uint32_t p=uint32_t(uint16_t(a>>(16*i)))*uint16_t(b>>(16*j))+t[i+j]+carry;
        t[i+j]=uint16_t(p);carry=p>>16;
      }
      t[i+4]=uint16_t(carry);
    }
    if(t[4] || t[5] || t[6] || t[7] || t[3]>=64) return false;
    out=U(t[0])|(U(t[1])<<16)|(U(t[2])<<32)|(U(t[3])<<48);return true;
  }
  static bool exact_boundary(U x,U y,U& result) {
    U a,b;int e,f;normalize(x,a,e);normalize(y&UINT64_C(0x7FFFFFFFFFFFFFFF),b,f);
    e-=52;f-=52;
    while(!(a&1)) {a>>=1;++e;}
    while(!(b&1)) {b>>=1;++f;}
    if(a==1) {
      // 2^(e*y) is dyadic exactly when e*y is an integer. The signed
      // exponent is small enough to clamp before any large left shift.
      const uint32_t m=unsigned(e<0?-e:e);
      U magnitude=word_product(uint32_t(b),m)+(U(uint32_t(b>>32)*m)<<32);
      const bool negative=(e<0)^bool(y>>63);
      if(f<0) {
        const unsigned shift=unsigned(-f);
        if(shift>=64 || (magnitude&((U(1)<<shift)-1))) return false;
        magnitude>>=shift;
      } else {
        if(f>=12 || magnitude>(U(2048)>>unsigned(f))) {result=negative?0:UINT64_C(0x7FF0000000000000);return true;}
        magnitude<<=unsigned(f);
      }
      if(magnitude>2048) {result=negative?0:UINT64_C(0x7FF0000000000000);return true;}
      result=rounded(integer64(1),negative?-int(magnitude):int(magnitude));return true;
    }
    // A nontrivial odd denominator cannot be a binary64 boundary.
    if(y>>63) return false;
    if(f<0) {
      const unsigned roots=unsigned(-f);
      if(roots>=6 || (uint32_t(e)&((1U<<roots)-1))) return false;
      for(unsigned i=0;i<roots;++i) {
        const U r=square_root(a);
        if(word_product(uint32_t(r),uint32_t(r))!=a) return false;
        a=r;
      }
      e/=int(1U<<roots);
    } else {
      if(f>=6 || b>(U(54)>>unsigned(f))) return false;
      b<<=unsigned(f);
    }
    if(b>54) return false;
    U power=1;
    for(unsigned i=0;i<unsigned(b);++i) if(!capped_product(power,a,power)) return false;
    result=rounded(integer64(power),e*int(b));return true;
  }
  static bool evaluate(U x,U y,U& result) {
    const U mask=UINT64_C(0x7FFFFFFFFFFFFFFF),one=UINT64_C(0x3FF0000000000000),infinity=UINT64_C(0x7FF0000000000000);
    x&=mask;const U ym=y&mask;
    if(!x || x>=infinity || ym>=infinity) return false;
    if(x==one || !ym) {result=one;return true;}
    const bool negative=(x<one)^bool(y>>63);
    if(ym>=UINT64_C(0x43E0000000000000)) {result=negative?0:infinity;return true;}
    if(exact_boundary(x,y,result)) return true;
    U sx,sy;int ex,ey;normalize(x,sx,ex);normalize(ym,sy,ey);
    const I l2=ln2(),lm=log_mantissa(sx);I logarithm;
    if(ex<0) logarithm={subtract(times(l2.lo,unsigned(-ex)),lm.hi),subtract(times(l2.hi,unsigned(-ex)),lm.lo)};
    else logarithm={add(times(l2.lo,unsigned(ex)),lm.lo),add(times(l2.hi,unsigned(ex)),lm.hi)};
    const I unscaled={times(logarithm.lo,sy),times(logarithm.hi,sy)};
    if(ey>52) {
      const B threshold=shift(integer(800),52-ey,false);
      if(compare(unscaled.lo,threshold)>0) {result=negative?0:infinity;return true;}
      if(compare(unscaled.hi,threshold)>0) return false;
    }
    const I q={shift(unscaled.lo,ey-52,false),shift(unscaled.hi,ey-52,true)};
    if(compare(q.lo,integer(800))>0) {result=negative?0:infinity;return true;}
    if(compare(q.hi,integer(800))>0) return false;
    // Approximate q/ln2 solely to choose a reduction; verify |r|<1/2 below.
    const uint32_t head=uint32_t(shifted64(q.lo,P-20));
    const uint32_t al=head&0xFFFFU,ah=head>>16,bl=1512775U&0xFFFFU,bh=1512775U>>16;
    const uint32_t p=al*bl,t=ah*bl+(p>>16),v=al*bh+(t&0xFFFFU);
    const U index_product=(U(ah*bh+(t>>16)+(v>>16))<<32)|(uint32_t(v<<16)|(p&0xFFFFU));
    const unsigned k=unsigned((index_product+(U(1)<<39))>>40);
    const I multiple={times(l2.lo,k),times(l2.hi,k)};
    S low=difference(q.lo,multiple.hi),high=difference(q.hi,multiple.lo);
    if(negative) {S old=low;low=negate(high);high=negate(old);}
    B half;half.w[F-1]=0x8000;
    if(compare(low.mag,half)>=0 || compare(high.mag,half)>=0) return false;
    const I lo=exp_endpoint(low),hi=exp_endpoint(high);
    const int scale=negative?-int(k):int(k);
    const U lower=rounded(lo.lo,scale),upper=rounded(hi.hi,scale);
    if(lower!=upper) return false;
    result=lower;return true;
  }
};
}
