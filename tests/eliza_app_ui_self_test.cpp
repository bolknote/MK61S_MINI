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

#include <assert.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>

#include <string>
#include <vector>

#define main eliza_app_entry
#include "../examples/portable-apps/ELIZA/main.c"
#undef main

extern "C" {
const mk61_app_api* mk61_api;
}

static mk61_app_api app_api = {};
static mk61_app_services app_services = {};
static mk61_service_keyboard app_keys = keyboard_layout::MINI;
static std::vector<int32_t> input_keys;
static size_t input_key_index;
static uint32_t clock_ms;
static std::vector<std::string> display_lines;
static unsigned editor_draws;

static uint32_t mock_millis(void) { return clock_ms++; }
static void mock_service(void) {}
static void mock_delay(uint32_t duration) { clock_ms += duration; }
static uint32_t mock_display_clear(void) {
  display_lines.clear();
  return 1;
}
static uint32_t mock_display_write(uint32_t column, uint32_t row,
                                   const char* text, uint32_t length) {
  assert(column == 0);
  if(display_lines.size() <= row) display_lines.resize(row + 1);
  display_lines[row].assign(text, length);
  return 1;
}

static uint32_t mock_call(uint32_t operation, uint32_t a, uint32_t b,
                          uint32_t c, void* payload) {
  (void) b;
  (void) c;
  if(operation == MK61_SERVICE_KEYBOARD) {
    if(a == MK61_SERVICE_KEY_SCAN) return 1;
    if(a == MK61_SERVICE_KEY_GET) {
      assert(input_key_index < input_keys.size());
      return (uint32_t) input_keys[input_key_index++];
    }
  }
  if(operation == MK61_SERVICE_EDITOR_SCROLL) return 1;
  if(operation == MK61_SERVICE_EDITOR_DRAW) {
    ++editor_draws;
    return 1;
  }
  if(operation == MK61_SERVICE_EDITOR_KEY) {
    mk61_service_edit_key* request = (mk61_service_edit_key*) payload;
    text_editor::Buffer editor = {
      request->source, (u16) request->capacity, (u16) request->length,
      (u16) request->cursor, (u16) request->top,
      (text_editor::Shift) request->shift,
      {request->sms_active != 0, request->sms_key, (u8) request->sms_index,
       request->sms_deadline}
    };
    const int32_t* key = request->keys;
    const text_editor::KeyMap key_map = {
      key[0], key[1], key[2], key[3], key[4], key[5], key[6],
      key[7], key[8], key[9], key[10], key[11], key[12]
    };
    const text_editor::Hooks hooks = {NULL, NULL, NULL, NULL, NULL};
    const text_editor::Options options = {
      request->ok_text,
      (request->options & 1U) != 0,
      (request->options & 2U) != 0,
      (request->options & 4U) != 0,
      request->backspace_key
    };
    const text_editor::KeyResult result = text_editor::handle_key(
        editor, key_map, hooks, options, request->key, request->now);
    request->length = editor.len;
    request->cursor = editor.cursor;
    request->top = editor.view_top;
    request->shift = (uint32_t) editor.shift;
    request->sms_active = editor.sms.active;
    request->sms_key = editor.sms.key_code;
    request->sms_index = editor.sms.index;
    request->sms_deadline = editor.sms.deadline_ms;
    return (uint32_t) result;
  }
  if(operation == MK61_SERVICE_DISPLAY) return 1;
  assert(!"unexpected service call");
  return 0;
}

static void reset_mocks(void) {
  input_keys.clear();
  input_key_index = 0;
  clock_ms = 10;
  editor_draws = 0;
  display_lines.clear();
}

static void push_digit(unsigned digit, unsigned taps) {
  while(taps-- != 0) input_keys.push_back(app_keys.digit[digit]);
}

static void test_direct_sms_entry(void) {
  char line[32];
  reset_mocks();
  push_digit(4, 2);                 // H
  push_digit(0, 1);                 // commit
  push_digit(4, 3);                 // I
  input_keys.push_back(app_keys.ok);
  assert(read_sms_line(&app_services, line, sizeof(line)) == 1);
  assert(strcmp(line, "HI") == 0);
  assert(input_key_index == input_keys.size());
  assert(editor_draws != 0);
}

static void test_space_and_backspace(void) {
  char line[32];
  reset_mocks();
  push_digit(4, 3);                 // I
  push_digit(0, 1);
  push_digit(7, 1);                 // space
  push_digit(8, 1);                 // A
  push_digit(0, 1);
  push_digit(6, 1);                 // M
  push_digit(0, 1);
  push_digit(4, 1);                 // G, then erase it
  input_keys.push_back(app_keys.cx);
  input_keys.push_back(app_keys.ok);
  assert(read_sms_line(&app_services, line, sizeof(line)) == 1);
  assert(strcmp(line, "I AM") == 0);
}

static void test_page_wrapping(void) {
  const char* rest;
  reset_mocks();
  rest = draw_page("ONE TWO THREE FOUR FIVE", 8, 2);
  assert(display_lines.size() == 2);
  assert(display_lines[0] == "ONE TWO");
  assert(display_lines[1] == "THREE");
  assert(strcmp(rest, "FOUR FIVE") == 0);
  rest = draw_page(rest, 8, 2);
  assert(display_lines[0] == "FOUR");
  assert(display_lines[1] == "FIVE");
  assert(*rest == 0);
}

int main(void) {
  app_api.millis_ms = mock_millis;
  app_api.service = mock_service;
  app_api.delay_ms = mock_delay;
  app_api.display_clear = mock_display_clear;
  app_api.display_write_utf8 = mock_display_write;
  mk61_api = &app_api;
  app_services.keyboard_mapping = &app_keys;
  app_services.call = mock_call;

  test_direct_sms_entry();
  test_space_and_backspace();
  test_page_wrapping();
  puts("eliza APP UI tests passed");
  return 0;
}
