#include "keyboard_core.hpp"
#include <cassert>
#include <cstdio>
using namespace keyboard_core;

static void check_sequence(DeliveryQueue& queue, const i32* expected, usize count) {
  for(usize i = 0; i < count; ++i) {
    const i32 actual = queue.pop();
    if(actual != expected[i]) {
      std::fprintf(stderr, "event[%u]: expected %ld, got %ld\n", (unsigned) i,
                   (long) expected[i], (long) actual);
      assert(false);
    }
  }
  assert(queue.pop() == -1);
}

int main() {
  for(i32 code = -257; code < 512; ++code) {
    Event event(code);
    assert(event.valid() == valid_scan_code(code));
    if(event.valid()) {
      assert(event.code() == code);
      assert(event.press() != event.release());
      assert(event.key() == (code & ~RELEASE_MASK));
    }
  }
  // Same contract for splash -> calculator, menu -> viewer/VM/USB, VM ->
  // stopped -> menu, font confirmation, and wake -> foreground. Try EVERY
  // physical cause and neighbor, so classic/mini scan-code differences cannot
  // hide loss of a neighboring key.
  for(i32 cause = 0; cause < (i32) KEY_COUNT; ++cause) {
    for(i32 neighbor = 0; neighbor < (i32) KEY_COUNT; ++neighbor) {
      if(cause == neighbor) continue;
      DeliveryQueue queue;
      assert(queue.push(cause));
      assert(queue.pop() == cause); // initiating press belongs to old context
      assert(queue.push(neighbor));
      queue.handoff(Event(cause), true);
      assert(queue.suppressed(cause));
      assert(queue.push(cause)); // repeat while held: no second action
      assert(queue.push(cause | RELEASE_MASK));
      assert(!queue.suppressed(cause));
      assert(queue.push(cause)); // second physical gesture IS an action
      assert(queue.push(neighbor | RELEASE_MASK));
      const i32 expected[] = {neighbor, cause, neighbor | RELEASE_MASK};
      check_sequence(queue, expected, 3);
      assert(queue.overflows() == 0);

      // Fast release/repress already queued before the owner changes.
      assert(queue.push(neighbor));
      assert(queue.push(cause | RELEASE_MASK));
      assert(queue.push(cause));
      queue.handoff(Event(cause), true);
      const i32 fast[] = {neighbor, cause};
      check_sequence(queue, fast, 2);
      assert(!queue.pending());

      // Two simultaneous handoffs do not clear each other's suppression.
      queue.handoff(Event(cause), true);
      queue.handoff(Event(neighbor), true);
      assert(queue.push(cause | RELEASE_MASK));
      assert(queue.suppressed(neighbor));
      assert(queue.push(neighbor | RELEASE_MASK));
      assert(!queue.pending());
    }
  }
  DeliveryQueue queue;
  queue.handoff(Event(5), false); // terminal kbd is a complete pulse
  assert(!queue.pending());
  assert(queue.push(5));
  assert(queue.pop() == 5);
  queue.handoff(Event(5 | RELEASE_MASK), true); // USER short release
  assert(!queue.pending());
  queue.handoff(Event(5), true); // sub-debounce immediate ESC
  queue.released(5); // scanner sees candidate+stable up, no debounced release
  assert(!queue.pending());

  // Overflow is counted once per rejected valid event, never overwrites FIFO,
  // and cannot strand handoff when a release arrives into a full queue.
  queue.handoff(Event(39), true);
  for(i32 i = 0; i < 8; ++i) assert(queue.push(i));
  assert(!queue.push(8));
  assert(!queue.push(40));
  assert(queue.overflows() == 1);
  assert(queue.push(39 | RELEASE_MASK));
  assert(!queue.pending());
  const i32 full[] = {0,1,2,3,4,5,6,7};
  check_sequence(queue, full, 8);
  queue.reset();
  assert(queue.overflows() == 0);
  std::puts("keyboard handoff: all cause/neighbor pairs, fast/long/external/overflow PASS");
}
