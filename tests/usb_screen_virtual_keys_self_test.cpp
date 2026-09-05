#include "usb_screen_virtual_keys.hpp"

#include <assert.h>
#include <initializer_list>
#include <stdio.h>

namespace {

using usb_screen::VirtualKeyQueue;

static void test_abort_discards_undelivered_press(void) {
  VirtualKeyQueue keys;
  assert(!keys.workPending());
  assert(keys.enqueue(7, true) ==
         VirtualKeyQueue::EnqueueResult::QUEUED);
  assert(keys.workPending());
  assert(keys.requestedPressed() == ((u64) 1 << 7));
  assert(keys.deliveredPressed() == 0);

  keys.abortPending();
  assert(keys.front() < 0);
  assert(keys.requestedPressed() == 0);
  assert(keys.deliveredPressed() == 0);
  assert(!keys.workPending());
}

static void test_abort_releases_only_delivered_press(void) {
  VirtualKeyQueue keys;
  assert(keys.enqueue(9, true) ==
         VirtualKeyQueue::EnqueueResult::QUEUED);
  assert(keys.markFrontDelivered());
  assert(keys.deliveredPressed() == ((u64) 1 << 9));

  keys.abortPending();
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
  assert(keys.stageNextRelease());
  assert(keys.stageNextRelease());
  assert(!keys.stageNextRelease());

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
  assert(!keys.workPending());
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

// Exercise the production USB delivery adapter against the real handoff queue,
// not a second implementation of the PRESS/RELEASE ordering algorithm.
struct Input {
  VirtualKeyQueue usb;
  keyboard_core::DeliveryQueue fifo;
  keyboard_core::ExternalKeyState external;
  unsigned held_updates = 0;

  bool deliver() {
    return usb.deliverFront(
      [this](i8 event) { return fifo.push(event); },
      [this](i32 key, bool down) {
        ++held_updates;
        if(down) (void) external.press(key, 0, 1000);
        else {
          i32 unhold = -1;
          (void) external.release(key, unhold);
        }
      });
  }
  void handoff(i32 key) {
    fifo.handoff(keyboard_core::Event(key), external.pressed(key));
  }
};

static void test_delivery_handoff_order(void) {
  for(u8 key = 0; key < keyboard_core::KEY_COUNT; ++key) {
    Input input;
    const u8 next = (key + 1) % keyboard_core::KEY_COUNT;
    assert(input.usb.enqueue(key, true) == VirtualKeyQueue::EnqueueResult::QUEUED);
    assert(input.usb.enqueue(key, false) == VirtualKeyQueue::EnqueueResult::QUEUED);
    assert(input.usb.enqueue(next, true) == VirtualKeyQueue::EnqueueResult::QUEUED);
    assert(!input.external.pressed(key));
    assert(input.deliver());
    assert(input.fifo.pop() == key);
    assert(input.external.pressed(key)); // USB already received RELEASE, FIFO hasn't.
    input.handoff(key);
    assert(input.fifo.suppressed(key));
    assert(input.deliver());
    assert(!input.external.pressed(key));
    assert(input.fifo.empty()); // Causal RELEASE must not enter the next screen.
    assert(!input.fifo.pending());
    assert(input.deliver());
    assert(input.fifo.pop() == next); // Nor may handoff eat the adjacent key.
    input.usb.abortPending();
    assert(input.deliver());
    assert(input.fifo.pop() == (next | keyboard_core::RELEASE_MASK));
    assert(!input.external.anyPressed());
  }
}

static void test_backpressure_does_not_advance_held_state(void) {
  Input input;
  for(usize i = 0; i < keyboard_core::Fifo::CAPACITY; ++i)
    assert(input.fifo.push(2));
  assert(input.usb.enqueue(3, true) == VirtualKeyQueue::EnqueueResult::QUEUED);
  assert(!input.deliver());
  assert(input.held_updates == 0);
  assert(!input.external.anyPressed());
  assert(input.usb.front() == 3);
  assert(input.fifo.pop() == 2);
  assert(input.deliver());
  assert(input.external.pressed(3));
  assert(input.held_updates == 1);

  input.usb.scheduleReleaseAll();
  assert(input.usb.stageNextRelease());
  assert(input.external.pressed(3));
  assert(!input.deliver()); // Full FIFO still owns the previous held-state.
  assert(input.held_updates == 1);
  assert(input.fifo.pop() == 2);
  assert(input.deliver());
  assert(!input.external.anyPressed());
}

static void test_abort_preserves_handoff_until_delivered_release(void) {
  for(bool release_queued : {false, true}) {
    Input input;
    assert(input.usb.enqueue(4, true) == VirtualKeyQueue::EnqueueResult::QUEUED);
    assert(input.deliver());
    assert(input.fifo.pop() == 4);
    input.handoff(4);
    if(release_queued)
      assert(input.usb.enqueue(4, false) == VirtualKeyQueue::EnqueueResult::QUEUED);
    assert(input.usb.enqueue(5, true) == VirtualKeyQueue::EnqueueResult::QUEUED);
    input.usb.abortPending();
    assert(input.external.pressed(4));
    assert(!input.external.pressed(5));
    assert(input.fifo.pending());
    assert(input.deliver());
    assert(!input.external.anyPressed());
    assert(input.fifo.empty());
    assert(!input.fifo.pending());
    assert(!input.deliver());
    // A new gesture of the same key remains usable after detach.
    assert(input.usb.enqueue(4, true) == VirtualKeyQueue::EnqueueResult::QUEUED);
    assert(input.deliver());
    assert(input.fifo.pop() == 4);
  }
}

} // безымянное пространство имён

int main(void) {
  test_abort_discards_undelivered_press();
  test_abort_releases_only_delivered_press();
  test_release_all_preserves_event_order();
  test_duplicate_and_invalid_events_are_ignored();
  test_delivery_handoff_order();
  test_backpressure_does_not_advance_held_state();
  test_abort_preserves_handoff_until_delivered_release();
  printf("usb_screen_virtual_keys_self_test: ok\n");
  return 0;
}
