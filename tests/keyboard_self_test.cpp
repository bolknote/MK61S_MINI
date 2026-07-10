#include "keyboard_core.hpp"

#include <assert.h>
#include <stdio.h>

namespace {

void test_scan_code_validation(void) {
  assert(keyboard_core::valid_scan_code(0));
  assert(keyboard_core::valid_scan_code(39));
  assert(keyboard_core::valid_scan_code(64));
  assert(keyboard_core::valid_scan_code(103));

  assert(!keyboard_core::valid_scan_code(-1));
  assert(!keyboard_core::valid_scan_code(40));
  assert(!keyboard_core::valid_scan_code(63));
  assert(!keyboard_core::valid_scan_code(104));
  assert(!keyboard_core::valid_scan_code(127));
  assert(!keyboard_core::valid_scan_code(128));
}

void test_fifo_bounds_and_wrap(void) {
  keyboard_core::Fifo fifo;
  assert(fifo.empty());
  assert(fifo.peek() == -1);
  assert(fifo.pop() == -1);

  for(i32 code = 0; code < (i32) keyboard_core::Fifo::CAPACITY; code++) {
    assert(fifo.push(code));
  }
  assert(fifo.full());
  assert(fifo.size() == keyboard_core::Fifo::CAPACITY);
  assert(!fifo.push(8));
  for(usize i = 0; i < keyboard_core::Fifo::CAPACITY; i++) assert(fifo.peek(i) == (i32) i);
  assert(fifo.peek(keyboard_core::Fifo::CAPACITY) == -1);

  for(i32 expected = 0; expected < 4; expected++) assert(fifo.pop() == expected);
  for(i32 code = 8; code < 12; code++) assert(fifo.push(code));
  for(i32 expected = 4; expected < 12; expected++) assert(fifo.pop() == expected);
  assert(fifo.empty());

  assert(!fifo.push(-1));
  assert(!fifo.push(40));
  assert(fifo.empty());
}

void test_debounce_and_simultaneous_edges(void) {
  keyboard_core::DebouncedRow row;
  row.reset(0);
  assert(row.update(0x02, 1) == 0);
  assert(row.update(0x02, 30) == 0);
  assert(row.update(0x02, 31) == 0x02);
  assert(row.pressed(1));
  assert(row.state_mask(1) == 0);

  // A bounce restarts the release debounce window.
  assert(row.update(0x00, 40) == 0);
  assert(row.update(0x02, 50) == 0);
  assert(row.update(0x00, 60) == 0);
  assert(row.update(0x00, 89) == 0);
  assert(row.update(0x00, 90) == 0x02);
  assert(!row.pressed(1));
  assert(row.state_mask(1) == keyboard_core::RELEASE_MASK);

  row.reset(100);
  assert(row.update(0x05, 101) == 0);
  assert(row.update(0x05, 131) == 0x01);
  assert(row.update(0x05, 131) == 0x04);
  assert(row.pressed(0));
  assert(row.pressed(2));
}

void test_time_wraparound(void) {
  assert(!keyboard_core::time_reached(0xFFFFFFF0u, 0x0000000Eu));
  assert(keyboard_core::time_reached(0x0000000Eu, 0x0000000Eu));
  assert(keyboard_core::time_reached(0x0000000Fu, 0x0000000Eu));

  keyboard_core::DebouncedRow row;
  row.reset(0xFFFFFFE0u);
  assert(row.update(0x80, 0xFFFFFFF0u) == 0);
  assert(row.update(0x80, 0x0000000Du) == 0);
  assert(row.update(0x80, 0x0000000Eu) == 0x80);
}

} // namespace

int main(void) {
  test_scan_code_validation();
  test_fifo_bounds_and_wrap();
  test_debounce_and_simultaneous_edges();
  test_time_wraparound();
  printf("keyboard_self_test: ok\n");
  return 0;
}
