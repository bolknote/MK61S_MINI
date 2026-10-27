#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
#include "native_eabi_m0_trig_cos70.inc"
// Center-value errors are <1 relative Q63 unit. The argument enclosure
// is added by the final packer; an undecided cell keeps the old fallback.
__attribute__((optimize("Os"),noipa,section(".m0_trig_tiny_sin")))
static U checked_trig_sin_tiny(U q,int e) {
  const uint32_t t=uint32_t(q>>48),s=unsigned(-50-2*e);
  const uint32_t high=uint32_t(wide32(t*t,t)>>32);
  const uint32_t numerator=(high+(3U<<s))>>(s+1);
  return q-((numerator*0xAAABU)>>17);
}
__attribute__((optimize("Os"),noipa,section(".m0_trig_sin70")))
static U checked_trig_sin70(U q,int e) {
  const U z=exp_high_square(q)>>unsigned(-2*e-8);
  const uint32_t t=uint32_t(z>>26),low=uint32_t(z)&0x3FFFFFFU;
  const U square=(wide32(t,t)>>18)+(wide32(t,low)>>43);
  const U cube=wide32(uint32_t(square>>14),t)>>30;
  const uint32_t term6=uint32_t(wide32(uint32_t((cube+2520)>>4),0xD00D00D1U)>>40);
  const U factor=((math62_third(z)+1)>>1)-exp_high_product(square,UINT64_C(0x0222222222222222))+term6;
  return q-((exp_high_product(q,factor)+32)>>6);
}
// Return the packed value directly instead of a16byte aggregate. Inlining
// the first pass retains its existing polynomial and cheap successful path.
MK61_M0_TRIG_SECTION("small")
__attribute__((optimize("Os"),noinline))
static U checked_trig_small_packed(CheckedTrigArgument a,unsigned op,U sign) {
  CheckedTrigValue value=checked_trig_small(a,op);U result;
  if(checked_trig_pack(value,sign,result)) return result;
  if(op) return checked_trig_cos70(a.q,a.e,a.error,sign);
  if(a.e>=-26 && a.e<=-6 && uint32_t(a.q>>62)==1 && a.error<=1) {
    value={checked_trig_sin70(a.q,a.e),a.e,1+a.error};
    if(checked_trig_pack(value,sign,result)) return result;
  }
  return 0;
}
#endif
