#include <stdint.h>
using U=uint64_t;
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
static double ln_refine(double) {return real(UINT64_C(0x7FF800000000019A));}
__attribute__((always_inline)) inline double ln_main_pack70(U low,uint32_t high,U sign,
    uint32_t exponent_error,uint32_t h_low,double x) {
  unsigned width,shift;int bias;
  if(high) {width=32-clz32(high);shift=width+11;bias=int(width)+1023;}
  else {width=64-clz64(low);shift=width-53;bias=int(width)+959;}
  const uint32_t tail=uint32_t(low)&((1U<<shift)-1),half=1U<<(shift-1);
  const uint32_t guard=15U+exponent_error;
  if(uint32_t(tail-(half-guard))<=2U*guard) {
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
    if((int32_t(distance)-int32_t(7U+exponent_error))*int32_t(den)+directed<0)
      return ln_refine(x);
  }
  const uint32_t lo=uint32_t(low),hi=uint32_t(low>>32);
  const U retained=(U((hi>>shift)|(high<<(32-shift)))<<32)|uint32_t((lo>>shift)|(hi<<(32-shift)));
  const U q=retained+U(tail>half || (tail==half && (retained&1)));
  return real(sign+(U(bias-8)<<52)+q);
}
struct PackInput {U low,xbits,sign;uint32_t high,extra,h_low,pad;};
extern "C" U audit_main_pack(U address) {
 const PackInput* p=reinterpret_cast<const PackInput*>(uintptr_t(uint32_t(address)));
 return bits(ln_main_pack70(p->low,p->high,p->sign,p->extra,p->h_low,real(p->xbits)));
}
