// Isolated RP2040 experiment. No production math entry points are replaced.
#include "kernels.h"
using U = uint64_t;
#define ENTRY extern "C" __attribute__((always_inline)) inline
struct Interp {
  volatile uint32_t accum[2], base[3], pop[3], peek[3], ctrl[2], add[2], base01;
};
static_assert(sizeof(Interp)==64, "RP2040 SIO interpolator layout");
static Interp* const i0=(Interp*)0xD0000080;
static Interp* const i1=(Interp*)0xD00000C0;
// Register definitions checked against the repository's pinned Pico SDK.
static constexpr uint32_t BLEND=1U<<21,CROSS_INPUT=1U<<16;
static constexpr uint32_t lane(unsigned shift,unsigned lsb,unsigned msb) {
  return shift|(lsb<<5)|(msb<<10);
}
ENTRY void interp_blend_setup(void) {
  i0->ctrl[0]=BLEND;i0->ctrl[1]=lane(0,0,7);i0->base[0]=0;
}
ENTRY void interp_exp_setup(void) {
  i1->ctrl[0]=lane(0,3,11);i1->base[0]=0x20010000;
}
ENTRY void interp_ln_setup(void) {
  i1->ctrl[0]=lane(7,3,12);i1->ctrl[1]=CROSS_INPUT|lane(10,0,9);
  i1->base[0]=0x20010000;i1->base[1]=0x20014000;
}
ENTRY void interp_pow_setup(void) {
  i1->ctrl[0]=lane(8,2,11);i1->ctrl[1]=CROSS_INPUT|lane(7,3,12);
  i1->base[2]=0x20010000;
}
// The exact existing wide32 algorithm. Four bounded, single-cycle MULS.
static __attribute__((always_inline)) inline U wide(uint32_t a,uint32_t b) {
  const uint32_t al=a&65535U,ah=a>>16,bl=b&65535U,bh=b>>16;
  const uint32_t p=al*bl,t=ah*bl+(p>>16),v=al*bh+(t&65535U);
  return (U(ah*bh+(t>>16)+(v>>16))<<32)|(uint32_t(v<<16)|(p&65535U));
}
static __attribute__((always_inline)) inline U blend8(uint32_t a,uint32_t b) {
  b&=255U;i0->base[1]=a;i0->accum[1]=b;
  const uint32_t q=i0->peek[1];
  return (U(q)<<8)|((a*b)&255U);
}
static __attribute__((always_inline)) inline U blendwide(uint32_t a,uint32_t b) {
  i0->base[1]=a;
  const uint32_t b0=b&255U,b1=(b>>8)&255U,b2=(b>>16)&255U,b3=b>>24;
  i0->accum[1]=b0;const U p0=(U(i0->peek[1])<<8)|((a*b0)&255U);
  i0->accum[1]=b1;const U p1=(U(i0->peek[1])<<8)|((a*b1)&255U);
  i0->accum[1]=b2;const U p2=(U(i0->peek[1])<<8)|((a*b2)&255U);
  i0->accum[1]=b3;const U p3=(U(i0->peek[1])<<8)|((a*b3)&255U);
  return p0+(p1<<8)+(p2<<16)+(p3<<24);
}
ENTRY U cpu_wide32(U a,U b) {return wide(uint32_t(a),uint32_t(b));}
ENTRY U interp_wide32(U a,U b) {return blendwide(uint32_t(a),uint32_t(b));}
ENTRY U cpu_mul8(U a,U b) {return wide(uint32_t(a),uint32_t(b)&255U);}
ENTRY U interp_mul8(U a,U b) {return blend8(uint32_t(a),uint32_t(b));}
template<bool HW> static inline U q62(U a,U b) {
  const uint32_t al=a,ah=a>>32,bl=b,bh=b>>32;
  const U p=HW?blendwide(al,bl):wide(al,bl);
  const U t=(HW?blendwide(ah,bl):wide(ah,bl))+(p>>32);
  const U v=(HW?blendwide(al,bh):wide(al,bh))+uint32_t(t);
  const U high=(HW?blendwide(ah,bh):wide(ah,bh))+(t>>32)+(v>>32);
  const U low=(v<<32)|uint32_t(p),q=(high<<2)|(low>>62);
  const U tail=low&((U(1)<<62)-1),half=U(1)<<61;
  return q+(tail>half || (tail==half && (q&1)));
}
ENTRY U cpu_q62(U a,U b) {return q62<false>(a,b);}
ENTRY U interp_q62(U a,U b) {return q62<true>(a,b);}

#include "tables.inc"
// Frozen control: the current pow_rsqrt() seed stage, before its Q63 Newton.
// Its divide uses the same idle-divider test and eight-cycle pause.
ENTRY U current_rsqrt_seed(U m,U parity64) {
  const unsigned parity=unsigned(parity64)&1U,index=unsigned((m&((U(1)<<52)-1))>>44);
  const uint32_t center=513+2*index;
  const U c=U(center)<<43;const bool negative=m<c;
  const U distance=negative?c-m:m-c;
  const uint32_t numerator=distance?uint32_t((distance-1)>>11):0;
  const uint32_t t=numerator?experiment_udiv32(numerator,center):0;
  const U z=wide(t,t);const uint32_t z32=uint32_t(z>>32);
  const uint32_t quadratic=(3*z32+4)>>3;
  const uint32_t cube=(z32*(t>>16))>>16,cubic=(5*cube+8)>>4;
  const int32_t delta=(negative?int32_t(t):-int32_t(t))+2*int32_t(quadratic)+
    (negative?2*int32_t(cubic):-2*int32_t(cubic));
  const uint32_t base=current_rsqrt_seeds[(parity<<8)|index];
  const uint32_t magnitude=uint32_t(delta<0?-delta:delta);
  const uint32_t correction=uint32_t((wide(base,magnitude)+(U(1)<<32))>>33);
  uint32_t seed=delta<0?base-correction:base+correction;
  if(delta>=0 && seed<base) seed=0xFFFFFFFFU;
  return seed;
}
template<bool HW,bool UP=false> static inline uint32_t linear_seed(U m,unsigned parity,const uint32_t table[2][257]) {
  const unsigned index=unsigned((m&((U(1)<<52)-1))>>44),alpha=unsigned(m>>36)&255U;
  const uint32_t a=table[parity][index],b=table[parity][index+1];
  uint32_t seed;
  if(HW) {i0->base[0]=a;i0->base[1]=b;i0->accum[1]=alpha;seed=i0->peek[1];}
  else if(UP) seed=a+(((b-a)*alpha)>>8);
  else seed=a-(((a-b)*alpha+255U)>>8);
  return seed;
}
static inline uint32_t refine_inverse(U m,unsigned parity,uint32_t seed) {
  // A single Q31 Newton step, with rounded partial products. The generated
  // certificate bounds its Q32 seed error by 13, including discarded m bits.
  const uint32_t x=parity?uint32_t(m>>21):uint32_t(m>>22); // Q30, floor
  const uint32_t square=uint32_t((wide(seed,seed)+(U(1)<<31))>>32);
  const uint32_t product=uint32_t((wide(x,square)+(U(1)<<29))>>30);
  const int32_t error=int32_t((1U<<30)-product);
  const uint32_t mag=uint32_t(error<0?-error:error);
  const uint32_t correction=uint32_t((wide(seed,mag)+(U(1)<<30))>>31);
  seed=error<0?seed-correction:seed+correction;
  return seed;
}
template<bool HW> static inline U linear_rsqrt(U m,unsigned parity) {
  const uint32_t seed=refine_inverse(m,parity,linear_seed<HW>(m,parity,linear_rsqrt_seeds));
  return seed>=0x80000000U?0xFFFFFFFFU:seed<<1;
}
ENTRY U cpu_rsqrt_seed(U m,U parity) {return linear_rsqrt<false>(m,unsigned(parity)&1U);}
ENTRY U interp_rsqrt_seed(U m,U parity) {return linear_rsqrt<true>(m,unsigned(parity)&1U);}
template<bool HW> static inline U sqrt_seeds(U m,unsigned parity) {
  uint32_t root=linear_seed<HW,true>(m,parity,linear_sqrt_seeds);
  const uint32_t inverse=linear_seed<HW>(m,parity,linear_rsqrt_seeds);
  const U n=parity?m<<11:m<<10,residual=n-wide(root,root);
  const bool negative=(residual>>63)!=0;
  const U mag=negative?U(0)-residual:residual;
  const U product=wide(uint32_t(mag>>32),inverse)+(wide(uint32_t(mag),inverse)>>32);
  const uint32_t correction=uint32_t((product+(U(1)<<30))>>31);
  if(negative)root-=correction;
  else {const U r=U(root)+correction;root=r>0xFFFFFFFFU?0xFFFFFFFFU:uint32_t(r);}
  return U(root)|(U(refine_inverse(m,parity,inverse))<<32);
}
ENTRY U cpu_sqrt_seeds(U m,U parity) {return sqrt_seeds<false>(m,unsigned(parity)&1U);}
ENTRY U interp_sqrt_seeds(U m,U parity) {return sqrt_seeds<true>(m,unsigned(parity)&1U);}

// Actual layouts: exp_table[512] uint64; ln's separate uint64/uint8 arrays;
// pow_refined_log's refine_log_table[1024][3] uint32. These return addresses
// only and never access the synthetic address ranges.
ENTRY U cpu_exp_address(U k,U) {return 0x20010000U+((uint32_t(k)&511U)<<3);}
ENTRY U interp_exp_address(U k,U) {i1->accum[0]=uint32_t(k)<<3;return i1->peek[0];}
ENTRY U cpu_ln_addresses(U high,U) {
  const uint32_t index=(uint32_t(high)>>10)&1023U;
  return U(0x20010000U+(index<<3))|(U(0x20014000U+index)<<32);
}
ENTRY U interp_ln_addresses(U high,U) {
  i1->accum[0]=uint32_t(high);const uint32_t lo=i1->peek[0],hi=i1->peek[1];
  return U(lo)|(U(hi)<<32);
}
ENTRY U cpu_pow_address(U high,U) {return 0x20010000U+12*((uint32_t(high)>>10)&1023U);}
ENTRY U interp_pow_address(U high,U) {i1->accum[0]=uint32_t(high);return i1->peek[2];}
// Offline regression probe for the exact checksum step used by benchmark.c.
// Unreferenced probe code is discarded from the four shipping APPs.
ENTRY U checksum_probe(U flip,U) {
  uint32_t h=0;
  for(unsigned i=0;i<4096;++i) {
    const uint32_t j=i&31U;
    U value=(U(j*2654435761U)<<32)|(j*0x1234567U+0x7654321U);
    if(j==7)value^=uint32_t(flip);
    h=interp_checksum_step(h,value,i);
  }
  return h;
}
