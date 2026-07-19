#include "cross_hal.h"

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

#include <assert.h>
#include <stdio.h>
#include <string.h>

namespace {

void test_program_key_constants_match_matrix_layout(void) {
  assert(KEY_CX == (u32) sw::CX);
  assert(KEY_PP == (u32) sw::JSR);
  assert(KEY_BP == (u32) sw::JP);
  assert(KEY_xP == (u32) sw::xP);
  assert(KEY_Px == (u32) sw::Px);
  assert(KEY_RUN == (u32) sw::RUN);
  assert(KEY_RET == (u32) sw::RET);
  assert(KEY_K == (u32) sw::K);
  assert(KEY_F == (u32) sw::F);
}

void test_digit_and_sms_layout(void) {
  const i32 digit_keys[] = {
    (i32) sw::_0, (i32) sw::_1, (i32) sw::_2, (i32) sw::_3, (i32) sw::_4,
    (i32) sw::_5, (i32) sw::_6, (i32) sw::_7, (i32) sw::_8, (i32) sw::_9
  };
  for(int digit = 0; digit <= 9; digit++) {
    assert(text_editor::digit_from_key(digit_keys[digit]) == digit);
  }
  assert(strcmp(text_editor::sms_letters_for_key((i32) sw::_4), "GHI") == 0);
  assert(strcmp(text_editor::plain_text_for_key(KEY_PP), " ") == 0);
}

void test_editor_controls_are_unambiguous(void) {
  assert(KEY_K != (u32) KEY_RIGHT);
  assert(KEY_ALPHA != KEY_OK);
}

text_editor::KeyMap editor_keys(void) {
  const text_editor::KeyMap keys = {
    KEY_LEFT, KEY_LEFT_PRESS, KEY_RIGHT, KEY_RIGHT_PRESS,
    KEY_OK, KEY_OK_PRESS, KEY_ESC, KEY_ESC_PRESS,
    KEY_SHG_LEFT_PRESS, KEY_SHG_RIGHT_PRESS, KEY_K, KEY_ALPHA, KEY_PP
  };
  return keys;
}

void test_editor_shortcuts_follow_active_profile(void) {
  const text_editor::KeyMap keys = editor_keys();
  const text_editor::Hooks hooks = {NULL, NULL, NULL, NULL, NULL};

  char sms_source[16] = "";
  text_editor::Buffer sms_editor;
  text_editor::init(sms_editor, sms_source, sizeof(sms_source));
  assert(text_editor::handle_key(sms_editor, keys, hooks, KEY_K, 0) ==
         text_editor::KeyResult::DIRTY);
  assert(text_editor::handle_key(sms_editor, keys, hooks, (i32) sw::_4, 1) ==
         text_editor::KeyResult::DIRTY);
  assert(strcmp(sms_source, "G") == 0);
  assert(text_editor::handle_key(sms_editor, keys, hooks, KEY_PP, 2) ==
         text_editor::KeyResult::DIRTY);
  assert(strcmp(sms_source, "G ") == 0);

  char symbol_source[8] = "";
  text_editor::Buffer symbol_editor;
  text_editor::init(symbol_editor, symbol_source, sizeof(symbol_source));
  assert(text_editor::handle_key(symbol_editor, keys, hooks, KEY_ALPHA, 2) ==
         text_editor::KeyResult::DIRTY);
  assert(text_editor::handle_key(symbol_editor, keys, hooks, (i32) sw::_0, 3) ==
         text_editor::KeyResult::DIRTY);
  assert(strcmp(symbol_source, "!") == 0);

  char cx_source[16] = "AB";
  text_editor::Buffer cx_editor;
  text_editor::init(cx_editor, cx_source, sizeof(cx_source));
  cx_editor.cursor = cx_editor.len;
  assert(text_editor::handle_key(cx_editor, keys, hooks, KEY_CX, 4) ==
         text_editor::KeyResult::DIRTY);
  assert(strcmp(cx_source, "A") == 0);

  assert(text_editor::handle_key(cx_editor, keys, hooks, KEY_ALPHA, 5) ==
         text_editor::KeyResult::DIRTY);
  assert(text_editor::handle_key(cx_editor, keys, hooks, KEY_LEFT, 6) ==
         text_editor::KeyResult::DIRTY);
  assert(strcmp(cx_source, "A") == 0 && cx_editor.cursor == 1);

  char line_source[24] = "ONE\nTWO";
  text_editor::Buffer line_editor;
  text_editor::init(line_editor, line_source, sizeof(line_source));
  line_editor.cursor = line_editor.len;
  assert(text_editor::handle_key(line_editor, keys, hooks, KEY_ALPHA, 7) ==
         text_editor::KeyResult::DIRTY);
  assert(text_editor::handle_key(line_editor, keys, hooks, KEY_CX, 8) ==
         text_editor::KeyResult::DIRTY);
  assert(strcmp(line_source, "ONE\n") == 0);
  assert(text_editor::handle_key(line_editor, keys, hooks, KEY_ALPHA, 9) ==
         text_editor::KeyResult::DIRTY);
  assert(text_editor::handle_key(line_editor, keys, hooks, KEY_CX, 10) ==
         text_editor::KeyResult::DIRTY);
  assert(strcmp(line_source, "ONE") == 0);
}

} // namespace

int main(void) {
  test_program_key_constants_match_matrix_layout();
  test_digit_and_sms_layout();
  test_editor_controls_are_unambiguous();
  test_editor_shortcuts_follow_active_profile();
  printf("keyboard_layout_profile_self_test: ok\n");
  return 0;
}
