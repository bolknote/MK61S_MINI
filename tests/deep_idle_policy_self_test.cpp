#include "deep_idle_policy.hpp"
#include "deep_idle_auto_policy.hpp"

#include <assert.h>
#include <stdio.h>
#include <string.h>

using deep_idle_policy::Conditions;
using deep_idle_policy::Controller;
using deep_idle_policy::FailureReason;
using deep_idle_policy::State;
using deep_idle_policy::WakeReason;

static Conditions ready_conditions(void) {
  return {
    true, true, false, false, false, false, false, false, false,
    true, true, true, true, false, true
  };
}

static void test_blockers(void) {
  Conditions value = ready_conditions();
  assert(deep_idle_policy::blockers(value) == 0);
  value.foreground_context = false;
  value.msc_active = true;
  value.spi_idle = false;
  value.irq_context = true;
  value.usb_stop_ready = false;
  const u32 expected = deep_idle_policy::BLOCK_FOREGROUND |
      deep_idle_policy::BLOCK_MSC | deep_idle_policy::BLOCK_SPI |
      deep_idle_policy::BLOCK_IRQ | deep_idle_policy::BLOCK_USB;
  assert(deep_idle_policy::blockers(value) == expected);
}

static void test_request_and_cycles(void) {
  Controller controller;
  assert(!controller.request(0, 1));
  assert(!controller.request(6, 1));
  assert(!controller.request(1, 0));
  assert(!controller.request(1, 1001));
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

static void test_automatic_request_span(void) {
  Controller controller;
  assert(!controller.request_automatic(0));
  assert(!controller.request_automatic(6));
  assert(controller.request_automatic(5));
  auto snapshot = controller.snapshot();
  assert(snapshot.requested_cycles == deep_idle_policy::AUTOMATIC_CYCLES);
  assert(controller.prepare(0));
  controller.note_stopped();
  controller.note_wake(WakeReason::KEYBOARD, 25);
  assert(!controller.continue_cycles());
  controller.finish();
  assert(controller.snapshot().state == State::LIGHT_IDLE);
}

static deep_idle_auto_policy::Conditions auto_conditions(void) {
  return {true, false, false, true, true};
}

static void test_automatic_usb_suspend_policy(void) {
  using deep_idle_auto_policy::Phase;
  deep_idle_auto_policy::Controller automatic;
  auto conditions = auto_conditions();

  assert(!automatic.poll(conditions, 10));
  assert(automatic.snapshot(10).phase == Phase::HOST_AWAKE);

  conditions.usb_suspended = true;
  assert(!automatic.poll(conditions, 100));
  auto snapshot = automatic.snapshot(100);
  assert(snapshot.phase == Phase::WAIT_INITIAL_IDLE);
  assert(snapshot.wait_remaining_ms ==
         deep_idle_auto_policy::INITIAL_IDLE_DELAY_MS);
  assert(!automatic.poll(
      conditions, 100 + deep_idle_auto_policy::INITIAL_IDLE_DELAY_MS - 1));
  assert(automatic.poll(
      conditions, 100 + deep_idle_auto_policy::INITIAL_IDLE_DELAY_MS));
  automatic.note_request_accepted();
  snapshot = automatic.snapshot(1100);
  assert(snapshot.phase == Phase::CONTROLLER_BUSY);
  assert(snapshot.automatic_requests == 1);
  assert(snapshot.automatic_reentries == 0);

  conditions.controller_busy = true;
  assert(!automatic.poll(conditions, 1200));
  conditions.controller_busy = false;
  conditions.local_idle = false;
  assert(!automatic.poll(conditions, 1300));
  snapshot = automatic.snapshot(1300);
  assert(snapshot.phase == Phase::WAIT_ACTIVITY_IDLE);
  assert(snapshot.wait_remaining_ms ==
         deep_idle_auto_policy::ACTIVITY_IDLE_DELAY_MS);

  conditions.local_idle = true;
  assert(!automatic.poll(
      conditions, 1300 + deep_idle_auto_policy::ACTIVITY_IDLE_DELAY_MS - 1));
  assert(automatic.poll(
      conditions, 1300 + deep_idle_auto_policy::ACTIVITY_IDLE_DELAY_MS));
  automatic.note_request_accepted();
  snapshot = automatic.snapshot(11300);
  assert(snapshot.automatic_requests == 2);
  assert(snapshot.automatic_reentries == 1);

  automatic.note_manual_completion(true);
  assert(!automatic.poll(conditions, 11400));
  assert(automatic.snapshot(11400).phase == Phase::MANUAL_HOLDOFF);
  conditions.usb_suspended = false;
  assert(!automatic.poll(conditions, 11500));
  snapshot = automatic.snapshot(11500);
  assert(snapshot.phase == Phase::HOST_AWAKE);
  assert(!snapshot.manual_holdoff);
  assert(!automatic.session_active());
}

static void test_automatic_policy_usb_settle_and_wrap(void) {
  using deep_idle_auto_policy::Phase;
  deep_idle_auto_policy::Controller automatic;
  auto conditions = auto_conditions();
  conditions.usb_suspended = true;
  conditions.usb_ready = false;
  const u32 start = 0xFFFFFF00UL;
  assert(!automatic.poll(conditions, start));
  assert(automatic.snapshot(start).phase == Phase::WAIT_USB);

  conditions.usb_ready = true;
  assert(!automatic.poll(conditions, start + 16U));
  const u32 due = start + 16U +
      deep_idle_auto_policy::INITIAL_IDLE_DELAY_MS;
  assert(!automatic.poll(conditions, due - 1U));
  assert(automatic.poll(conditions, due));
  assert(strcmp(deep_idle_auto_policy::phase_name(Phase::READY), "ready") == 0);
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

static void test_host_resume_between_rtc_cycles_is_not_a_failure(void) {
  Controller controller;
  assert(controller.request(1, 3));
  assert(controller.prepare(0));
  controller.note_stopped();
  controller.note_wake(WakeReason::RTC_TIMER, 1000);
  assert(controller.continue_cycles());
  controller.prepare_next_cycle();

  // USB resumes before the second STOP is armed. The first timer cycle
  // remains completed and the request ends cleanly without a fictional entry.
  controller.note_interruption(WakeReason::USB_HOST);
  assert(!controller.continue_cycles());
  controller.finish();
  auto snapshot = controller.snapshot();
  assert(snapshot.state == State::LIGHT_IDLE);
  assert(snapshot.last_wake == WakeReason::USB_HOST);
  assert(snapshot.last_failure == FailureReason::NONE);
  assert(snapshot.entries == 1);
  assert(snapshot.completed_cycles == 1);
  assert(snapshot.rtc_timer_wakes == 1);
  assert(snapshot.other_wakes == 1);
  assert(snapshot.failures == 0);

  // The same boundary is valid before the first physical STOP entry.
  assert(controller.request(1, 1));
  assert(controller.prepare(0));
  controller.note_interruption(WakeReason::USB_HOST);
  controller.finish();
  snapshot = controller.snapshot();
  assert(snapshot.entries == 1);
  assert(snapshot.completed_cycles == 0);
  assert(snapshot.other_wakes == 2);
  assert(snapshot.failures == 0);
}

int main(void) {
  test_blockers();
  test_request_and_cycles();
  test_automatic_request_span();
  test_automatic_usb_suspend_policy();
  test_automatic_policy_usb_settle_and_wrap();
  test_keyboard_exit_cancel_and_recovery();
  test_host_resume_between_rtc_cycles_is_not_a_failure();
  printf("deep_idle_policy_self_test: ok\n");
  return 0;
}
