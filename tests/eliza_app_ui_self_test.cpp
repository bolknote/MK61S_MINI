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
static std::vector<std::vector<uint8_t>> graphic_frames;
static unsigned editor_draws;
static unsigned graphics_begins;
static unsigned graphics_ends;
static bool expose_ui_font;

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

static int32_t mock_key_wait(void) {
  assert(input_key_index < input_keys.size());
  return input_keys[input_key_index++];
}

static uint32_t mock_graphics_available(void) { return 1; }
static uint32_t mock_graphics_width(void) { return HELP_WIDTH; }
static uint32_t mock_graphics_height(void) { return HELP_HEIGHT; }
static uint32_t mock_graphics_begin(void) {
  ++graphics_begins;
  return 1;
}
static uint32_t mock_graphics_present(const uint8_t* pixels, uint32_t size) {
  assert(size == HELP_FRAME_BYTES);
  graphic_frames.emplace_back(pixels, pixels + size);
  return 1;
}
static void mock_graphics_end(void) { ++graphics_ends; }

static uint32_t mock_call(uint32_t operation, uint32_t a, uint32_t b,
                          uint32_t c, void* payload) {
  (void) b;
  (void) c;
  if(operation == MK61_SERVICE_CAPABILITIES) {
    return MK61_SERVICE_CAP_UI | MK61_SERVICE_CAP_EDITOR |
        (expose_ui_font ? MK61_SERVICE_CAP_UI_FONT : 0U);
  }
  if(operation == MK61_SERVICE_UI_FONT) {
    mk61_service_ui_glyph* glyph =
        static_cast<mk61_service_ui_glyph*>(payload);
    assert(expose_ui_font);
    assert(a == MK61_UI_FONT_GLYPH);
    assert(b <= 0x7fU);
    assert(c == sizeof(*glyph));
    assert(glyph->family == HELP_FONT_FAMILY);
    assert(glyph->size == HELP_FONT_SIZE);
    glyph->bearing_x = 0;
    glyph->bearing_y = 5;
    glyph->advance = b == ' ' ? 3 : 4;
    glyph->width = b == ' ' ? 0 : 3;
    glyph->height = b == ' ' ? 0 : 5;
    for(unsigned row = 0; row < glyph->height; ++row)
      glyph->pixels[row] = 0xe0;
    return 1;
  }
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
  graphic_frames.clear();
  graphics_begins = 0;
  graphics_ends = 0;
  expose_ui_font = true;
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

static void expect_page(const char* text,
                        const char* const expected[6]) {
  const char* rest;
  reset_mocks();
  rest = draw_page(text, 16, 6);
  assert(*rest == 0);
  assert(display_lines.size() == 6);
  for(size_t row = 0; row < 6; ++row) {
    assert(display_lines[row] == expected[row]);
    assert(display_lines[row].size() <= 16);
  }
}

static void test_help_layout(void) {
  static const char* const key_lines[6] = {
    "ELIZA SMS KEYS", "1:PQRS   2:TUV", "3:WXYZ   4:GHI",
    "5:JKL    6:MNO", "7:SPACE  8:ABC", "9:DEF  OK:NEXT"
  };
  static const char* const control_lines[6] = {
    "HOW TO TYPE", "SAME KEY=CYCLE", "0=ACCEPT LETTER",
    "CX=ERASE", "OK=SEND ESC=EXIT", "OK: NEXT"
  };
  expect_page(key_help, key_lines);
  expect_page(control_help, control_lines);
}

static void test_pages_require_ok(void) {
  reset_mocks();
  input_keys = {MK61_APP_KEY_DIGIT_1, MK61_APP_KEY_OK};
  assert(show_pages("READY", 16, 6) == 1);
  assert(input_key_index == input_keys.size());

  reset_mocks();
  input_keys = {MK61_APP_KEY_ESC};
  assert(show_pages("READY", 16, 6) == 0);
}

static bool frame_pixel(const std::vector<uint8_t>& frame,
                        unsigned x, unsigned y) {
  return (frame[(y / 8) * HELP_WIDTH + x] & (1U << (y & 7))) != 0;
}

static void test_graphic_help(void) {
  reset_mocks();
  input_keys = {MK61_APP_KEY_DIGIT_1, MK61_APP_KEY_OK, MK61_APP_KEY_OK};
  assert(show_graphic_intro(&app_services) == HELP_DONE);
  assert(input_key_index == input_keys.size());
  assert(graphics_begins == 1);
  assert(graphics_ends == 1);
  assert(graphic_frames.size() == 2);
  for(unsigned x = 3; x < HELP_WIDTH - 3; ++x) {
    assert(frame_pixel(graphic_frames[0], x, 13));
    assert(frame_pixel(graphic_frames[1], x, 13));
  }
  assert(frame_pixel(graphic_frames[0], 4, 28));
  assert(frame_pixel(graphic_frames[0], 4, 39));
  assert(frame_pixel(graphic_frames[1], 10, 40));
  assert(frame_pixel(graphic_frames[1], 10, 51));

  reset_mocks();
  input_keys = {MK61_APP_KEY_OK, MK61_APP_KEY_ESC};
  assert(show_graphic_intro(&app_services) == HELP_EXIT);
  assert(graphic_frames.size() == 2);
  assert(graphics_begins == 1);
  assert(graphics_ends == 1);

  reset_mocks();
  expose_ui_font = false;
  assert(show_graphic_intro(&app_services) == HELP_UNAVAILABLE);
  assert(graphic_frames.empty());
  assert(graphics_begins == 0);
  assert(graphics_ends == 0);
}

static void test_frame_clipping(void) {
  help_clear();
  help_set_pixel(-1, 0);
  help_set_pixel(0, -1);
  help_set_pixel(HELP_WIDTH, 0);
  help_set_pixel(0, HELP_HEIGHT);
  for(unsigned index = 0; index < HELP_FRAME_BYTES; ++index)
    assert(help_frame[index] == 0);
  help_set_pixel(HELP_WIDTH - 1, HELP_HEIGHT - 1);
  assert(help_frame[HELP_FRAME_BYTES - 1] == 0x80);
}

int main(void) {
  app_api.millis_ms = mock_millis;
  app_api.service = mock_service;
  app_api.delay_ms = mock_delay;
  app_api.display_clear = mock_display_clear;
  app_api.display_write_utf8 = mock_display_write;
  app_api.key_wait = mock_key_wait;
  app_api.magic = MK61_APP_API_MAGIC;
  app_api.version = MK61_APP_API_VERSION;
  app_api.struct_size = sizeof(app_api);
  app_api.capabilities = MK61_APP_CAP_GRAPHICS;
  app_api.graphics_available = mock_graphics_available;
  app_api.graphics_width = mock_graphics_width;
  app_api.graphics_height = mock_graphics_height;
  app_api.graphics_begin = mock_graphics_begin;
  app_api.graphics_present = mock_graphics_present;
  app_api.graphics_end = mock_graphics_end;
  mk61_api = &app_api;
  app_services.keyboard_mapping = &app_keys;
  app_services.call = mock_call;

  test_direct_sms_entry();
  test_space_and_backspace();
  test_page_wrapping();
  test_help_layout();
  test_pages_require_ok();
  test_graphic_help();
  test_frame_clipping();
  puts("eliza APP UI tests passed");
  return 0;
}
