#include "usb_mode_handoff.hpp"

#include <assert.h>

int main() {
  usb_mode_handoff::TerminalLifecycle lifecycle;

  // Normal boot starts CDC exactly once.
  assert(lifecycle.generation() == 0);
  assert(lifecycle.consume_start_required());
  assert(!lifecycle.consume_start_required());

  // If preparation fails before Serial.end(), CDC is still running and must
  // not be initialized recursively from the active terminal command.
  assert(!lifecycle.consume_start_required());

  // Once CDC really has stopped for MSC, returning to terminal mode performs
  // exactly one restart.  A repeated cleanup call remains harmless.
  lifecycle.cdc_stopped();
  assert(lifecycle.generation() == 1);
  assert(lifecycle.consume_start_required());
  assert(!lifecycle.consume_start_required());

  // A later successful handoff has the same independent lifecycle.
  lifecycle.cdc_stopped();
  assert(lifecycle.generation() == 2);
  assert(lifecycle.consume_start_required());
  assert(!lifecycle.consume_start_required());
}
