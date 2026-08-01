#include <cassert>
#include <iostream>

#include "watchdog_gate.hpp"

using watchdog_gate::Gate;
using watchdog_gate::Snapshot;

static void test_requires_start_and_completed_epoch(void) {
  Gate gate;
  gate.note_epoch(10);
  assert(!gate.take_reload(1000));

  gate.start(100);
  assert(!gate.take_reload(1000));
  gate.note_epoch(110);
  assert(!gate.take_reload(200));
  assert(gate.take_reload(350));

  const Snapshot state = gate.snapshot();
  assert(state.started);
  assert(state.epochs == 1);
  assert(state.reloads == 2);
  assert(state.last_reload_ms == 350);
  assert(state.maximum_reload_gap_ms == 250);
}

static void test_one_epoch_cannot_feed_twice(void) {
  Gate gate;
  gate.start(0);
  gate.note_epoch(1);
  assert(gate.take_reload(250));
  assert(!gate.take_reload(500));
  gate.note_epoch(501);
  assert(gate.take_reload(750));
}

static void test_epoch_arriving_before_interval_remains_pending(void) {
  Gate gate;
  gate.start(1000);
  gate.note_epoch(1001);
  assert(!gate.take_reload(1100));
  // No second epoch is needed once the minimum interval has elapsed.
  assert(gate.take_reload(1250));
  assert(!gate.take_reload(1500));
}

static void test_inhibit_is_irreversible_until_restart(void) {
  Gate gate;
  gate.start(10);
  gate.note_epoch(20);
  gate.inhibit();
  assert(!gate.take_reload(1000));
  assert(gate.snapshot().inhibited);

  gate.start(2000);
  gate.note_epoch(2001);
  assert(gate.take_reload(2250));
  assert(!gate.snapshot().inhibited);
}

static void test_unsigned_time_wrap(void) {
  Gate gate;
  gate.start(0xFFFFFF00UL);
  gate.note_epoch(0xFFFFFF80UL);
  assert(!gate.take_reload(0xFFFFFFF0UL));
  assert(gate.take_reload(0x00000020UL));
  assert(gate.snapshot().maximum_reload_gap_ms == 0x120UL);
}

static void test_counters_saturate(void) {
  Gate gate;
  gate.start(0);
  for(u32 index = 0; index < 1000; index++) gate.note_epoch(index);
  assert(gate.snapshot().epochs == 1000);
}

int main(void) {
  test_requires_start_and_completed_epoch();
  test_one_epoch_cannot_feed_twice();
  test_epoch_arriving_before_interval_remains_pending();
  test_inhibit_is_irreversible_until_restart();
  test_unsigned_time_wrap();
  test_counters_saturate();
  std::cout << "watchdog_gate_self_test: ok\n";
  return 0;
}
