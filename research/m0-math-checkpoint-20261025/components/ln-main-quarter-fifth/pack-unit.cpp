#include <stdint.h>
#define MK61_M0_RP2040_EABI 1
using U=uint64_t;
enum : uint32_t {ln_main_radius=8U};
struct D {static constexpr U Fraction=(U(1)<<52)-1;};
static unsigned clz32(uint32_t x) {
  if(!x) return 32;
  unsigned n=0;
  if(!(x&0xFFFF0000U)) {n+=16;x<<=16;}
  if(!(x&0xFF000000U)) {n+=8;x<<=8;}
  if(!(x&0xF0000000U)) {n+=4;x<<=4;}
  if(!(x&0xC0000000U)) {n+=2;x<<=2;}
  return n+unsigned(!(x&0x80000000U));
}
static unsigned clz64(U x) {return uint32_t(x>>32)?clz32(uint32_t(x>>32)):32+clz32(uint32_t(x));}

static double real(U x) {union {U u;double d;} q={x};return q.d;}
static U bits(double x) {union {double d;U u;} q={x};return q.u;}
static double ln_refine(double) {return real(UINT64_C(0x7FF8000000000284));}
__attribute__((always_inline)) inline bool ln_main_coefficient_accept(uint32_t distance,bool above,
    U sign,uint32_t n,uint32_t den,int32_t oriented,bool negative,uint32_t fourth,uint32_t fifth) {
  const int32_t r4=int32_t((fourth+2U)&3U)-2;
  const int32_t r5=int32_t(fifth)-5*int32_t(((fifth+2U)*52429U)>>18);
  int32_t bias20=5*r4+(negative?4*r5:-4*r5);
  uint32_t lower=negative?85U:90U;
  uint32_t upper=den>=3585U?(negative?85U:80U):
      den>=2081U?(negative?180U:170U):(negative?190U:180U);
  if(sign) {const uint32_t old=lower;lower=upper;upper=old;bias20=-bias20;}
  // ln2 is a strict lower bound with error greater than -1/2 Q70.
  const uint32_t limit=above?upper:lower+20U*n;
  const int32_t adjustment=2*bias20*int32_t(den)-40*oriented;
  return (int32_t(40U*distance)-int32_t(limit))*int32_t(den)+
      (above?-adjustment:adjustment)>=0;
}
__attribute__((always_inline)) inline double ln_pack70(U low,uint32_t high,U sign,uint32_t error,double x
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
    ,uint32_t h_low=0,uint32_t fourth=0,uint32_t fifth=0
#endif
    ) {
  unsigned width,shift;int bias;
  if(high) {width=32-clz32(high);shift=width+11;bias=int(width)+1023;}
  else {width=64-clz64(low);shift=width-53;bias=int(width)+959;}
  const uint32_t tail=uint32_t(low)&((1U<<shift)-1),half=1U<<(shift-1);
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  // Actual error is strictly below the integer radius. The discrete
  // midpoint distance may equal that radius and still be accepted.
  const uint32_t guard=error-1;
#else
  const uint32_t guard=error;
#endif
  if(uint32_t(tail-(half-guard))<=2*guard) {
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
    // Q70 ln2 rounds down. Its exponent contribution cannot move a
    // point from above the midpoint to below it.
    bool safe=error>ln_main_radius && tail>=half+ln_main_radius;
    if(!safe && error==ln_main_radius) {
      const uint32_t bh=uint32_t(bits(x)>>32);
      if((bh>>20)==1023U) {
        const uint32_t distance=tail>half?tail-half:half-tail;
        // Main k=0: lower error>-4; upper error<6 on negative
        // offsets and<7 on positive offsets.
        if(tail<half) {
          safe=distance>=4U || ((bh&0xFFFFFU)<32768U && (bh&1023U)>=1022U);
        } else safe=distance>=((bh&512U)?7U:6U);
      }
    }
    if(!safe && error>=ln_main_radius) {
      const uint32_t distance=tail>half?tail-half:half-tail;
      if(distance) {
        const U b=bits(x);
        const uint32_t den=2049U+2U*unsigned((b&D::Fraction)>>42);
        const bool negative=(b&(U(1)<<41))==0;
        uint32_t delta_low=uint32_t(b)<<29;
        if(negative) delta_low=0U-delta_low;
        const int32_t residue=int32_t(delta_low-h_low*den);
        const int32_t oriented=(negative!=(sign!=0))?-residue:residue;
        const uint32_t n=2U*(error-ln_main_radius)-((uint32_t(b>>52)^1U)&1U);
        safe=ln_main_coefficient_accept(distance,tail>half,sign,n,den,oriented,negative,fourth,fifth);
      }
    }
    if(!safe) return ln_refine(x);
#else
    return ln_refine(x);
#endif
  }
  const uint32_t lo=uint32_t(low),hi=uint32_t(low>>32);
  const U retained=(U((hi>>shift)|(high<<(32-shift)))<<32)|uint32_t((lo>>shift)|(hi<<(32-shift)));
  const U q=retained+U(tail>half || (tail==half && (retained&1)));
  return real(sign+(U(bias-8)<<52)+q);
}
__attribute__((always_inline)) inline double ln_main_pack70(U low,uint32_t high,U sign,
    uint32_t exponent_error,uint32_t h_low,double x,uint32_t fourth,uint32_t fifth) {
  unsigned width,shift;int bias;
  if(high) {width=32-clz32(high);shift=width+11;bias=int(width)+1023;}
  else {width=64-clz64(low);shift=width-53;bias=int(width)+959;}
  const uint32_t tail=uint32_t(low)&((1U<<shift)-1),half=1U<<(shift-1);
  const uint32_t guard=15U+exponent_error;
  if(uint32_t(tail-(half-guard))<=2U*guard) {
    // The generic polynomial bound is13.400121<14; the ln2 error
    // on exponent paths is nonpositive in the final magnitude.
    if(!exponent_error || tail<half+14U) {
      const uint32_t distance=tail>half?tail-half:half-tail;
      if(!distance) return ln_refine(x);
      const U b=bits(x);
      const uint32_t den=2049U+2U*unsigned((b&D::Fraction)>>42);
      const bool negative=(b&(U(1)<<41))==0;
      uint32_t delta_low=uint32_t(b)<<29;
      if(negative) delta_low=0U-delta_low;
      const int32_t residue=int32_t(delta_low-h_low*den);
      const int32_t oriented=(negative!=(sign!=0))?-residue:residue;
      const int32_t directed=tail>half?oriented:-oriented;
      uint32_t radius=7U+exponent_error;
      if(!exponent_error) {
        // The exact h residual supplies the linear argument error.
        // Remaining lower radii are3/4; the upper radius is6.
        radius=tail>half?6U:(negative?3U:4U);
        if(!negative && tail<half && den<=2111U && (uint32_t(b>>32)&1023U)>=1022U)
          radius=1U;
      }
      if((int32_t(distance)-int32_t(radius))*int32_t(den)+directed<0) {
        const uint32_t n=2U*exponent_error-((uint32_t(b>>52)^1U)&1U);
        if(!ln_main_coefficient_accept(distance,tail>half,sign,n,den,oriented,negative,fourth,fifth))
          return ln_refine(x);
      }
    }
  }
  const uint32_t lo=uint32_t(low),hi=uint32_t(low>>32);
  const U retained=(U((hi>>shift)|(high<<(32-shift)))<<32)|uint32_t((lo>>shift)|(hi<<(32-shift)));
  const U q=retained+U(tail>half || (tail==half && (retained&1)));
  return real(sign+(U(bias-8)<<52)+q);
}
static const volatile uint32_t* input() {return reinterpret_cast<const volatile uint32_t*>(UINT32_C(0x20000000));}
static U input_bits() {const auto p=input();return (U(p[1])<<32)|p[0];}
extern "C" U audit_exact(U low,U config) {
 const auto p=input();const uint32_t c=uint32_t(config),n=(c>>16)&1023U;
 return bits(ln_pack70(low,c&65535U,U((c>>26)&1U)<<63,8U+(n+1U)/2,real(input_bits()),p[2],p[3],p[4]));
}
extern "C" U audit_raw(U low,U config) {
 const auto p=input();const uint32_t c=uint32_t(config),n=(c>>16)&1023U;
 return bits(ln_main_pack70(low,c&65535U,U((c>>26)&1U)<<63,(n+1U)/2,p[2],real(input_bits()),p[3],p[4]));
}
extern "C" U audit_coefficient(U fields,U config) {
 const auto p=input();const U b=input_bits();
 const uint32_t c=uint32_t(config),n=(c>>16)&1023U,den=2049U+2U*unsigned((b&D::Fraction)>>42);
 const bool sign=(c>>26)&1U,negative=(b&(U(1)<<41))==0;
 const int32_t residue=int32_t(p[7]),oriented=negative!=sign?-residue:residue;
 return U(ln_main_coefficient_accept(p[5],p[6]!=0,U(sign)<<63,n,den,oriented,negative,uint32_t(fields),uint32_t(fields>>32)));
}
