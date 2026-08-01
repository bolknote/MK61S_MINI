#include <cassert>
#include <iostream>

#include "classic_scheduler.hpp"

using classic_scheduler::Scheduler;
using classic_scheduler::Snapshot;

static void test_inactive_scheduler_ignores_ticks(void) {
  Scheduler scheduler;
  scheduler.on_tick();
  scheduler.on_ticks(10);
  assert(!scheduler.take_step());

  const Snapshot state = scheduler.snapshot();
  assert(!state.active);
  assert(state.pending == 0);
  assert(state.ticks == 0);
  assert(state.steps == 0);
  assert(state.missed_ticks == 0);
}

static void test_one_tick_releases_one_step(void) {
  Scheduler scheduler;
  scheduler.set_active(true);
  scheduler.on_tick();

  Snapshot state = scheduler.snapshot();
  assert(state.active);
  assert(state.pending == 1);
  assert(state.maximum_pending == 1);
  assert(state.ticks == 1);

  assert(scheduler.take_step());
  assert(!scheduler.take_step());
  state = scheduler.snapshot();
  assert(state.pending == 0);
  assert(state.steps == 1);
  assert(state.missed_ticks == 0);
}

static void test_burst_has_bounded_catch_up(void) {
  Scheduler scheduler;
  scheduler.set_active(true);
  scheduler.on_ticks(5);

  Snapshot state = scheduler.snapshot();
  assert(state.ticks == 5);
  assert(state.pending == classic_scheduler::MAX_PENDING_STEPS);
  assert(state.maximum_pending == classic_scheduler::MAX_PENDING_STEPS);
  assert(state.missed_ticks == 3);

  assert(scheduler.take_step());
  assert(scheduler.take_step());
  assert(!scheduler.take_step());
  assert(scheduler.snapshot().steps == 2);
}

static void test_state_transition_resets_phase(void) {
  Scheduler scheduler;
  scheduler.set_active(true);
  scheduler.on_tick();
  scheduler.set_active(false);

  Snapshot state = scheduler.snapshot();
  assert(!state.active);
  assert(state.pending == 0);
  assert(!scheduler.take_step());

  scheduler.set_active(true);
  state = scheduler.snapshot();
  assert(state.active);
  assert(state.pending == 0);
  assert(!scheduler.take_step());
}

static void test_statistics_reset_preserves_pending_work(void) {
  Scheduler scheduler;
  scheduler.set_active(true);
  scheduler.on_ticks(2);
  scheduler.reset_statistics();

  Snapshot state = scheduler.snapshot();
  assert(state.active);
  assert(state.pending == 2);
  assert(state.maximum_pending == 2);
  assert(state.ticks == 0);
  assert(state.steps == 0);
  assert(state.missed_ticks == 0);
  assert(scheduler.take_step());
}

static void test_counters_saturate(void) {
  Scheduler scheduler;
  scheduler.set_active(true);
  scheduler.on_ticks(0xFFFFFFFFUL);
  scheduler.on_ticks(3);

  const Snapshot state = scheduler.snapshot();
  assert(state.ticks == 0xFFFFFFFFUL);
  assert(state.missed_ticks == 0xFFFFFFFFUL);
  assert(state.pending == classic_scheduler::MAX_PENDING_STEPS);
}

int main(void) {
  test_inactive_scheduler_ignores_ticks();
  test_one_tick_releases_one_step();
  test_burst_has_bounded_catch_up();
  test_state_transition_resets_phase();
  test_statistics_reset_preserves_pending_work();
  test_counters_saturate();
  std::cout << "classic_scheduler_self_test: ok\n";
  return 0;
}
