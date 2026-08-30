#include <cassert>
#include <iostream>

#include "power_monitor_policy.hpp"

using power_monitor_policy::State;

static void test_initial_states(void) {
  State stable = power_monitor_policy::initial_state(false, 10);
  assert(power_monitor_policy::writes_allowed(stable));
  assert(!power_monitor_policy::below_threshold(stable));
  assert(!power_monitor_policy::recovering(stable));

  State low = power_monitor_policy::initial_state(true, 20);
  assert(!power_monitor_policy::writes_allowed(low));
  assert(power_monitor_policy::below_threshold(low));
  assert(!power_monitor_policy::recovering(low));
}

static void test_fall_rise_and_stable_delay(void) {
  State state = power_monitor_policy::initial_state(false, 0);
  assert(power_monitor_policy::note_edge(state, true, 40));
  assert(!power_monitor_policy::writes_allowed(state));
  assert(!power_monitor_policy::note_edge(state, true, 41));

  assert(power_monitor_policy::note_edge(state, false, 50));
  assert(power_monitor_policy::recovering(state));
  assert(!power_monitor_policy::writes_allowed(state));
  assert(power_monitor_policy::stable_remaining_ms(state, 149, 100) == 1);
  assert(!power_monitor_policy::poll_stable(state, 149, 100));
  assert(power_monitor_policy::poll_stable(state, 150, 100));
  assert(power_monitor_policy::writes_allowed(state));
  assert(power_monitor_policy::stable_remaining_ms(state, 150, 100) == 0);
}

static void test_bounce_restarts_recovery(void) {
  State state = power_monitor_policy::initial_state(true, 0);
  assert(power_monitor_policy::note_edge(state, false, 100));
  assert(!power_monitor_policy::poll_stable(state, 150, 100));
  assert(power_monitor_policy::note_edge(state, true, 151));
  assert(power_monitor_policy::note_edge(state, false, 180));
  assert(!power_monitor_policy::poll_stable(state, 279, 100));
  assert(power_monitor_policy::poll_stable(state, 280, 100));
}

static void test_millis_wraparound(void) {
  State state = power_monitor_policy::initial_state(true, 0);
  assert(power_monitor_policy::note_edge(state, false, 0xFFFFFFF0UL));
  assert(!power_monitor_policy::poll_stable(state, 0x00000053UL, 100));
  assert(power_monitor_policy::stable_remaining_ms(
      state, 0x00000053UL, 100) == 1);
  assert(power_monitor_policy::poll_stable(state, 0x00000054UL, 100));
  assert(power_monitor_policy::writes_allowed(state));
}

int main(void) {
  test_initial_states();
  test_fall_rise_and_stable_delay();
  test_bounce_restarts_recovery();
  test_millis_wraparound();
  std::cout << "power_monitor_policy_self_test: ok\n";
  return 0;
}
