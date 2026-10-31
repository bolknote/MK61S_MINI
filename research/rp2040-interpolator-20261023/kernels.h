#ifndef RP2040_INTERPOLATOR_EXPERIMENT_H
#define RP2040_INTERPOLATOR_EXPERIMENT_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef uint64_t UnaryPair(uint64_t, uint64_t);
static inline uint32_t interp_checksum_step(uint32_t h,uint64_t value,uint32_t index) {
  // Mix the two words sequentially. Right shifts propagate high-bit errors
  // back into low bits before the next multiply; the V2 odd-multiply-only
  // recurrence let 128 repeated MSB toggles cancel over a 4096-call batch.
  h=(h^(uint32_t)value)*16777619U;h^=h>>16;
  h=(h^(uint32_t)(value>>32))*16777619U;h^=h>>16;
  return h+index;
}
void interp_blend_setup(void);
void interp_exp_setup(void);
void interp_ln_setup(void);
void interp_pow_setup(void);
uint64_t cpu_wide32(uint64_t, uint64_t);
uint64_t interp_wide32(uint64_t, uint64_t);
uint64_t cpu_mul8(uint64_t, uint64_t);
uint64_t interp_mul8(uint64_t, uint64_t);
uint64_t cpu_q62(uint64_t, uint64_t);
uint64_t interp_q62(uint64_t, uint64_t);
uint64_t current_rsqrt_seed(uint64_t, uint64_t);
uint64_t cpu_rsqrt_seed(uint64_t, uint64_t);
uint64_t interp_rsqrt_seed(uint64_t, uint64_t);
uint64_t current_sqrt_seeds(uint64_t, uint64_t);
uint64_t cpu_sqrt_seeds(uint64_t, uint64_t);
uint64_t interp_sqrt_seeds(uint64_t, uint64_t);
uint64_t cpu_exp_address(uint64_t, uint64_t);
uint64_t interp_exp_address(uint64_t, uint64_t);
uint64_t cpu_ln_addresses(uint64_t, uint64_t);
uint64_t interp_ln_addresses(uint64_t, uint64_t);
uint64_t cpu_pow_address(uint64_t, uint64_t);
uint64_t interp_pow_address(uint64_t, uint64_t);
uint32_t experiment_udiv32(uint32_t, uint32_t);
#ifdef __cplusplus
}
#endif
#endif
