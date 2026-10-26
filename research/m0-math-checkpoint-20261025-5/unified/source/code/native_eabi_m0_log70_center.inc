#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
// Exact Q70 residual delta*2^29/den for an exact dyadic center.
// Three20-bit quotient limbs keep every hardware numerator below2^32.
MK61_SOFT_PCS U mk61_m0_log_ratio70(U delta,uint32_t den);
__attribute__((optimize("Os"),noinline,cold,section(".m0_pow_extension"))) MK61_SOFT_PCS U mk61_m0_log_ratio70_slow(U delta,uint32_t den) {
  uint32_t a=uint32_t(delta>>11);
  const uint32_t q0=mk61_m0_math_udiv32(a,den);
  uint32_t r=a-q0*den;
  a=(r<<20)|((uint32_t(delta)&2047U)<<9);
  const uint32_t q1=mk61_m0_math_udiv32(a,den);
  r=a-q1*den;
  const uint32_t q2=mk61_m0_math_udiv32(r<<20,den);
  return (U(q0)<<40)|(U(q1)<<20)|q2;
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
