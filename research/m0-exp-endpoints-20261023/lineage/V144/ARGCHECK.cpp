#include "/Users/bolk/Projects/MK61S_MINI/.build/m0-pow-small-y-stable-v144-20261023/source/code/native_eabi_m0.cpp"

extern "C" unsigned argcheck(const uint32_t *in,m0_eabi::Product *out) {
  PowFastLog q={(uint64_t(in[1])<<32)|in[0],in[2],0,false,0};
  const uint64_t sy=(uint64_t(in[4])<<32)|in[3];
  return pow_small_argument(q,sy,in[5],*out);
}
