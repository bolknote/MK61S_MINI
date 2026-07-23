#include "config.h"

#if MK61_ANY_LOADABLE_MODULE

#include "loadable_app_api.hpp"

#include "Arduino.h"
#include "cross_hal.h"
#include "display.hpp"
#include "keyboard.h"
#include "keyboard_layout.hpp"
#include "lcd_ru.hpp"
#include "ledcontrol.h"
#include "runtime_safety.hpp"
#include "tools.hpp"

#include <string.h>

extern void idle_main_process(void);

namespace loadable_app {
namespace {

static u32 api_millis(void) {
  return millis();
}

static void api_service(void) {
  idle_main_process();
}

static void api_delay(u32 duration_ms) {
  if(duration_ms == 0) {
    idle_main_process();
    return;
  }
  const u32 started_at = millis();
  do {
    idle_main_process();
    delay(1);
  } while((u32) (millis() - started_at) < duration_ms);
}

static u32 api_display_columns(void) {
  return main_lcd().cols();
}

static u32 api_display_rows(void) {
  return main_lcd().rows();
}

static u32 api_display_clear(void) {
  MK61DisplayUpdate update(main_lcd());
  main_lcd().clear();
  return 1;
}

static bool valid_utf8(const u8* text, u32 size) {
  u32 offset = 0;
  while(offset < size) {
    const u8 first = text[offset++];
    if(first == 0) return false;
    if(first < 0x80) continue;
    if((first & 0xE0) == 0xC0) {
      if(offset >= size || (text[offset] & 0xC0) != 0x80) return false;
      const u16 codepoint =
          (u16) (((first & 0x1F) << 6) | (text[offset] & 0x3F));
      if(codepoint < 0x80) return false;
      offset++;
      continue;
    }
    if((first & 0xF0) == 0xE0) {
      if(offset + 1 >= size || (text[offset] & 0xC0) != 0x80 ||
         (text[offset + 1] & 0xC0) != 0x80) return false;
      const u16 codepoint =
          (u16) (((first & 0x0F) << 12) |
                 ((text[offset] & 0x3F) << 6) |
                 (text[offset + 1] & 0x3F));
      if(codepoint < 0x800 ||
         (codepoint >= 0xD800 && codepoint <= 0xDFFF)) return false;
      offset += 2;
      continue;
    }
    // Текстовый API v1 принимает только BMP: именно его умеют оба дисплея.
    return false;
  }
  return true;
}

static u32 api_display_write_utf8(u32 column, u32 row,
                                  const char* text, u32 byte_length) {
  if(text == nullptr || byte_length > MAX_TEXT_BYTES ||
     column >= main_lcd().cols() || row >= main_lcd().rows() ||
     !valid_utf8((const u8*) text, byte_length)) return 0;
  char buffer[MAX_TEXT_BYTES + 1];
  if(byte_length != 0) memcpy(buffer, text, byte_length);
  buffer[byte_length] = 0;
  lcd_ru::print_at((u8) column, (u8) row, buffer,
                   (u8) (main_lcd().cols() - column));
  return 1;
}

static i32 normalize_key(i32 raw) {
  const keyboard_layout::Mapping& keys = keyboard_layout::ACTIVE;
  const int digit = keyboard_layout::digit_from_key(keys, raw);
  if(digit >= 0) return KEY_DIGIT_0 + digit;
  if(raw == keys.dot) return KEY_DECIMAL;
  if(raw == keys.add) return KEY_ADD;
  if(raw == keys.sub) return KEY_SUBTRACT;
  if(raw == keys.mul) return KEY_MULTIPLY;
  if(raw == keys.div) return KEY_DIVIDE;
  if(raw == keys.left) return KEY_LEFT;
  if(raw == keys.right) return KEY_RIGHT;
  if(raw == keys.shg_left) return KEY_SHIFT_LEFT;
  if(raw == keys.shg_right) return KEY_SHIFT_RIGHT;
  if(raw == keys.ok) return KEY_OK;
  if(raw == keys.esc) return KEY_ESC;
  if(raw == keys.run) return KEY_RUN;
  if(raw == keys.cx) return KEY_CLEAR;
  if(raw == keys.k) return KEY_K;
  if(raw == keys.alpha) return KEY_F;
  if(raw == keys.user) return KEY_USER;
  if(raw == keys.pp) return KEY_PP;
  if(raw == keys.bp) return KEY_BP;
  if(raw == keys.x_to_p) return KEY_X_TO_P;
  if(raw == keys.p_to_x) return KEY_P_TO_X;
  if(raw == keys.ret) return KEY_RETURN;
  if(raw == keys.frw) return KEY_FORWARD;
  if(raw == keys.bkw) return KEY_BACKWARD;
  return raw >= 0 ? KEY_RAW_BASE + raw : KEY_NONE;
}

static i32 api_key_poll(void) {
  idle_main_process();
  const i32 scan_code = (i32) kbd::scan_and_debounced();
  if(scan_code < 0) return KEY_NONE;
  kbd::exclude_before(scan_code);
  if((scan_code & (i32) key_state::RELEASED) != 0) return KEY_NONE;
  return normalize_key(scan_code);
}

static i32 api_key_wait(void) {
  for(;;) {
    const i32 key = api_key_poll();
    if(key != KEY_NONE) return key;
    delay(1);
  }
}

static void api_led_set(u32 enabled) {
  if(enabled) led::on(); else led::off();
}

static u32 api_led_blink(u32 count, u32 on_ms, u32 off_ms) {
  if(count == 0 || count > 65535U || on_ms > 60000U || off_ms > 60000U) {
    return 0;
  }
  led::blink((usize) count, (t_time_ms) on_ms, (t_time_ms) off_ms);
  return 1;
}

static u32 api_beep(u32 frequency_hz, u32 duration_ms,
                    u32 volume_percent) {
  if(frequency_hz > 65535U || duration_ms > 65535U ||
     volume_percent > 100U ||
     !runtime_safety::valid_sound_note(
         (u16) frequency_hz, (u16) duration_ms, (u8) volume_percent)) {
    return 0;
  }
  sound_scaled(PIN_BUZZER, (isize) frequency_hz, (usize) duration_ms,
               library_mk61::sound_volume(), (usize) volume_percent);
  return 1;
}

static void api_sound_stop(void) {
  sound_stop();
}

static const Api API = {
  API_MAGIC,
  API_VERSION,
  (u16) sizeof(Api),
  CAP_TIME | CAP_TEXT_DISPLAY | CAP_KEYBOARD | CAP_LED | CAP_SOUND,
  api_millis,
  api_service,
  api_delay,
  api_display_columns,
  api_display_rows,
  api_display_clear,
  api_display_write_utf8,
  api_key_poll,
  api_key_wait,
  api_led_set,
  api_led_blink,
  api_beep,
  api_sound_stop
};

} // namespace

const Api& resident_api(void) {
  return API;
}

} // namespace loadable_app

#endif
