#ifndef MK61_SPI1_BUS_HPP
#define MK61_SPI1_BUS_HPP

#include "spi1_arbiter.hpp"

#ifndef MK61_ENABLE_SPI1_ARBITER
  #define MK61_ENABLE_SPI1_ARBITER 1
#endif
#if MK61_ENABLE_SPI1_ARBITER != 0 && MK61_ENABLE_SPI1_ARBITER != 1
  #error "MK61_ENABLE_SPI1_ARBITER must be 0 or 1"
#endif

// Production facade shared by every SPI1 client. The first rollout keeps the
// physical transfers synchronous and only makes ownership explicit; DMA is a
// later backend behind the same boundary.
namespace spi1_bus {

#if MK61_ENABLE_SPI1_ARBITER

bool acquire(spi1_arbiter::Owner owner);
bool release(spi1_arbiter::Owner owner);
bool recover(void);
spi1_arbiter::Snapshot statistics(void);
const char* backend_name(void);
bool enabled(void);

#else

// The disabled path deliberately has no global object or out-of-line call.
// Clients compile to their original direct begin/endTransaction sequence.
inline bool acquire(spi1_arbiter::Owner) { return true; }
inline bool release(spi1_arbiter::Owner) { return true; }
inline bool recover(void) { return false; }
inline spi1_arbiter::Snapshot statistics(void) {
  const spi1_arbiter::Snapshot result = {
    spi1_arbiter::State::IDLE,
    spi1_arbiter::Owner::NONE,
    spi1_arbiter::Result::NONE,
    spi1_arbiter::Result::NONE,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0
  };
  return result;
}
inline const char* backend_name(void) { return "direct"; }
inline bool enabled(void) { return false; }

#endif

} // namespace spi1_bus

#endif
