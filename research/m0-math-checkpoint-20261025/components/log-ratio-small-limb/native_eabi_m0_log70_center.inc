#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
// Exact Q70 residual delta*2^29/den for an exact dyadic center.
// Three20-bit quotient limbs keep every hardware numerator below2^32.
MK61_SOFT_PCS U mk61_m0_log_ratio70(U delta,uint32_t den);
__attribute__((optimize("Os"),noinline,cold,section(".m0_pow_extension"))) MK61_SOFT_PCS U mk61_m0_log_ratio70_slow(U delta,uint32_t den) {
  // The log10 table already stores floor(2^75/den), cleared to64.
  // Its Q46 product estimates H=delta*2^29/den within6.500062 units.
  const uint32_t* row=log10_table[(den>>1)-1024U];
  const U reciprocal=(U(row[1])<<32)|(row[0]&~63U);
  if(uint32_t(uint32_t(delta)+64U)<=128U) {
  // At either dyadic half-segment endpoint the product needs only shifts.
  // R is a multiple of64, and R mod2^46 is nonzero for every odd den.
  if(uint32_t(delta>>32)==512U || (uint32_t(uint32_t(delta)+1U)==0U && uint32_t(delta>>32)==511U)) {
    U q=reciprocal>>5;
    if(delta<(U(1)<<41)) q-=(reciprocal>>46)+1;
    const uint32_t r=(uint32_t(delta)<<29)-uint32_t(q)*den;
    return q+(uint32_t(r>=den)+uint32_t(r>=2*den));
  }
  // For a small signed low limb, delta=F*2^32+ell. Six small products
  // give an underestimate within five units, with no retained-product call.
    const uint32_t lo=uint32_t(delta),rh=uint32_t(reciprocal>>32);
    const bool below=int32_t(lo)<0;
    const uint32_t factor=uint32_t(delta>>32)+uint32_t(below);
    const uint32_t magnitude=below?0U-lo:lo;
    U base;
    if(factor==512U) base=reciprocal>>5;
    else if(!factor) base=0;
    else {
      const uint32_t rl=uint32_t(reciprocal);
      const uint32_t a0=(rl&65535U)*factor;
      const uint32_t a1=(rl>>16)*factor+(a0>>16);
      const uint32_t a2=(rh&65535U)*factor+(a1>>16);
      const uint32_t a3=(rh>>16)*factor+(a2>>16);
      base=(U(((a2>>14)&3U)|(a3<<2))<<32)|
           uint32_t(((a0&65535U)>>14)|((a1&65535U)<<2)|(a2<<18));
    }
    const uint32_t low=(rh>>14)*magnitude+(((rh&16383U)*magnitude)>>14);
    const U seed=below?base-U(low+2U):base+low;
    uint32_t top=(uint32_t(delta)<<29)-uint32_t(seed)*den;
    uint32_t divisor=den<<2,correction;
    asm volatile(".syntax unified\n"
      "movs %[q],#0\ncmp %[n],%[d]\nblo 1f\nsubs %[n],%[n],%[d]\n1:\nadcs %[q],%[q]\n"
      "lsrs %[d],%[d],#1\ncmp %[n],%[d]\nblo 1f\nsubs %[n],%[n],%[d]\n1:\nadcs %[q],%[q]\n"
      "lsrs %[d],%[d],#1\ncmp %[n],%[d]\nblo 1f\nsubs %[n],%[n],%[d]\n1:\nadcs %[q],%[q]\n"
      ".syntax divided\n" : [n]"+&l"(top),[d]"+&l"(divisor),[q]"=&l"(correction) : : "cc");
    return seed+correction;
  }
  const U q=mk61_m0_log_product46(delta,reciprocal);
  const int32_t residue=int32_t((uint32_t(delta)<<29)-uint32_t(q)*den);
  const bool negative=residue<0;
  uint32_t top=negative?uint32_t(0)-uint32_t(residue)+den-1U:uint32_t(residue);
  uint32_t divisor=den<<2,correction;
  // Three quotient bits suffice. A negative residual needs ceil division
  // so that subtracting the correction produces exactly floor(H).
  asm volatile(".syntax unified\n"
    "movs %[q],#0\ncmp %[n],%[d]\nblo 1f\nsubs %[n],%[n],%[d]\n1:\nadcs %[q],%[q]\n"
    "lsrs %[d],%[d],#1\ncmp %[n],%[d]\nblo 1f\nsubs %[n],%[n],%[d]\n1:\nadcs %[q],%[q]\n"
    "lsrs %[d],%[d],#1\ncmp %[n],%[d]\nblo 1f\nsubs %[n],%[n],%[d]\n1:\nadcs %[q],%[q]\n"
    ".syntax divided\n" : [n]"+&l"(top),[d]"+&l"(divisor),[q]"=&l"(correction) : : "cc");
  const int32_t signed_correction=negative?-int32_t(correction):int32_t(correction);
  return q+U(int64_t(signed_correction));
}
#endif
struct Log70Center {U low;uint32_t high;};
__attribute__((always_inline)) inline Log70Center log70_center(unsigned index) {
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  return {log70_low[index],log70_high[index]};
#else
  const uint32_t* row=log70_table[index];
  return {(U(row[3])<<32)|row[2],row[0]&63U};
#endif
}
__attribute__((always_inline)) inline U log70_residual(U delta,unsigned index) {
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  // Keep the positive-center correction nonnegative, including delta=0.
  // The upward unit replaces the old product bias4; error stays<=1.
  return mk61_m0_log_ratio70(delta,2049+2*index)+1;
#else
  const uint32_t* row=log70_table[index];
  const U reciprocal=(U(row[1])<<32)|(row[0]&~63U);
  return mk61_m0_log_product46(delta,reciprocal);
#endif
}
