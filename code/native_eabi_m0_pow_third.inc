// Exact unsigned division by3 using short shifts and a bounded correction.
// The pow log cube is below2^37+1. Masking the high word communicates the
// independently certified <2^38 domain to ARMv6-M's instruction selector.
__attribute__((always_inline)) inline uint32_t pow_divide3(uint32_t a) {
  uint32_t q=(a>>2)+(a>>4);
  q+=q>>4;q+=q>>8;q+=q>>16;
  const uint32_t r=a-3*q;
  return q+((11*r)>>5);
}
__attribute__((always_inline)) inline uint32_t pow_exp_linear32(uint32_t t) {
  uint32_t q=(t>>2)+(t>>4);
  q+=q>>4;q+=q>>8;q+=q>>16;
  const uint32_t r=t-3*q;
  return t-q-((11*(r+1))>>5);
}

// Split the certified38-bit cube into a32-bit quotient and six tail bits.
// With r in0..2, tail is1..192, where floor(171*tail/512)=floor(tail/3).
__attribute__((always_inline)) inline U pow_log_third70(U a) {
  const uint32_t top=uint32_t(a>>6),q=pow_divide3(top);
  const uint32_t r=top-3*q;
  const uint32_t tail=(r<<6)+(uint32_t(a)&63U)+1;
  return (U(q)<<6)+((tail*171U)>>9);
}
