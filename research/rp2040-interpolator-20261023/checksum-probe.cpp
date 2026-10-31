// Offline-only full-batch integrity probes; never linked into shipping APPs.
#include "kernels.h"
#define PROBE extern "C" __attribute__((noinline,noipa,used)) uint64_t
PROBE checksum_stream_v3(uint64_t flip,uint64_t position) {
  uint32_t h=0;
  for(uint32_t k=0;k<4096;++k) {
    const uint32_t j=k&31U;
    uint64_t value=(uint64_t(j*2654435761U)<<32)|(j*0x1234567U+0x7654321U);
    if(j==(position&31U))value^=flip;
    h=interp_checksum_step(h,value,k);
  }
  return h;
}
PROBE checksum_step_v3(uint64_t value,uint64_t state_index) {
  return interp_checksum_step(uint32_t(state_index),value,uint32_t(state_index>>32));
}
PROBE checksum_step_v2_formula(uint64_t value,uint64_t state_index) {
  return (uint32_t(state_index)^uint32_t(value)^uint32_t(value>>32))*16777619U+uint32_t(state_index>>32);
}
