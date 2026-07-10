#include "rust_types.h"

class MK61Display {
  public:
    u8 rows(void) const { return 2; }
    void clear(void) {}
    void setCursor(u8, u8) {}
    void write(u8) {}
    bool supportsCursor(void) const { return true; }
    void cursorOn(void) {}
};

class MK61DisplayUpdate {
  public:
    explicit MK61DisplayUpdate(MK61Display&) {}
};

#define TEXT_EDITOR_HOST_TEST
#include "text_editor.hpp"
#include "utf8_view.hpp"

#include <assert.h>
#include <stdio.h>
#include <string.h>

namespace {

void test_init_terminates_untrusted_buffer(void) {
  char source[4] = {'A', 'B', 'C', 'D'};
  text_editor::Buffer editor;
  text_editor::init(editor, source, sizeof(source));
  assert(editor.len == 3);
  assert(source[3] == 0);
  assert(editor.cursor == 0 && editor.view_top == 0);

  text_editor::init(editor, NULL, 0);
  assert(editor.len == 0 && editor.cursor == 0);
}

void test_edit_primitives_reject_corrupt_state(void) {
  char source[8] = "ABC";
  u16 len = 3;
  u16 cursor = 7;
  assert(!text_editor::insert_text(source, len, cursor, sizeof(source), "X"));
  assert(strcmp(source, "ABC") == 0 && len == 3 && cursor == 7);
  assert(!text_editor::backspace(source, len, cursor));

  cursor = 2;
  assert(text_editor::replace_range(source, len, cursor, sizeof(source), 1, 2, "xyz"));
  assert(strcmp(source, "AxyzC") == 0);
  assert(len == 5 && cursor == 4);
  assert(!text_editor::replace_range(source, len, cursor, sizeof(source), 0, 0, "toolong"));
}

void test_sms_failure_does_not_arm_stale_state(void) {
  char full[4] = "ABC";
  u16 len = 3;
  u16 cursor = 3;
  text_editor::SmsState sms;
  text_editor::sms_reset(sms);
  assert(!text_editor::sms_tap(full, len, cursor, sizeof(full), sms, 18, 100));
  assert(!sms.active);
  assert(strcmp(full, "ABC") == 0);

  char source[8] = "AX";
  len = 2;
  cursor = 2;
  sms.active = true;
  sms.key_code = 18; // ABC
  sms.index = 0;
  sms.deadline_ms = 1000;
  assert(text_editor::sms_tap(source, len, cursor, sizeof(source), sms, 18, 200));
  assert(strcmp(source, "AXA") == 0);
}

bool corrupting_macro(char*, u16& len, u16& cursor, u16, i32, void*) {
  len = 0xFFFF;
  cursor = 0xFFFF;
  return true;
}

void test_hook_output_is_sanitized(void) {
  char source[8] = "ABC";
  text_editor::Buffer editor;
  text_editor::init(editor, source, sizeof(source));
  editor.shift = text_editor::Shift::ALPHA;

  const text_editor::KeyMap keys = {};
  const text_editor::Hooks hooks = {NULL, &corrupting_macro, NULL};
  assert(text_editor::handle_key(editor, keys, hooks, 99, 0) == text_editor::KeyResult::DIRTY);
  assert(editor.len == 3);
  assert(editor.cursor == 3);
}

void test_sms_deadline_wraparound(void) {
  text_editor::SmsState sms = {true, 1, 0, 0x00000010u};
  assert(!text_editor::sms_expired(sms, 0xFFFFFFF0u));
  assert(text_editor::sms_expired(sms, 0x00000010u));
}

void test_utf8_validation(void) {
  const u8 valid[] = {
    'A', 0xD0, 0x90, 0xE2, 0x82, 0xAC, 0xF0, 0x9F, 0x98, 0x80
  };
  assert(utf8_view::sequence_length(valid, sizeof(valid), 0) == 1);
  assert(utf8_view::sequence_length(valid, sizeof(valid), 1) == 2);
  assert(utf8_view::sequence_length(valid, sizeof(valid), 3) == 3);
  assert(utf8_view::sequence_length(valid, sizeof(valid), 6) == 4);

  const u8 overlong2[] = {0xC0, 0x80};
  const u8 overlong3[] = {0xE0, 0x80, 0x80};
  const u8 surrogate[] = {0xED, 0xA0, 0x80};
  const u8 too_high[] = {0xF4, 0x90, 0x80, 0x80};
  const u8 truncated[] = {0xE2, 0x82};
  assert(utf8_view::sequence_length(overlong2, sizeof(overlong2), 0) == 1);
  assert(utf8_view::sequence_length(overlong3, sizeof(overlong3), 0) == 1);
  assert(utf8_view::sequence_length(surrogate, sizeof(surrogate), 0) == 1);
  assert(utf8_view::sequence_length(too_high, sizeof(too_high), 0) == 1);
  assert(utf8_view::sequence_length(truncated, sizeof(truncated), 0) == 1);
}

} // namespace

int main(void) {
  test_init_terminates_untrusted_buffer();
  test_edit_primitives_reject_corrupt_state();
  test_sms_failure_does_not_arm_stale_state();
  test_hook_output_is_sanitized();
  test_sms_deadline_wraparound();
  test_utf8_validation();
  printf("text_editor_self_test: ok\n");
  return 0;
}
