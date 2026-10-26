#include <stdint.h>
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
using U=uint64_t;
struct D {static constexpr U Sign=U(1)<<63,Magnitude=Sign-1,Infinity=UINT64_C(0x7ff0000000000000),Quiet=U(1)<<51;};
static U bits(double x) {union {double d;U u;} v={x};return v.u;}
static double real(U x) {union {U u;double d;} v={x};return v.d;}
extern "C" __attribute__((pcs("aapcs"))) double mk61_m0_pow_negative_integer_dispatch(double,double);
extern "C" bool mk61_m0_pow_near_one_binomial_dispatch(U,U,U*);
extern "C" __attribute__((pcs("aapcs"))) double mk61_m0_pow_positive_checked_dispatch(double,double);
extern "C" U pow_root128_ranged(U,U);
#define pow_negative_integer mk61_m0_pow_negative_integer_dispatch
#define pow_positive_checked mk61_m0_pow_positive_checked_dispatch
#define pow_near_one_binomial(x,y,out) mk61_m0_pow_near_one_binomial_dispatch((x),(y),&(out))
// Called only by the assembly after low32(y)==0, y!=+/-0 and every exact
// exponent shortcut has failed. The unchanged dispatcher handles cold roots.
extern "C" __attribute__((optimize("Os"),noinline,noipa,section(".m0_pow_dispatch_ordinary"),pcs("aapcs")))
double mk61_m0_pow_dispatch_ordinary(double x,double y) {
 const U xb=bits(x),yb=bits(y),ym=yb&D::Magnitude;
  if(xb==UINT64_C(0x3FF0000000000000)) return real(ym>D::Infinity && !(yb&D::Quiet)?yb|D::Quiet:xb);
  if(xb&D::Sign) return pow_negative_integer(x,y);
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  const uint32_t xh=uint32_t(xb>>32);
  if(xh-0x3FEFFFFFU<=1U) {
    if(uint32_t(yb) && xb-UINT64_C(0x3FF0000000000000)+64<=96) {
      U result;
      if(pow_near_one_binomial(xb,yb,result)) return real(result);
    }
  } else if(!uint32_t(yb)) {
    const uint32_t yh=uint32_t(yb>>32);
    const bool small=yh-0x40080000U<=0x00180000U &&
      !(yh&(yh<0x40100000U?0x7FFFFU:0x3FFFFU));
    // The unchanged root prefix itself accepts only ey in[-7,5].
    // Reject other exponents before allocating/calling its128-byte frame.
    if(!small && ((yh>>20)&0x7FFU)-1016U<=12U) {
      const U result=pow_root128_ranged(xb,yb);
      if(result!=(D::Infinity|D::Quiet)) return real(result);
    }
  }

#endif
  return pow_positive_checked(x,y);
}
#endif
