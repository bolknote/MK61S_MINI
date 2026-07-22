#include "usb_screen_virtual_keys.hpp"

#include <assert.h>
#include <stdio.h>

namespace {

using usb_screen::VirtualKeyQueue;

static void test_abort_discards_undelivered_press(void) {
  VirtualKeyQueue keys;
  assert(keys.enqueue(7, true) ==
         VirtualKeyQueue::EnqueueResult::QUEUED);
  assert(keys.requestedPressed() == ((u64) 1 << 7));
  assert(keys.deliveredPressed() == 0);

  const u64 external = keys.abortPending();
  assert(external == ((u64) 1 << 7));
  assert(keys.front() < 0);
  assert(keys.requestedPressed() == 0);
  assert(keys.deliveredPressed() == 0);
}

static void test_abort_releases_only_delivered_press(void) {
  VirtualKeyQueue keys;
  assert(keys.enqueue(9, true) ==
         VirtualKeyQueue::EnqueueResult::QUEUED);
  assert(keys.markFrontDelivered());
  assert(keys.deliveredPressed() == ((u64) 1 << 9));

  const u64 external = keys.abortPending();
  assert(external == ((u64) 1 << 9));
  assert(keys.front() == (9 | keyboard_core::RELEASE_MASK));
  assert(keys.markFrontDelivered());
  assert(keys.front() < 0);
  assert(keys.deliveredPressed() == 0);
}

static void test_release_all_preserves_event_order(void) {
  VirtualKeyQueue keys;
  assert(keys.enqueue(2, true) ==
         VirtualKeyQueue::EnqueueResult::QUEUED);
  assert(keys.enqueue(3, true) ==
         VirtualKeyQueue::EnqueueResult::QUEUED);
  keys.scheduleReleaseAll();
  u8 released = 0;
  assert(keys.stageNextRelease(released) && released == 2);
  assert(keys.stageNextRelease(released) && released == 3);
  assert(!keys.stageNextRelease(released));

  const i32 expected[] = {
    2,
    3,
    2 | keyboard_core::RELEASE_MASK,
    3 | keyboard_core::RELEASE_MASK,
  };
  for(usize i = 0; i < sizeof(expected) / sizeof(expected[0]); i++) {
    assert(keys.front() == expected[i]);
    assert(keys.markFrontDelivered());
  }
  assert(keys.front() < 0);
  assert(keys.requestedPressed() == 0);
  assert(keys.deliveredPressed() == 0);
}

static void test_duplicate_and_invalid_events_are_ignored(void) {
  VirtualKeyQueue keys;
  assert(keys.enqueue(1, true) ==
         VirtualKeyQueue::EnqueueResult::QUEUED);
  assert(keys.enqueue(1, true) ==
         VirtualKeyQueue::EnqueueResult::IGNORED);
  assert(keys.enqueue(keyboard_core::KEY_COUNT, true) ==
         VirtualKeyQueue::EnqueueResult::INVALID);
  assert(keys.pendingEvents() == 1);
}

} // безымянное пространство имён

int main(void) {
  test_abort_discards_undelivered_press();
  test_abort_releases_only_delivered_press();
  test_release_all_preserves_event_order();
  test_duplicate_and_invalid_events_are_ignored();
  printf("usb_screen_virtual_keys_self_test: ok\n");
  return 0;
}
