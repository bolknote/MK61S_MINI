#include <cassert>
#include <iostream>

#include "idle_sleep.hpp"
#include "idle_sleep_policy.hpp"

using idle_sleep_policy::Conditions;
using idle_sleep_policy::Snapshot;
using idle_sleep_policy::Tracker;

static Conditions idle_conditions(void) {
  const Conditions result = {
    true, true, false, false, false,
    false, false, false, false, true
  };
  return result;
}

static void test_policy_maps_every_blocker(void) {
  Conditions value = idle_conditions();
  assert(idle_sleep_policy::blockers(value) == 0);

  value.foreground_context = false;
  value.calculator_idle = false;
  value.usb_mass_storage_active = true;
  value.usb_screen_active = true;
  value.terminal_active = true;
  value.sound_active = true;
  value.keyboard_active = true;
  value.classic_active = true;
  value.scheduled_work = true;
  value.periodic_wake_ready = false;
  const u32 expected =
      idle_sleep_policy::BLOCK_FOREGROUND_CONTEXT |
      idle_sleep_policy::BLOCK_CALCULATOR_BUSY |
      idle_sleep_policy::BLOCK_USB_MASS_STORAGE |
      idle_sleep_policy::BLOCK_USB_SCREEN |
      idle_sleep_policy::BLOCK_TERMINAL |
      idle_sleep_policy::BLOCK_SOUND |
      idle_sleep_policy::BLOCK_KEYBOARD |
      idle_sleep_policy::BLOCK_CLASSIC |
      idle_sleep_policy::BLOCK_SCHEDULED_WORK |
      idle_sleep_policy::BLOCK_PERIODIC_WAKE;
  assert(idle_sleep_policy::blockers(value) == expected);
}

static void test_tracker_counts_entries_and_each_rejection(void) {
  Tracker tracker;
  assert(!tracker.note_attempt(
      idle_sleep_policy::BLOCK_SOUND |
      idle_sleep_policy::BLOCK_KEYBOARD));
  assert(tracker.note_attempt(0));
  tracker.note_entry(900);
  assert(tracker.note_attempt(0));
  tracker.note_entry(1100);

  Snapshot state = tracker.snapshot();
  assert(state.attempts == 3);
  assert(state.entries == 2);
  assert(state.total_sleep_us == 2000);
  assert(state.minimum_sleep_us == 900);
  assert(state.average_sleep_us() == 1000);
  assert(state.maximum_sleep_us == 1100);
  assert(state.last_blockers == 0);
  assert(state.rejected[5] == 1);
  assert(state.rejected[6] == 1);

  tracker.reset();
  state = tracker.snapshot();
  assert(state.attempts == 0);
  assert(state.entries == 0);
  assert(state.minimum_sleep_us == 0);
}

static void test_saturating_helpers(void) {
  assert(idle_sleep_policy::saturating_increment(0) == 1);
  assert(idle_sleep_policy::saturating_increment(0xFFFFFFFFUL) ==
         0xFFFFFFFFUL);
  assert(idle_sleep_policy::saturating_add(10, 20) == 30);
  assert(idle_sleep_policy::saturating_add(~((u64) 0) - 2, 3) ==
         ~((u64) 0));
}

static void test_non_arm_backend_is_explicitly_disabled(void) {
  idle_sleep::reset_statistics();
  const Conditions value = idle_conditions();
  assert(!idle_sleep::enabled());
  assert(!idle_sleep::attempt(value));
  const Snapshot state = idle_sleep::statistics();
  assert(state.attempts == 1);
  assert((state.last_blockers & idle_sleep_policy::BLOCK_IRQ_CONTEXT) != 0);
}

int main(void) {
  test_policy_maps_every_blocker();
  test_tracker_counts_entries_and_each_rejection();
  test_saturating_helpers();
  test_non_arm_backend_is_explicitly_disabled();
  std::cout << "idle_sleep_policy_self_test: ok\n";
  return 0;
}
