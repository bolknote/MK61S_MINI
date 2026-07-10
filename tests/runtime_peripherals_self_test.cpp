#include <cassert>
#include <cstdint>
#include <iostream>
#include <limits>

#include "runtime_safety.hpp"

static void test_deadline(void) {
  runtime_safety::Deadline deadline;
  assert(!deadline.pending());
  assert(!deadline.due(100));

  deadline.schedule(100, 20);
  assert(deadline.pending());
  assert(deadline.target() == 120);
  assert(!deadline.due(119));
  assert(deadline.due(120));
  assert(deadline.due(121));

  deadline.clear();
  assert(!deadline.pending());

  deadline.schedule(0xFFFFFFF0u, 0x20u);
  assert(deadline.target() == 0x10u);
  assert(!deadline.due(0x0Fu));
  assert(deadline.due(0x10u));
  assert(deadline.due(0x11u));
}

static void test_runtime_bounds(void) {
  assert(!runtime_safety::valid_index(-1, 40));
  assert(runtime_safety::valid_index(0, 40));
  assert(runtime_safety::valid_index(39, 40));
  assert(!runtime_safety::valid_index(40, 40));

  assert(runtime_safety::positive_quantum(-50) == 1);
  assert(runtime_safety::positive_quantum(0) == 1);
  assert(runtime_safety::positive_quantum(72500) == 72500);

  assert(!runtime_safety::valid_extended_command(0, 7));
  assert(runtime_safety::valid_extended_command(1, 7));
  assert(runtime_safety::valid_extended_command(6, 7));
  assert(!runtime_safety::valid_extended_command(7, 7));

  const t_time_ms expected[] = {200, 500, 1000, 2000, 100, 100};
  for(u8 code = 1; code <= 6; code++) {
    t_time_ms delay = 0;
    assert(runtime_safety::extended_command_delay(code, delay));
    assert(delay == expected[code - 1]);
  }
  t_time_ms unchanged = 123;
  assert(!runtime_safety::extended_command_delay(0, unchanged));
  assert(unchanged == 123);
  assert(!runtime_safety::extended_command_delay(7, unchanged));
}

static void test_peripheral_bounds(void) {
  assert(!runtime_safety::valid_sound_frequency(0));
  assert(runtime_safety::valid_sound_frequency(1));
  assert(runtime_safety::valid_sound_frequency(65535));
  assert(!runtime_safety::valid_sound_frequency(65536));
  assert(!runtime_safety::valid_sound_frequency(-1));

  assert(runtime_safety::valid_sound_note(4000, 100, 100));
  assert(runtime_safety::valid_sound_note(0, 100, 0));
  assert(!runtime_safety::valid_sound_note(4000, 0, 100));
  assert(!runtime_safety::valid_sound_note(4000, 100, 101));

  assert(runtime_safety::blink_transition_count(0) == 0);
  assert(runtime_safety::blink_transition_count(1) == 1);
  assert(runtime_safety::blink_transition_count(2) == 3);

  const usize max_value = std::numeric_limits<usize>::max();
  const usize max_exact_count = max_value / 2 + 1;
  assert(runtime_safety::blink_transition_count(max_exact_count) == max_value);
  assert(runtime_safety::blink_transition_count(max_value) == max_value);
}

int main(void) {
  test_deadline();
  test_runtime_bounds();
  test_peripheral_bounds();
  std::cout << "runtime_peripherals_self_test: ok\n";
  return 0;
}
