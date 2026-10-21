#include "native_eabi_m0_pow_interval.inc"

extern "C" int pow_interval512(uint64_t x,uint64_t y,uint64_t* out) {
  return m0_pow_interval::Fixed<512>::evaluate(x,y,*out);
}
extern "C" int pow_interval1024(uint64_t x,uint64_t y,uint64_t* out) {
  return m0_pow_interval::Fixed<1024>::evaluate(x,y,*out);
}
extern "C" uint64_t pow_interval_pack512(const uint16_t* words,int scale) {
  m0_pow_interval::Fixed<512>::B value;
  for(unsigned i=0;i<m0_pow_interval::Fixed<512>::N;++i) value.w[i]=words[i];
  return m0_pow_interval::Fixed<512>::rounded(value,scale);
}
extern "C" uint64_t pow_interval_pack1024(const uint16_t* words,int scale) {
  m0_pow_interval::Fixed<1024>::B value;
  for(unsigned i=0;i<m0_pow_interval::Fixed<1024>::N;++i) value.w[i]=words[i];
  return m0_pow_interval::Fixed<1024>::rounded(value,scale);
}
extern "C" uint64_t pow_interval_root(uint64_t a) {
  return m0_pow_interval::Fixed<512>::square_root(a);
}
extern "C" int pow_interval_product(uint64_t a,uint64_t b,uint64_t* out) {
  return m0_pow_interval::Fixed<512>::capped_product(a,b,*out);
}
