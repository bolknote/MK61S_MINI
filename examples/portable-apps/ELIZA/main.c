#include "mk61_app.h"
#include "eliza_engine.h"

#define SMS_SHIFT_K 2U
#define HELP_WIDTH 192U
#define HELP_HEIGHT 64U
#define HELP_FRAME_BYTES (HELP_WIDTH * HELP_HEIGHT / 8U)
#define HELP_FONT_FAMILY 1U
#define HELP_FONT_SIZE 12U

enum help_result {
  HELP_UNAVAILABLE = -1,
  HELP_EXIT = 0,
  HELP_DONE = 1
};

static uint8_t help_frame[HELP_FRAME_BYTES];

static const char key_help[] =
  "ELIZA SMS KEYS\n"
  "1:PQRS   2:TUV\n"
  "3:WXYZ   4:GHI\n"
  "5:JKL    6:MNO\n"
  "7:SPACE  8:ABC\n"
  "9:DEF  OK:NEXT";

static const char control_help[] =
  "HOW TO TYPE\n"
  "SAME KEY=CYCLE\n"
  "0=ACCEPT LETTER\n"
  "CX=ERASE\n"
  "OK=SEND ESC=EXIT\n"
  "OK: NEXT";

static const char greeting[] =
  "HOW DO YOU DO?\n"
  "PLEASE TELL ME\n"
  "YOUR PROBLEM.\n"
  "OK: START";

static const char goodbye[] =
  "GOODBYE. IT WAS NICE TALKING TO YOU.";

static const char service_error[] =
  "ELIZA NEEDS THE EDITOR SERVICE FROM THE CURRENT SYSTEM APP SET.";

static void help_clear(void) {
  uint32_t index;
  for(index = 0; index < HELP_FRAME_BYTES; ++index) help_frame[index] = 0;
}

static void help_set_pixel(int32_t x, int32_t y) {
  if(x < 0 || y < 0 || x >= (int32_t) HELP_WIDTH ||
     y >= (int32_t) HELP_HEIGHT) return;
  help_frame[((uint32_t) y / 8U) * HELP_WIDTH + (uint32_t) x] |=
      (uint8_t) (1U << ((uint32_t) y & 7U));
}

static void help_horizontal_line(int32_t x, int32_t y, uint32_t width) {
  uint32_t offset;
  for(offset = 0; offset < width; ++offset)
    help_set_pixel(x + (int32_t) offset, y);
}

static void help_rectangle(int32_t x, int32_t y,
                           uint32_t width, uint32_t height) {
  uint32_t offset;
  if(width == 0 || height == 0) return;
  for(offset = 0; offset < width; ++offset) {
    help_set_pixel(x + (int32_t) offset, y);
    help_set_pixel(x + (int32_t) offset, y + (int32_t) height - 1);
  }
  for(offset = 1; offset + 1 < height; ++offset) {
    help_set_pixel(x, y + (int32_t) offset);
    help_set_pixel(x + (int32_t) width - 1, y + (int32_t) offset);
  }
}

static int help_glyph(const mk61_app_services* services, uint32_t codepoint,
                      mk61_service_ui_glyph* glyph) {
  uint32_t index;
  uint32_t stride;
  uint8_t* bytes = (uint8_t*) glyph;
  for(index = 0; index < sizeof(*glyph); ++index) bytes[index] = 0;
  glyph->family = HELP_FONT_FAMILY;
  glyph->size = HELP_FONT_SIZE;
  if(!services->call(MK61_SERVICE_UI_FONT, MK61_UI_FONT_GLYPH,
                     codepoint, sizeof(*glyph), glyph)) return 0;
  stride = ((uint32_t) glyph->width + 7U) / 8U;
  return glyph->family == HELP_FONT_FAMILY &&
      glyph->size == HELP_FONT_SIZE && glyph->width <= 16U &&
      glyph->height <= 16U && glyph->advance != 0U &&
      glyph->advance <= 16U && glyph->bearing_x <= 16U &&
      glyph->bearing_y >= -16 && glyph->bearing_y <= 16 &&
      stride * glyph->height <= sizeof(glyph->pixels) &&
      (glyph->width == 0U || glyph->height != 0U);
}

static int help_measure(const mk61_app_services* services, const char* text,
                        uint32_t* width) {
  uint32_t measured = 0;
  while(*text != 0) {
    mk61_service_ui_glyph glyph;
    if(!help_glyph(services, (uint8_t) *text, &glyph) ||
       measured > HELP_WIDTH - glyph.advance) return 0;
    measured += glyph.advance;
    ++text;
  }
  *width = measured;
  return 1;
}

static int help_draw_text(const mk61_app_services* services, int32_t x,
                          int32_t baseline, const char* text) {
  int32_t pen = x;
  while(*text != 0) {
    mk61_service_ui_glyph glyph;
    uint32_t row;
    uint32_t column;
    uint32_t stride;
    if(!help_glyph(services, (uint8_t) *text, &glyph)) return 0;
    stride = ((uint32_t) glyph.width + 7U) / 8U;
    for(row = 0; row < glyph.height; ++row) {
      for(column = 0; column < glyph.width; ++column) {
        if((glyph.pixels[row * stride + column / 8U] &
            (uint8_t) (0x80U >> (column & 7U))) != 0) {
          help_set_pixel(pen + glyph.bearing_x + (int32_t) column,
                         baseline - glyph.bearing_y + (int32_t) row);
        }
      }
    }
    pen += glyph.advance;
    ++text;
  }
  return 1;
}

static int help_draw_centered(const mk61_app_services* services,
                              int32_t baseline, const char* text) {
  uint32_t width;
  if(!help_measure(services, text, &width)) return 0;
  return help_draw_text(services, (HELP_WIDTH - (int32_t) width) / 2,
                        baseline, text);
}

static int help_draw_right(const mk61_app_services* services,
                           int32_t baseline, const char* text) {
  uint32_t width;
  if(!help_measure(services, text, &width) || width + 4U > HELP_WIDTH) return 0;
  return help_draw_text(services, HELP_WIDTH - 4 - (int32_t) width,
                        baseline, text);
}

static int help_draw_header(const mk61_app_services* services,
                            const char* page) {
  if(!help_draw_text(services, 4, 10, "ELIZA / DOCTOR") ||
     !help_draw_right(services, 10, page)) return 0;
  help_horizontal_line(3, 13, HELP_WIDTH - 6U);
  return 1;
}

static int help_draw_key_label(const mk61_app_services* services,
                               int32_t x, int32_t baseline,
                               const char* key, const char* label) {
  uint32_t key_width;
  uint32_t box_width;
  if(!help_measure(services, key, &key_width)) return 0;
  box_width = key_width + 6U;
  help_rectangle(x, baseline - 10, box_width, 12);
  return help_draw_text(services, x + 3, baseline, key) &&
      help_draw_text(services, x + (int32_t) box_width + 3, baseline, label);
}

static int help_render_keys(const mk61_app_services* services) {
  help_clear();
  return help_draw_header(services, "1/2  OK >") &&
      help_draw_centered(services, 25, "TAP KEY AGAIN TO CHANGE") &&
      help_draw_key_label(services, 4, 38, "1", "PQRS") &&
      help_draw_key_label(services, 67, 38, "2", "TUV") &&
      help_draw_key_label(services, 130, 38, "3", "WXYZ") &&
      help_draw_key_label(services, 4, 50, "4", "GHI") &&
      help_draw_key_label(services, 67, 50, "5", "JKL") &&
      help_draw_key_label(services, 130, 50, "6", "MNO") &&
      help_draw_key_label(services, 4, 62, "7", "SPACE") &&
      help_draw_key_label(services, 67, 62, "8", "ABC") &&
      help_draw_key_label(services, 130, 62, "9", "DEF");
}

static int help_render_start(const mk61_app_services* services) {
  help_clear();
  return help_draw_header(services, "2/2  OK >") &&
      help_draw_centered(services, 26, "HOW DO YOU DO?") &&
      help_draw_centered(services, 38, "TELL ME YOUR PROBLEM") &&
      help_draw_key_label(services, 10, 50, "0", "ACCEPT") &&
      help_draw_key_label(services, 104, 50, "CX", "ERASE") &&
      help_draw_key_label(services, 10, 62, "OK", "SEND") &&
      help_draw_key_label(services, 104, 62, "ESC", "EXIT");
}

static int help_wait_for_ok(void) {
  for(;;) {
    const int32_t key = (int32_t) mk61_api->key_wait();
    if(key == MK61_APP_KEY_ESC) return 0;
    if(key == MK61_APP_KEY_OK) return 1;
  }
}

static int show_graphic_intro(const mk61_app_services* services) {
  const uint16_t graphics_api_size = (uint16_t)
      (offsetof(mk61_app_api, graphics_end) + sizeof(mk61_api->graphics_end));
  uint32_t service_capabilities;

  if(!mk61_app_api_compatible(mk61_api, graphics_api_size,
                              MK61_APP_CAP_GRAPHICS) ||
     mk61_api->graphics_available == NULL ||
     mk61_api->graphics_width == NULL || mk61_api->graphics_height == NULL ||
     mk61_api->graphics_begin == NULL || mk61_api->graphics_present == NULL ||
     mk61_api->graphics_end == NULL) return HELP_UNAVAILABLE;
  service_capabilities = services->call(MK61_SERVICE_CAPABILITIES,
                                        0, 0, 0, NULL);
  if((service_capabilities & MK61_SERVICE_CAP_UI_FONT) == 0 ||
     !mk61_api->graphics_available() || !mk61_api->graphics_begin())
    return HELP_UNAVAILABLE;
  if(mk61_api->graphics_width() != HELP_WIDTH ||
     mk61_api->graphics_height() != HELP_HEIGHT) {
    mk61_api->graphics_end();
    return HELP_UNAVAILABLE;
  }
  if(!help_render_keys(services) ||
     !mk61_api->graphics_present(help_frame, sizeof(help_frame))) {
    mk61_api->graphics_end();
    return HELP_UNAVAILABLE;
  }
  if(!help_wait_for_ok()) {
    mk61_api->graphics_end();
    return HELP_EXIT;
  }
  if(!help_render_start(services) ||
     !mk61_api->graphics_present(help_frame, sizeof(help_frame))) {
    mk61_api->graphics_end();
    return HELP_UNAVAILABLE;
  }
  if(!help_wait_for_ok()) {
    mk61_api->graphics_end();
    return HELP_EXIT;
  }
  mk61_api->graphics_end();
  return HELP_DONE;
}

static int time_reached(uint32_t now, uint32_t target) {
  return (int32_t) (now - target) >= 0;
}

static const char* skip_separators(const char* text) {
  while(*text == ' ' || *text == '\n' || *text == '\r' || *text == '\t') ++text;
  return text;
}

/* Draw one word-wrapped page and return the first byte of the next page. */
static const char* draw_page(const char* text, uint32_t columns, uint32_t rows) {
  char line[MK61_APP_MAX_TEXT_BYTES + 1U];
  uint32_t row;
  text = skip_separators(text);
  mk61_api->display_clear();
  for(row = 0; row < rows && *text != 0; ++row) {
    uint32_t available = 0;
    uint32_t take;
    uint32_t index;
    uint32_t last_space = 0;

    while(text[available] != 0 && text[available] != '\n' &&
          text[available] != '\r' && available < columns) {
      if(text[available] == ' ') last_space = available;
      ++available;
    }
    take = available;
    if(available == columns && text[available] != 0 &&
       text[available] != ' ' && text[available] != '\n' &&
       text[available] != '\r' && last_space != 0) {
      take = last_space;
    }
    while(take != 0 && text[take - 1] == ' ') --take;
    for(index = 0; index < take; ++index) line[index] = text[index];
    line[take] = 0;
    if(take != 0) mk61_api->display_write_utf8(0, row, line, take);

    text += available == columns && take == last_space ? last_space : available;
    text = skip_separators(text);
  }
  return text;
}

static int show_pages(const char* text, uint32_t columns, uint32_t rows) {
  text = draw_page(text, columns, rows);
  for(;;) {
    const int32_t key = (int32_t) mk61_api->key_wait();
    if(key == MK61_APP_KEY_ESC) return 0;
    if(key != MK61_APP_KEY_OK) continue;
    if(*text == 0) return 1;
    text = draw_page(text, columns, rows);
  }
}

static int sms_letter_key(const mk61_service_keyboard* keys, int32_t key) {
  uint32_t digit;
  for(digit = 1; digit <= 9; ++digit) {
    if(digit == 7) continue;
    if(key == keys->digit[digit]) return 1;
  }
  return 0;
}

static void end_editor_view(const mk61_app_services* services) {
  services->call(MK61_SERVICE_DISPLAY, MK61_SERVICE_DISPLAY_CURSOR_OFF,
                 0, 0, NULL);
  services->call(MK61_SERVICE_DISPLAY, MK61_SERVICE_DISPLAY_END_VIEWPORT,
                 0, 0, NULL);
  services->call(MK61_SERVICE_DISPLAY, MK61_SERVICE_DISPLAY_END_UI_TEXT,
                 0, 0, NULL);
}

/* Returns 1 for a submitted line and 0 for ESC. */
static int read_sms_line(const mk61_app_services* services,
                         char* source, uint32_t capacity) {
  const mk61_service_keyboard* keys = services->keyboard_mapping;
  mk61_service_edit_key editor = {0};
  uint32_t dirty = 1;

  source[0] = 0;
  editor.source = source;
  editor.capacity = capacity;
  editor.sms_key = -1;
  editor.keys[0] = keys->left;
  editor.keys[1] = keys->left;
  editor.keys[2] = keys->right;
  editor.keys[3] = keys->right;
  editor.keys[4] = keys->ok;
  editor.keys[5] = keys->ok;
  editor.keys[6] = keys->esc;
  editor.keys[7] = keys->esc;
  editor.keys[8] = keys->shg_left;
  editor.keys[9] = keys->shg_right;
  editor.keys[10] = keys->k;
  editor.keys[11] = keys->alpha;
  editor.keys[12] = keys->pp;
  editor.ok_text = "";
  editor.options = 1U; /* resident editor SMS mode */
  editor.backspace_key = keys->cx;

  for(;;) {
    const uint32_t now = mk61_api->millis_ms();
    int32_t key;
    if(editor.sms_active && time_reached(now, editor.sms_deadline)) {
      editor.sms_active = 0;
      editor.sms_key = -1;
      editor.sms_index = 0;
      editor.sms_deadline = 0;
      dirty = 1;
    }
    if(dirty) {
      mk61_service_editor view = {
        source, editor.length, editor.cursor, editor.top, editor.sms_active
      };
      services->call(MK61_SERVICE_EDITOR_SCROLL, 0, 0, 0, &view);
      editor.top = view.top;
      services->call(MK61_SERVICE_EDITOR_DRAW, 0, 0, 0, &view);
      dirty = 0;
    }

    mk61_api->service();
    services->call(MK61_SERVICE_KEYBOARD, MK61_SERVICE_KEY_SCAN, 0, 0, NULL);
    key = (int32_t) services->call(MK61_SERVICE_KEYBOARD,
                                  MK61_SERVICE_KEY_GET, 0, 0, NULL);
    if(key < 0) {
      mk61_api->delay_ms(1);
      continue;
    }
    if(key == keys->esc) {
      end_editor_view(services);
      return 0;
    }
    if(key == keys->ok) {
      if(editor.length != 0) {
        end_editor_view(services);
        return 1;
      }
      continue;
    }

    /* Enter SMS letters directly, instead of requiring K before each run. */
    if(!editor.sms_active && editor.shift == 0 &&
       (sms_letter_key(keys, key) || key == keys->digit[7])) {
      editor.shift = SMS_SHIFT_K;
    }
    editor.key = key;
    editor.now = now;
    dirty = services->call(MK61_SERVICE_EDITOR_KEY, 0, 0, 0, &editor) != 0;
  }
}

int main(void) {
  const uint32_t required = MK61_APP_CAP_TIME | MK61_APP_CAP_TEXT_DISPLAY |
                            MK61_APP_CAP_KEYBOARD;
  const mk61_app_services* services;
  uint32_t columns;
  uint32_t rows;
  eliza_state state;
  char input[ELIZA_INPUT_BYTES];
  char reply[ELIZA_REPLY_BYTES];
  int intro;

  if(!mk61_app_api_compatible(mk61_api, sizeof(*mk61_api), required))
    return MK61_APP_RUNTIME_ERROR;
  columns = mk61_api->display_columns();
  rows = mk61_api->display_rows();
  if(columns == 0 || rows == 0) return MK61_APP_UNSUPPORTED_DISPLAY;
  if(columns > MK61_APP_MAX_TEXT_BYTES) columns = MK61_APP_MAX_TEXT_BYTES;

  services = mk61_app_get_services(mk61_api, MK61_SERVICE_CAP_UI |
                                             MK61_SERVICE_CAP_EDITOR);
  if(services == NULL || services->keyboard_mapping == NULL) {
    show_pages(service_error, columns, rows);
    return MK61_APP_RUNTIME_ERROR;
  }

  eliza_init(&state);
  intro = show_graphic_intro(services);
  if(intro == HELP_EXIT) return MK61_APP_OK;
  if(intro == HELP_UNAVAILABLE) {
    if(!show_pages(key_help, columns, rows)) return MK61_APP_OK;
    if(!show_pages(control_help, columns, rows)) return MK61_APP_OK;
    if(!show_pages(greeting, columns, rows)) return MK61_APP_OK;
  }
  while(read_sms_line(services, input, sizeof(input))) {
    if(eliza_is_goodbye(input)) {
      show_pages(goodbye, columns, rows);
      return MK61_APP_OK;
    }
    eliza_reply(&state, input, reply, sizeof(reply));
    if(!show_pages(reply, columns, rows)) return MK61_APP_OK;
  }
  return MK61_APP_OK;
}
