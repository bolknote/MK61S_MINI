#include <cassert>
#include <iostream>

#include "classic_scheduler.hpp"
#include "stm32f4_timer_math.hpp"

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

static void test_timer_frequency_divider(void) {
  using stm32f4_timer_math::Divider;

  const Divider tone = stm32f4_timer_math::frequency_divider(84000000UL, 4000UL);
  assert(tone.prescaler_factor() == 1);
  assert(tone.period_ticks() == 21000);
  assert(stm32f4_timer_math::pwm_compare(tone.period_ticks(), 128) == 10541);

  const Divider low = stm32f4_timer_math::frequency_divider(100000000UL, 1UL);
  assert(low.prescaler_factor() <= 65536UL);
  assert(low.period_ticks() <= 65536UL);
  const u32 actual_cycles = low.prescaler_factor() * low.period_ticks();
  assert(actual_cycles > 99900000UL && actual_cycles < 100100000UL);
}

static void test_classic_fractional_phase_and_counter_wrap(void) {
  using namespace stm32f4_timer_math;

  assert(elapsed_counter_ticks(65530, 4) == 10);

  u32 phase = 0;
  u32 due = 0;
  for(u32 ticks = 0; ticks < 150000UL; ticks += 1000UL) {
    due += advance_classic_phase(1000, phase);
  }
  assert(due == 13);
  assert(phase == 0);

  phase = 0;
  assert(advance_classic_phase(11538, phase) == 0);
  assert(advance_classic_phase(1, phase) == 1);
  assert(phase == 7);
}

int main(void) {
  test_inactive_scheduler_ignores_ticks();
  test_one_tick_releases_one_step();
  test_burst_has_bounded_catch_up();
  test_state_transition_resets_phase();
  test_statistics_reset_preserves_pending_work();
  test_counters_saturate();
  test_timer_frequency_divider();
  test_classic_fractional_phase_and_counter_wrap();
  std::cout << "classic_scheduler_self_test: ok\n";
  return 0;
}
