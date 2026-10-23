// Use narrow limbs as Qfplib does for exponent*ln2. Four22-bit
// parts preserve our Q70 constant exactly for every n<=1023.
__attribute__((always_inline)) inline Product pow_log_two70(uint32_t n) {
  const uint32_t mask=(1U<<22)-1;
  const uint32_t p0=(uint32_t(log70_two_low)&mask)*n;
  const uint32_t p1=(uint32_t(log70_two_low>>22)&mask)*n;
  const uint32_t p2=(uint32_t((log70_two_low>>44)|(U(log70_two_high)<<20))&mask)*n;
  const uint32_t p3=(log70_two_high>>2)*n;
  const uint32_t low=p0+(p1<<22);
  const uint32_t shifted=p2<<12;
  const uint32_t middle=(p1>>10)+shifted+uint32_t(low<p0);
  const uint32_t high=(p2>>20)+(p3<<2)+uint32_t(middle<shifted);
  return {high,(U(middle)<<32)|low};
}
