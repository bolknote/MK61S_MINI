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

void test_sized_fifo_handles_a_full_virtual_keyboard_cycle(void) {
  keyboard_core::FixedFifo<keyboard_core::KEY_COUNT * 2> fifo;
  for(i32 key = 0; key < (i32) keyboard_core::KEY_COUNT; key++) {
    assert(fifo.push(key));
  }
  for(i32 key = 0; key < (i32) keyboard_core::KEY_COUNT; key++) {
    assert(fifo.push(key | keyboard_core::RELEASE_MASK));
  }
  assert(fifo.full());
  for(i32 key = 0; key < (i32) keyboard_core::KEY_COUNT; key++) {
    assert(fifo.pop() == key);
  }
  for(i32 key = 0; key < (i32) keyboard_core::KEY_COUNT; key++) {
    assert(fifo.pop() == (key | keyboard_core::RELEASE_MASK));
  }
  assert(fifo.empty());
}

void test_external_keys_press_hold_release_and_clear(void) {
  keyboard_core::ExternalKeyState state;
  state.reset();
  assert(!state.anyPressed());
  assert(!state.pressed(39));
  assert(!state.press(-1, 0, 1500));
  assert(!state.press(40, 0, 1500));

  assert(state.press(39, 100, 1500));
  assert(!state.press(39, 200, 1500));
  assert(state.anyPressed());
  assert(state.pressed(39));

  i32 held_key = -1;
  i32 hold_quant = -1;
  assert(!state.pollHold(1599, 1500, held_key, hold_quant));
  assert(state.pollHold(1600, 1500, held_key, hold_quant));
  assert(held_key == 39);
  assert(hold_quant == 0);
  assert(state.pollHold(3100, 1500, held_key, hold_quant));
  assert(hold_quant == 1);

  i32 unhold_quant = -1;
  assert(state.release(39, unhold_quant));
  assert(unhold_quant == 1);
  assert(!state.anyPressed());
  assert(!state.release(39, unhold_quant));
}

void test_external_keys_multiple_keys_and_hold_wraparound(void) {
  keyboard_core::ExternalKeyState state;
  state.reset();
  assert(state.press(1, 0xFFFFFF00u, 0x200u));
  assert(state.press(2, 0xFFFFFF10u, 0x200u));
  assert(state.pressed(1));
  assert(state.pressed(2));

  i32 held_key = -1;
  i32 hold_quant = -1;
  assert(!state.pollHold(0x0000010Fu, 0x200u, held_key, hold_quant));
  assert(state.pollHold(0x00000110u, 0x200u, held_key, hold_quant));
  assert(held_key == 2);
  assert(hold_quant == 0);

  i32 unhold_quant = -1;
  assert(state.release(1, unhold_quant));
  assert(unhold_quant == -1);
  state.clearHold();
  assert(state.release(2, unhold_quant));
  assert(unhold_quant == -1);
  assert(!state.anyPressed());
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
  test_sized_fifo_handles_a_full_virtual_keyboard_cycle();
  test_external_keys_press_hold_release_and_clear();
  test_external_keys_multiple_keys_and_hold_wraparound();
  test_debounce_and_simultaneous_edges();
  test_time_wraparound();
  printf("keyboard_self_test: ok\n");
  return 0;
}
