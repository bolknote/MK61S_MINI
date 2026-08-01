#if defined(ARDUINO_ARCH_STM32)
  // config.h owns the source-tree default. Host state-machine tests pass the
  // feature flag on the compiler command line and avoid board pin definitions.
  #include <Arduino.h>
  #include "config.h"
#endif

#include "spi1_bus.hpp"

#if MK61_ENABLE_SPI1_ARBITER

namespace {

// Arbiter has a constexpr constructor and is constant-initialized. The build
// gate verifies that this does not introduce a global constructor.
spi1_arbiter::Arbiter bus_arbiter;

} // namespace

namespace spi1_bus {

bool acquire(spi1_arbiter::Owner owner) {
  return bus_arbiter.acquire(owner) == spi1_arbiter::Result::ACQUIRED;
}

bool release(spi1_arbiter::Owner owner) {
  return bus_arbiter.release(owner) == spi1_arbiter::Result::RELEASED;
}

bool recover(void) {
  return bus_arbiter.recover() == spi1_arbiter::Result::RECOVERED;
}

spi1_arbiter::Snapshot statistics(void) {
  return bus_arbiter.snapshot();
}

const char* backend_name(void) { return "polling-arbiter"; }

bool enabled(void) { return true; }

} // namespace spi1_bus

#endif
