#include "mk61_app.h"
#include "eliza_engine.h"

#define SMS_SHIFT_K 2U

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
  static const char instructions[] =
    "ELIZA / DOCTOR. SMS: 1 PQRS, 2 TUV, 3 WXYZ, 4 GHI, 5 JKL, "
    "6 MNO, 7 SPACE, 8 ABC, 9 DEF. 0 COMMITS A LETTER; CX ERASES; "
    "OK SENDS; ESC EXITS. PRESS ANY KEY.";
  static const char greeting[] =
    "HOW DO YOU DO. PLEASE TELL ME YOUR PROBLEM.";
  static const char goodbye[] =
    "GOODBYE. IT WAS NICE TALKING TO YOU.";
  static const char service_error[] =
    "ELIZA NEEDS THE EDITOR SERVICE FROM THE CURRENT SYSTEM APP SET.";
  const uint32_t required = MK61_APP_CAP_TIME | MK61_APP_CAP_TEXT_DISPLAY |
                            MK61_APP_CAP_KEYBOARD;
  const mk61_app_services* services;
  uint32_t columns;
  uint32_t rows;
  eliza_state state;
  char input[ELIZA_INPUT_BYTES];
  char reply[ELIZA_REPLY_BYTES];

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
  if(!show_pages(instructions, columns, rows)) return MK61_APP_OK;
  if(!show_pages(greeting, columns, rows)) return MK61_APP_OK;
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
