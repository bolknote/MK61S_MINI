#include "deep_idle_policy.hpp"

#include <assert.h>
#include <stdio.h>

using deep_idle_policy::Conditions;
using deep_idle_policy::Controller;
using deep_idle_policy::FailureReason;
using deep_idle_policy::State;
using deep_idle_policy::WakeReason;

static Conditions ready_conditions(void) {
  return {
    true, true, false, false, false, false, false, false, false,
    true, true, true, true, false
  };
}

static void test_blockers(void) {
  Conditions value = ready_conditions();
  assert(deep_idle_policy::blockers(value) == 0);
  value.foreground_context = false;
  value.msc_active = true;
  value.spi_idle = false;
  value.irq_context = true;
  const u32 expected = deep_idle_policy::BLOCK_FOREGROUND |
      deep_idle_policy::BLOCK_MSC | deep_idle_policy::BLOCK_SPI |
      deep_idle_policy::BLOCK_IRQ;
  assert(deep_idle_policy::blockers(value) == expected);
}

static void test_request_and_cycles(void) {
  Controller controller;
  assert(!controller.request(0, 1));
  assert(!controller.request(6, 1));
  assert(!controller.request(1, 0));
  assert(!controller.request(1, 121));
  assert(controller.request(5, 2));
  assert(!controller.request(1, 1));
  assert(controller.pending());

  assert(!controller.prepare(deep_idle_policy::BLOCK_SOUND));
  auto snapshot = controller.snapshot();
  assert(snapshot.state == State::DEEP_IDLE_PENDING);
  assert(snapshot.attempts == 1);
  assert(snapshot.rejected[5] == 1);

  assert(controller.prepare(0));
  controller.note_stopped();
  controller.note_wake(WakeReason::RTC_TIMER, 4998);
  assert(controller.continue_cycles());
  controller.prepare_next_cycle();
  controller.note_stopped();
  controller.note_wake(WakeReason::RTC_TIMER, 5001);
  assert(!controller.continue_cycles());
  controller.finish();

  snapshot = controller.snapshot();
  assert(snapshot.state == State::LIGHT_IDLE);
  assert(snapshot.entries == 2);
  assert(snapshot.rtc_timer_wakes == 2);
  assert(snapshot.completed_cycles == 2);
  assert(snapshot.last_elapsed_ms == 5001);
  assert(snapshot.total_elapsed_ms == 9999);
}

static void test_keyboard_exit_cancel_and_recovery(void) {
  Controller controller;
  assert(controller.request(3, 10));
  assert(controller.prepare(0));
  controller.note_stopped();
  controller.note_wake(WakeReason::KEYBOARD, 42);
  assert(!controller.continue_cycles());
  controller.finish();
  auto snapshot = controller.snapshot();
  assert(snapshot.keyboard_wakes == 1);
  assert(snapshot.completed_cycles == 1);

  assert(controller.request(1, 1));
  assert(controller.cancel());
  assert(!controller.cancel());

  assert(controller.request(1, 1));
  assert(controller.prepare(0));
  controller.note_wake(WakeReason::OTHER, 0); // illegal: not STOPPED
  snapshot = controller.snapshot();
  assert(snapshot.state == State::RECOVERY);
  assert(snapshot.failures == 1);
  assert(snapshot.last_failure == FailureReason::STATE);
  controller.recover();
  assert(controller.snapshot().state == State::LIGHT_IDLE);

  controller.note_failure(FailureReason::RTC_ARM);
  snapshot = controller.snapshot();
  assert(snapshot.last_failure == FailureReason::RTC_ARM);
  assert(snapshot.failures == 2);
  controller.recover();
}

int main(void) {
  test_blockers();
  test_request_and_cycles();
  test_keyboard_exit_cancel_and_recovery();
  printf("deep_idle_policy_self_test: ok\n");
  return 0;
}
