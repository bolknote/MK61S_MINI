#ifndef MK61_ENTROPY_POOL_HPP
#define MK61_ENTROPY_POOL_HPP

#include "rust_types.h"

namespace entropy_pool {

enum class Domain : u8 {
  CALCULATOR = 0,
  FOCAL = 1,
  TINYBASIC = 2
};

// Start collecting the internal AVBAT ADC noise.  poll_startup() is cheap
// enough to call once per splash wait loop; finish_startup() fills any missing
// Von Neumann bits when a splash is skipped and restores the normal ADC width.
void begin(void);
void poll_startup(void);
void finish_startup(void);

// Mix every physical key transition time into the pool and rekey the enhanced
// calculator stream when that mode is active.
void note_key(u8 keycode, u32 timestamp_us);

// Independent, domain-separated random streams for calculator, FOCAL and
// TinyBASIC.  Language streams never depend on the calculator compatibility
// setting.
u32 next_u32(Domain domain);
void configure_calculator(bool enhanced);

u16 startup_raw_samples(void);
u8 startup_entropy_bits(void);

} // namespace entropy_pool

#endif
