#include "startup_splash.hpp"

#include <Arduino.h>

#include "config.h"
#include "cross_hal.h"
#include "display.hpp"
#include "entropy_pool.hpp"
#include "keyboard.h"
#include "runtime_safety.hpp"

namespace startup_splash {
namespace {

static constexpr u8 CUSTOM_CHARS = 8;
static constexpr u8 CUSTOM_CHAR_ROWS = 8;

#if defined(MK61s)
static constexpr u8 CUSTOM_CHAR[CUSTOM_CHARS][CUSTOM_CHAR_ROWS] = {
  {0x07, 0x0F, 0x1F, 0x1F, 0x1F, 0x1F, 0x1F, 0x1F},
  {0x07, 0x0F, 0x1F, 0x1F, 0x1F, 0x17, 0x07, 0x07},
  {0x1F, 0x1F, 0x1F, 0x1F, 0x1F, 0x1F, 0x1F, 0x1F},
  {0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07},
  {0x03, 0x07, 0x0F, 0x1F, 0x1E, 0x1C, 0x18, 0x10},
  {0x10, 0x18, 0x1C, 0x1E, 0x1F, 0x0F, 0x07, 0x03},
  {0x1F, 0x1F, 0x1F, 0x00, 0x00, 0x00, 0x1F, 0x1F},
  {0x1F, 0x1F, 0x1F, 0x07, 0x07, 0x0F, 0x1E, 0x1C}
};

static constexpr u8 LOGO[ROWS][COLS] = {
  {0, 1, 1, ' ', 0, 4, ' ', 0, 6, ' ', 4, 2, ' ', 0, 6, 6},
  {2, 3, 3, ' ', 2, 5, ' ', 2, 7, ' ', ' ', 2, ' ', 6, 6, 7}
};
#elif defined(MK52s)
static constexpr u8 CUSTOM_CHAR[CUSTOM_CHARS][CUSTOM_CHAR_ROWS] = {
  {0x1F, 0x1F, 0x1F, 0x1F, 0x1F, 0x1F, 0x1F, 0x1F},
  {0x0F, 0x1F, 0x1F, 0x17, 0x07, 0x07, 0x07, 0x07},
  {0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07},
  {0x07, 0x0F, 0x1F, 0x1F, 0x1E, 0x1C, 0x18, 0x10},
  {0x10, 0x18, 0x1C, 0x1E, 0x1F, 0x1F, 0x0F, 0x07},
  {0x1F, 0x1F, 0x1F, 0x00, 0x00, 0x00, 0x00, 0x00},
  {0x00, 0x00, 0x00, 0x00, 0x00, 0x1F, 0x1F, 0x1F},
  {0x1F, 0x1F, 0x1F, 0x00, 0x00, 0x00, 0x1F, 0x1F}
};

static constexpr u8 LOGO[ROWS][COLS] = {
  {0, 1, 1, ' ', 0, 3, ' ', 0, 5, ' ', 5, 0, ' ', 0, 7, 7},
  {0, 2, 2, ' ', 0, 4, ' ', 6, 0, ' ', 0, 6, ' ', 6, 6, 0}
};
#else
  #error "Startup splash requires an MK61s or MK52s model"
#endif

void loadCustomChars(MK61Display& display) {
  for(u8 slot = 0; slot < CUSTOM_CHARS; slot++) {
    display.createChar(slot, const_cast<u8*>(CUSTOM_CHAR[slot]));
  }
}

void drawFrame(MK61Display& display, const char* model, const char* version, u8 frame) {
  const char* const text[ROWS] = {model, version};
  u8 row_buffer[COLS];

  MK61DisplayUpdate update(display);
  for(u8 row = 0; row < ROWS; row++) {
    composeRow(text[row], LOGO[row], frame, row_buffer);
    display.setCursor(0, row);
    for(u8 col = 0; col < COLS; col++) display.write(row_buffer[col]);
  }
}

bool pollEscape(void) {
  const isize scan_code = kbd::scan();
  if(scan_code < 0) return false;

  while(kbd::get_key() >= 0) {}
  return scan_code == KEY_ESC_PRESS;
}

bool waitOrEscape(t_time_ms duration_ms) {
  const t_time_ms deadline = millis() + duration_ms;
  do {
    entropy_pool::poll_startup();
    if(pollEscape()) return true;
    delay(1);
  } while(!runtime_safety::time_reached(millis(), deadline));
  return false;
}

} // namespace

Result show(MK61Display& display, const char* model, const char* version) {
  loadCustomChars(display);
  drawFrame(display, model, version, 0);
  if(waitOrEscape(LOGO_HOLD_MS)) return Result::SKIPPED;

  for(u8 frame = 1; frame <= FINAL_FRAME; frame++) {
    drawFrame(display, model, version, frame);
    if(waitOrEscape(FRAME_MS)) return Result::SKIPPED;
  }

  return Result::COMPLETED;
}

} // namespace startup_splash
