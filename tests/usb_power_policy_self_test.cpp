#include "usb_power_policy.hpp"

#include <assert.h>
#include <string.h>
#include <stdio.h>

using usb_power_policy::Conditions;

static Conditions ready(void) {
  return {true, true, true, true, true, true,
          usb_power_policy::MIN_SUSPEND_AGE_MS};
}

static void test_stop_gate(void) {
  Conditions value = ready();
  assert(usb_power_policy::stop_ready(value));
  assert(usb_power_policy::stop_blockers(value) == 0U);

  value.supported = false;
  value.wrappers_ready = false;
  value.suspended = false;
  value.configured_before_suspend = false;
  value.endpoints_idle = false;
  value.application_idle = false;
  value.suspend_age_ms = usb_power_policy::MIN_SUSPEND_AGE_MS - 1U;
  const u32 all = usb_power_policy::BLOCK_UNSUPPORTED |
      usb_power_policy::BLOCK_WRAPPERS |
      usb_power_policy::BLOCK_NOT_SUSPENDED |
      usb_power_policy::BLOCK_NOT_CONFIGURED |
      usb_power_policy::BLOCK_SUSPEND_SETTLE |
      usb_power_policy::BLOCK_ENDPOINTS |
      usb_power_policy::BLOCK_APPLICATION;
  assert(usb_power_policy::stop_blockers(value) == all);
  assert(!usb_power_policy::stop_ready(value));
}

static void test_state_classification(void) {
  using usb_power_policy::LinkState;
  assert(usb_power_policy::classify(3, false, 1, 2, 3, 4) ==
         LinkState::LINK_DETACHED);
  assert(usb_power_policy::classify(1, true, 1, 2, 3, 4) ==
         LinkState::LINK_DEFAULT);
  assert(usb_power_policy::classify(2, true, 1, 2, 3, 4) ==
         LinkState::LINK_ADDRESSED);
  assert(usb_power_policy::classify(3, true, 1, 2, 3, 4) ==
         LinkState::LINK_CONFIGURED);
  assert(usb_power_policy::classify(4, true, 1, 2, 3, 4) ==
         LinkState::LINK_SUSPENDED);
  assert(usb_power_policy::classify(0, true, 1, 2, 3, 4) ==
         LinkState::LINK_UNKNOWN);
  assert(strcmp(usb_power_policy::state_name(LinkState::LINK_SUSPENDED),
                "suspended") == 0);
}

static void test_stop_session_irq_handshake(void) {
  using namespace usb_power_policy;

  const u8 armed = begin_stop_session();
  assert((armed & STOP_SESSION_ARMED) != 0U);

  StopCompletion completion = complete_stop_session(armed, false, true);
  assert(completion.active);
  assert(!completion.host_wake);

  const u8 resumed = note_host_event(armed);
  completion = complete_stop_session(resumed, false, false);
  assert(completion.active);
  assert(completion.host_wake);

  // The EXTI snapshot remains sufficient even if the resume callback has not
  // run yet, and a callback after completion cannot resurrect an idle owner.
  completion = complete_stop_session(armed, true, true);
  assert(completion.active);
  assert(completion.host_wake);
  assert(note_host_event(STOP_SESSION_IDLE) == STOP_SESSION_IDLE);

  completion = complete_stop_session(STOP_SESSION_IDLE, true, false);
  assert(!completion.active);
  assert(!completion.host_wake);
}

int main(void) {
  test_stop_gate();
  test_state_classification();
  test_stop_session_irq_handshake();
  puts("usb_power_policy_self_test: ok");
  return 0;
}
