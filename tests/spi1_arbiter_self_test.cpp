#include <cassert>
#include <iostream>

#include "spi1_arbiter.hpp"

using spi1_arbiter::Arbiter;
using spi1_arbiter::Owner;
using spi1_arbiter::Result;
using spi1_arbiter::Snapshot;
using spi1_arbiter::State;

static_assert(sizeof(Arbiter) <= 24, "SPI1 arbiter state must remain bounded");

static void assert_idle(const Arbiter& arbiter) {
  const Snapshot state = arbiter.snapshot();
  assert(state.state == State::IDLE);
  assert(state.owner == Owner::NONE);
}

static void test_normal_flash_and_display_leases(void) {
  Arbiter arbiter;
  assert_idle(arbiter);

  assert(arbiter.acquire(Owner::FLASH_CLIENT) == Result::ACQUIRED);
  assert(arbiter.snapshot().state == State::ACTIVE);
  assert(arbiter.snapshot().owner == Owner::FLASH_CLIENT);
  assert(arbiter.release(Owner::FLASH_CLIENT) == Result::RELEASED);
  assert_idle(arbiter);

  assert(arbiter.acquire(Owner::DISPLAY_CLIENT) == Result::ACQUIRED);
  assert(arbiter.snapshot().owner == Owner::DISPLAY_CLIENT);
  assert(arbiter.release(Owner::DISPLAY_CLIENT) == Result::RELEASED);
  assert_idle(arbiter);

  const Snapshot state = arbiter.snapshot();
  assert(state.acquisitions == 2);
  assert(state.releases == 2);
  assert(state.failures == 0);
}

static void test_contention_latches_error(void) {
  Arbiter arbiter;
  assert(arbiter.acquire(Owner::FLASH_CLIENT) == Result::ACQUIRED);
  assert(arbiter.acquire(Owner::DISPLAY_CLIENT) == Result::CONTENTION);

  Snapshot state = arbiter.snapshot();
  assert(state.state == State::ERROR);
  assert(state.owner == Owner::FLASH_CLIENT);
  assert(state.last_fault == Result::CONTENTION);
  assert(state.contentions == 1);
  assert(state.failures == 1);

  assert(arbiter.release(Owner::FLASH_CLIENT) == Result::ERROR_LATCHED);
  assert(arbiter.acquire(Owner::FLASH_CLIENT) == Result::ERROR_LATCHED);
  state = arbiter.snapshot();
  assert(state.rejected_while_error == 2);
  assert(state.owner == Owner::FLASH_CLIENT);

  assert(arbiter.recover() == Result::RECOVERED);
  assert_idle(arbiter);
  assert(arbiter.acquire(Owner::DISPLAY_CLIENT) == Result::ACQUIRED);
  assert(arbiter.release(Owner::DISPLAY_CLIENT) == Result::RELEASED);
}

static void test_double_acquire_and_release(void) {
  Arbiter arbiter;
  assert(arbiter.acquire(Owner::FLASH_CLIENT) == Result::ACQUIRED);
  assert(arbiter.acquire(Owner::FLASH_CLIENT) == Result::DOUBLE_ACQUIRE);
  assert(arbiter.snapshot().double_acquires == 1);
  assert(arbiter.recover() == Result::RECOVERED);

  assert(arbiter.acquire(Owner::FLASH_CLIENT) == Result::ACQUIRED);
  assert(arbiter.release(Owner::FLASH_CLIENT) == Result::RELEASED);
  assert(arbiter.release(Owner::FLASH_CLIENT) == Result::NOT_ACTIVE);
  assert(arbiter.snapshot().inactive_releases == 1);
  assert(arbiter.recover() == Result::RECOVERED);
  assert_idle(arbiter);
}

static void test_wrong_and_invalid_owner(void) {
  Arbiter arbiter;
  assert(arbiter.acquire(Owner::DISPLAY_CLIENT) == Result::ACQUIRED);
  assert(arbiter.release(Owner::FLASH_CLIENT) == Result::WRONG_OWNER);

  Snapshot state = arbiter.snapshot();
  assert(state.state == State::ERROR);
  assert(state.owner == Owner::DISPLAY_CLIENT);
  assert(state.wrong_owner_releases == 1);
  assert(arbiter.recover() == Result::RECOVERED);

  assert(arbiter.acquire(Owner::NONE) == Result::INVALID_OWNER);
  assert(arbiter.snapshot().invalid_owners == 1);
  assert(arbiter.recover() == Result::RECOVERED);

  assert(arbiter.acquire((Owner) 0xFFU) == Result::INVALID_OWNER);
  assert(arbiter.snapshot().invalid_owners == 2);
  assert(arbiter.recover() == Result::RECOVERED);
  assert_idle(arbiter);
}

static void test_recovery_cannot_cancel_valid_lease(void) {
  Arbiter arbiter;
  assert(arbiter.recover() == Result::NOT_IN_ERROR);
  assert_idle(arbiter);
  assert(arbiter.snapshot().recoveries == 0);

  assert(arbiter.acquire(Owner::DISPLAY_CLIENT) == Result::ACQUIRED);
  assert(arbiter.recover() == Result::NOT_IN_ERROR);
  assert(arbiter.snapshot().state == State::ACTIVE);
  assert(arbiter.snapshot().owner == Owner::DISPLAY_CLIENT);
  assert(arbiter.release(Owner::DISPLAY_CLIENT) == Result::RELEASED);
}

static void test_diagnostics_saturate_and_state_remains_reusable(void) {
  Arbiter arbiter;
  for(u32 index = 0; index < 70000UL; index++) {
    assert(arbiter.acquire(Owner::FLASH_CLIENT) == Result::ACQUIRED);
    assert(arbiter.release(Owner::FLASH_CLIENT) == Result::RELEASED);
  }

  Snapshot state = arbiter.snapshot();
  assert(state.acquisitions == spi1_arbiter::DIAGNOSTIC_MAX);
  assert(state.releases == spi1_arbiter::DIAGNOSTIC_MAX);

  for(u32 index = 0; index < 70000UL; index++) {
    assert(arbiter.acquire(Owner::FLASH_CLIENT) == Result::ACQUIRED);
    assert(arbiter.acquire(Owner::DISPLAY_CLIENT) == Result::CONTENTION);
    assert(arbiter.release(Owner::FLASH_CLIENT) == Result::ERROR_LATCHED);
    assert(arbiter.recover() == Result::RECOVERED);
  }

  state = arbiter.snapshot();
  assert(state.contentions == spi1_arbiter::DIAGNOSTIC_MAX);
  assert(state.failures == spi1_arbiter::DIAGNOSTIC_MAX);
  assert(state.rejected_while_error == spi1_arbiter::DIAGNOSTIC_MAX);
  assert(state.recoveries == spi1_arbiter::DIAGNOSTIC_MAX);
  assert_idle(arbiter);

  assert(arbiter.acquire(Owner::DISPLAY_CLIENT) == Result::ACQUIRED);
  assert(arbiter.release(Owner::DISPLAY_CLIENT) == Result::RELEASED);
  assert_idle(arbiter);
}

int main(void) {
  test_normal_flash_and_display_leases();
  test_contention_latches_error();
  test_double_acquire_and_release();
  test_wrong_and_invalid_owner();
  test_recovery_cannot_cancel_valid_lease();
  test_diagnostics_saturate_and_state_remains_reusable();
  std::cout << "spi1_arbiter_self_test: ok\n";
  return 0;
}
