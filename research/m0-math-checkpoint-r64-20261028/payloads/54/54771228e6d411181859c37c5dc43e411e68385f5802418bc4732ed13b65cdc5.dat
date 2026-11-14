#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
// A second pass for a small cosine whose Q62 cell was ambiguous.
// q*2^(e-63) has argument error at most one relative Q63 unit.
// The complete decrement enclosure is <3 Q70 units; retain four.
__attribute__((optimize("Os"),noipa,section(".m0_trig_cos70")))
static U checked_trig_cos70(U q,int e,unsigned argument_error,U sign) {
  if(e<-26 || e>-6 || argument_error>1 || uint32_t(q>>62)!=1) return 0;
  const U z=exp_high_square(q)>>unsigned(-2*e-8);
  const uint32_t t=uint32_t(z>>26),low=uint32_t(z)&0x3FFFFFFU;
  const U square=(wide32(t,t)>>18)+(wide32(t,low)>>43);
  const uint32_t u=uint32_t(square>>14);
  const U cube=wide32(u,t)>>30;
  const uint32_t fourth=uint32_t(wide32(u,u)>>42);
  const U term4=(math62_third(square)+4)>>3;
  // These reciprocal quotients are exact in their bounded32bit domains.
  const uint32_t term6=uint32_t(wide32(uint32_t((cube+360)>>4),0xB60B60B7U)>>37);
  const uint32_t term8=uint32_t(wide32(fourth+20160,0x68068069U)>>46);
  const U decrease=((z+1)>>1)-term4+term6-term8;
  const uint32_t tail=uint32_t(decrease)&0x1FFFFU,half=0x10000U;
  if(tail>=half?tail-half<=4:half-tail<=4) return 0;
  const U retained=decrease>>17;
  const U rounded=retained+U(tail>half || (tail==half && (retained&1)));
  return (sign&D::Sign)|(UINT64_C(0x3FF0000000000000)-rounded);
}
#endif
