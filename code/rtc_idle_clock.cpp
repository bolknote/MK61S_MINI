#include "rtc_idle_clock.hpp"

#include "display.hpp"
#include "rtc_clock.hpp"
#include "rtc_idle_clock_core.hpp"
#include "runtime_safety.hpp"

#include <string.h>

namespace rtc_idle_clock {

#if defined(MK61_DISPLAY_LCD1602)
namespace {

static constexpr u8 CLOCK_ROW = 0;
static constexpr u8 FIRST_CLOCK_COLUMN = lcd_display::COLS - CLOCK_GLYPH_COUNT;
static constexpr t_time_ms RTC_POLL_INTERVAL_MS = 500;

struct SlotLease {
  bool active;
  bool previous_valid;
  u8 slot;
  u8 previous[GLYPH_ROWS];
  u8 installed[GLYPH_ROWS];
};

struct OverlayState {
  bool leased;
  bool visible;
  u8 hour;
  u8 minute;
  u8 slots[CLOCK_GLYPH_COUNT];
  SlotLease leases[CLOCK_GLYPH_COUNT];
};

struct GraphicOverlayState {
  bool visible;
  u8 hour;
  u8 minute;
};

static OverlayState state = {};
static GraphicOverlayState graphic_state = {};
static bool reconcile_pending = false;
static t_time_ms next_rtc_poll_ms = 0;

u8 clock_column(u8 index) {
  return (u8) (FIRST_CLOCK_COLUMN + index);
}

bool clock_cell_value(MK61Display& display, u8 index, u8& value) {
  return display.readCell(clock_column(index), CLOCK_ROW, value);
}

bool clock_cells_blank(MK61Display& display) {
  for(u8 index = 0; index < CLOCK_GLYPH_COUNT; index++) {
    u8 value = 0;
    if(!clock_cell_value(display, index, value) || value != (u8) ' ') return false;
  }
  return true;
}

bool clock_cells_owned(MK61Display& display) {
  if(!state.leased || !state.visible) return false;
  for(u8 index = 0; index < CLOCK_GLYPH_COUNT; index++) {
    u8 value = 0;
    if(!clock_cell_value(display, index, value) || value != state.slots[index]) return false;
  }
  return true;
}

u8 slots_used_outside_clock(MK61Display& display) {
  u8 result = 0;
  for(u8 row = 0; row < display.rows(); row++) {
    for(u8 column = 0; column < display.cols(); column++) {
      if(row == CLOCK_ROW && column >= FIRST_CLOCK_COLUMN) continue;
      u8 value = 0;
      if(!display.readCell(column, row, value)) continue;
      const u8 slot = slot_for_character(value);
      if(slot != INVALID_SLOT) result |= (u8) 1 << slot;
    }
  }
  return result;
}

bool slot_still_contains(MK61Display& display, const SlotLease& lease) {
  u8 current[GLYPH_ROWS];
  return lease.active && display.copyCustomChar(lease.slot, current) &&
         memcmp(current, lease.installed, sizeof(current)) == 0;
}

bool overlay_leases_intact(MK61Display& display) {
  if(!state.leased) return false;
  for(u8 index = 0; index < CLOCK_GLYPH_COUNT; index++) {
    if(!slot_still_contains(display, state.leases[index])) return false;
  }
  return true;
}

void restore_lease(MK61Display& display, SlotLease& lease) {
  if(!lease.active) return;
  // Если другой экран уже перезаписал слот, его новое содержимое важнее
  // сохранённого нами состояния.
  if(slot_still_contains(display, lease)) {
    if(lease.previous_valid) display.createChar(lease.slot, lease.previous);
    else display.clearCustomChar(lease.slot);
  }
  lease.active = false;
}

void hide_cells(MK61Display& display) {
  if(!state.leased || !state.visible) return;

  bool owned[CLOCK_GLYPH_COUNT] = {};
  for(u8 index = 0; index < CLOCK_GLYPH_COUNT; index++) {
    u8 value = 0;
    owned[index] = clock_cell_value(display, index, value) && value == state.slots[index];
  }

  {
    MK61DisplayUpdate update(display);
    for(u8 index = 0; index < CLOCK_GLYPH_COUNT;) {
      if(!owned[index]) {
        index++;
        continue;
      }
      display.setCursor(clock_column(index), CLOCK_ROW);
      do {
        display.write((u8) ' ');
        index++;
      } while(index < CLOCK_GLYPH_COUNT && owned[index]);
    }
  }

  state.visible = false;
  reconcile_pending = true;
}

void release_overlay(MK61Display& display) {
  if(!state.leased) return;

  hide_cells(display);
  for(u8 index = 0; index < CLOCK_GLYPH_COUNT; index++) {
    restore_lease(display, state.leases[index]);
  }
  // createChar оставляет HD44780 в адресном пространстве CGRAM.
  display.setCursor(0, 0);
  state = {};
  reconcile_pending = false;
}

void lease_slot(MK61Display& display, SlotLease& lease, u8 slot,
                const u8 glyph[GLYPH_ROWS]) {
  lease = {};
  lease.active = true;
  lease.slot = slot;
  lease.previous_valid = display.copyCustomChar(slot, lease.previous);
  memcpy(lease.installed, glyph, sizeof(lease.installed));
  display.createChar(slot, lease.installed);
}

bool build_time_glyphs(const rtc_clock::DateTime& value,
                       u8 glyphs[CLOCK_GLYPH_COUNT][GLYPH_ROWS]) {
  return build_hour_tens_glyph(value.hour, glyphs[0]) &&
         build_hour_units_colon_glyph(value.hour, glyphs[1]) &&
         build_pair_glyph(value.minute, glyphs[2]);
}

void show_leased_cells(MK61Display& display) {
  MK61DisplayUpdate update(display);
  display.setCursor(FIRST_CLOCK_COLUMN, CLOCK_ROW);
  for(u8 index = 0; index < CLOCK_GLYPH_COUNT; index++) {
    display.write(state.slots[index]);
  }
  state.visible = true;
}

bool show_time(MK61Display& display, const rtc_clock::DateTime& value) {
  if(!clock_cells_blank(display)) return false;

  Slots slots = {};
  if(!select_slots(slots_used_outside_clock(display), slots)) return false;

  u8 glyphs[CLOCK_GLYPH_COUNT][GLYPH_ROWS];
  if(!build_time_glyphs(value, glyphs)) return false;

  state = {};
  state.hour = value.hour;
  state.minute = value.minute;
  state.slots[0] = slots.hour_tens;
  state.slots[1] = slots.hour_units_colon;
  state.slots[2] = slots.minute;
  for(u8 index = 0; index < CLOCK_GLYPH_COUNT; index++) {
    lease_slot(display, state.leases[index], state.slots[index], glyphs[index]);
  }
  state.leased = true;
  show_leased_cells(display);
  reconcile_pending = false;
  return true;
}

bool overlay_slots_conflict(MK61Display& display) {
  if(!state.leased) return false;
  const u8 used = slots_used_outside_clock(display);
  for(u8 index = 0; index < CLOCK_GLYPH_COUNT; index++) {
    if((used & ((u8) 1 << state.slots[index])) != 0) return true;
  }
  return false;
}

bool validate_overlay(MK61Display& display) {
  if(!state.leased) return false;
  if(!overlay_leases_intact(display) || overlay_slots_conflict(display)) {
    release_overlay(display);
    return false;
  }
  if(state.visible) {
    if(clock_cells_owned(display)) return true;
    release_overlay(display);
    return false;
  }
  if(!clock_cells_blank(display)) {
    release_overlay(display);
    return false;
  }
  show_leased_cells(display);
  return true;
}

bool update_time(MK61Display& display, const rtc_clock::DateTime& value) {
  if(!state.leased) return false;

  u8 glyphs[CLOCK_GLYPH_COUNT][GLYPH_ROWS];
  if(!build_time_glyphs(value, glyphs)) return false;

  bool changed = false;
  for(u8 index = 0; index < CLOCK_GLYPH_COUNT; index++) {
    SlotLease& lease = state.leases[index];
    if(memcmp(lease.installed, glyphs[index], GLYPH_ROWS) == 0) continue;
    memcpy(lease.installed, glyphs[index], GLYPH_ROWS);
    display.createChar(lease.slot, lease.installed);
    changed = true;
  }
  if(changed) {
    // Возвращаем контроллер из CGRAM в адресное пространство экрана.
    display.setCursor(0, 0);
  }
  state.hour = value.hour;
  state.minute = value.minute;
  return true;
}

void discard_lcd_overlay_state(void) {
  // Once USB Screen is attached all display calls target the 192x64 surface,
  // so an old HD44780 lease must not be restored through that interface.  The
  // physical LCD is dark and receives a complete redraw after USB Screen exits.
  state = {};
  reconcile_pending = false;
}

void hide_graphic_overlay(MK61Display& display) {
  if(!graphic_state.visible) return;
  if(display.graphicsMode()) display.hideTopRightOverlay();
  graphic_state = {};
}

void poll_graphic_overlay(MK61Display& display, bool calculator_context,
                          bool calculator_idle) {
  if(state.leased) discard_lcd_overlay_state();

  if(!calculator_context || !calculator_idle) {
    hide_graphic_overlay(display);
    if(!calculator_context) next_rtc_poll_ms = 0;
    return;
  }

  const t_time_ms now = millis();
  if(next_rtc_poll_ms != 0 &&
     !runtime_safety::time_reached(now, next_rtc_poll_ms)) return;
  next_rtc_poll_ms = now + RTC_POLL_INTERVAL_MS;

  rtc_clock::DateTime value = {};
  if(!rtc_clock::read(value)) {
    hide_graphic_overlay(display);
    return;
  }
  if(graphic_state.visible && graphic_state.hour == value.hour &&
     graphic_state.minute == value.minute) return;

  u32 rows[GRAPHIC_CLOCK_HEIGHT];
  if(!build_graphic_clock(value.hour, value.minute, rows) ||
     !display.showTopRightOverlay(rows, GRAPHIC_CLOCK_WIDTH,
                                  GRAPHIC_CLOCK_HEIGHT,
                                  GRAPHIC_CLOCK_CLEAR_BORDER)) {
    hide_graphic_overlay(display);
    return;
  }
  graphic_state.visible = true;
  graphic_state.hour = value.hour;
  graphic_state.minute = value.minute;
}

} // анонимное пространство имён

void hide(MK61Display& display) {
  if(display.graphicsMode()) {
    discard_lcd_overlay_state();
    hide_graphic_overlay(display);
    return;
  }
  // The USB surface no longer exists after detaching; only its bookkeeping
  // remains and can be discarded without touching the physical LCD.
  graphic_state = {};
  // На обычном нажатии освобождать CGRAM не нужно: достаточно временно
  // убрать часы с экрана. Слоты проверяются перед повторным показом.
  hide_cells(display);
}

void poll(MK61Display& display, bool calculator_context, bool calculator_idle) {
  if(display.graphicsMode()) {
    poll_graphic_overlay(display, calculator_context, calculator_idle);
    return;
  }
  graphic_state = {};
  if(!calculator_context) {
    release_overlay(display);
    next_rtc_poll_ms = 0;
    return;
  }

  if(!calculator_idle) {
    hide_cells(display);
    return;
  }

  bool overlay_validated = false;
  if(reconcile_pending) {
    reconcile_pending = false;
    if(state.leased) validate_overlay(display);
    overlay_validated = true;
  }

  const t_time_ms now = millis();
  if(next_rtc_poll_ms != 0 &&
     !runtime_safety::time_reached(now, next_rtc_poll_ms)) return;
  next_rtc_poll_ms = now + RTC_POLL_INTERVAL_MS;

  // Полный просмотр теневого экрана выполняется только два раза в секунду
  // или после нажатия, а не в каждом обороте loop().
  if(state.leased && !overlay_validated) validate_overlay(display);

  rtc_clock::DateTime value = {};
  if(!rtc_clock::read(value)) {
    release_overlay(display);
    return;
  }

  if(state.leased && state.hour == value.hour && state.minute == value.minute) return;
  if(state.leased && update_time(display, value)) return;
  release_overlay(display);
  show_time(display, value);
}

#elif defined(MK61_DISPLAY_UC1609)

namespace {

static constexpr t_time_ms RTC_POLL_INTERVAL_MS = 500;

struct GraphicOverlayState {
  bool visible;
  u8 hour;
  u8 minute;
};

static GraphicOverlayState state = {};
static t_time_ms next_rtc_poll_ms = 0;

void hide_overlay(MK61Display& display) {
  if(!state.visible) return;
  display.hideTopRightOverlay();
  state.visible = false;
}

} // анонимное пространство имён

void hide(MK61Display& display) {
  hide_overlay(display);
}

void poll(MK61Display& display, bool calculator_context, bool calculator_idle) {
  if(!calculator_context) {
    hide_overlay(display);
    next_rtc_poll_ms = 0;
    return;
  }

  if(!calculator_idle) {
    hide_overlay(display);
    return;
  }

  const t_time_ms now = millis();
  if(next_rtc_poll_ms != 0 &&
     !runtime_safety::time_reached(now, next_rtc_poll_ms)) return;
  next_rtc_poll_ms = now + RTC_POLL_INTERVAL_MS;

  rtc_clock::DateTime value = {};
  if(!rtc_clock::read(value)) {
    hide_overlay(display);
    return;
  }
  if(state.visible && state.hour == value.hour && state.minute == value.minute) return;

  u32 rows[GRAPHIC_CLOCK_HEIGHT];
  if(!build_graphic_clock(value.hour, value.minute, rows) ||
     !display.showTopRightOverlay(rows, GRAPHIC_CLOCK_WIDTH,
                                  GRAPHIC_CLOCK_HEIGHT,
                                  GRAPHIC_CLOCK_CLEAR_BORDER)) {
    hide_overlay(display);
    return;
  }
  state.visible = true;
  state.hour = value.hour;
  state.minute = value.minute;
}

#else

void hide(MK61Display&) {}
void poll(MK61Display&, bool, bool) {}

#endif

} // пространство имён rtc_idle_clock
