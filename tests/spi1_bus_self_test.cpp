#include <cassert>
#include <cstring>
#include <iostream>

#include "spi1_bus.hpp"

using spi1_arbiter::Owner;
using spi1_arbiter::Result;
using spi1_arbiter::Snapshot;
using spi1_arbiter::State;

static void assert_empty_snapshot(const Snapshot& state) {
  assert(state.state == State::IDLE);
  assert(state.owner == Owner::NONE);
  assert(state.last_fault == Result::NONE);
  assert(state.acquisitions == 0);
  assert(state.releases == 0);
  assert(state.failures == 0);
}

int main(void) {
#if MK61_ENABLE_SPI1_ARBITER
  assert(spi1_bus::enabled());
  assert(std::strcmp(spi1_bus::backend_name(), "polling-arbiter") == 0);
  assert_empty_snapshot(spi1_bus::statistics());

  assert(spi1_bus::acquire(Owner::FLASH_CLIENT));
  Snapshot state = spi1_bus::statistics();
  assert(state.state == State::ACTIVE);
  assert(state.owner == Owner::FLASH_CLIENT);
  assert(!spi1_bus::acquire(Owner::DISPLAY_CLIENT));
  state = spi1_bus::statistics();
  assert(state.state == State::ERROR);
  assert(state.last_fault == Result::CONTENTION);
  assert(state.contentions == 1);
  assert(!spi1_bus::release(Owner::FLASH_CLIENT));
  assert(spi1_bus::recover());

  assert(spi1_bus::acquire(Owner::FLASH_CLIENT));
  assert(spi1_bus::release(Owner::FLASH_CLIENT));
  state = spi1_bus::statistics();
  assert(state.state == State::IDLE);
  assert(state.owner == Owner::NONE);
  assert(state.acquisitions == 2);
  assert(state.releases == 1);
  assert(state.failures == 1);
  assert(state.rejected_while_error == 1);
  assert(state.recoveries == 1);
  assert(!spi1_bus::recover());
#else
  assert(!spi1_bus::enabled());
  assert(std::strcmp(spi1_bus::backend_name(), "direct") == 0);
  assert_empty_snapshot(spi1_bus::statistics());
  assert(spi1_bus::acquire(Owner::FLASH_CLIENT));
  assert(spi1_bus::release(Owner::FLASH_CLIENT));
  assert_empty_snapshot(spi1_bus::statistics());
  assert(!spi1_bus::recover());
#endif

  std::cout << "spi1_bus_self_test: ok\n";
  return 0;
}
