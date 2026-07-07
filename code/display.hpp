#ifndef MK61_DISPLAY_HPP
#define MK61_DISPLAY_HPP

#include "config.h"
#include "rust_types.h"
#include <Arduino.h>
#include <Print.h>

#if defined(DISPLAY_UC1609) && !defined(MK61_DISPLAY_UC1609)
  #define MK61_DISPLAY_UC1609
#endif

#if defined(DISPLAY_LCD1602) && !defined(MK61_DISPLAY_LCD1602)
  #define MK61_DISPLAY_LCD1602
#endif

#if !defined(MK61_DISPLAY_LCD1602) && !defined(MK61_DISPLAY_UC1609)
  #define MK61_DISPLAY_LCD1602
#endif

#if defined(MK61_DISPLAY_LCD1602) && defined(MK61_DISPLAY_UC1609)
  #error "Select only one display backend"
#endif

#if defined(MK61_DISPLAY_LCD1602)
  #include <LiquidCrystal.h>
#else
  #include "ERM19264_UC1609.h"
#endif

namespace lcd_display {

static constexpr u8 COLS = 16;

struct TextProfile {
  u8 rows;
  u8 glyph_width;
  u8 glyph_height;
  u8 line_gap;
};

#if defined(MK61_DISPLAY_LCD1602)
static constexpr u8 ROWS = 2;
static constexpr u8 DEFAULT_ROWS = ROWS;
static constexpr u8 MAX_ROWS = ROWS;
static inline TextProfile defaultTextProfileForRows(u8) {
  return {ROWS, 5, 8, 0};
}
static inline TextProfile normalizeTextProfile(TextProfile) {
  return defaultTextProfileForRows(ROWS);
}
#else
// ROWS is the legacy/default text grid. Graphical displays can switch to
// COMPACT_ROWS at runtime while keeping the same 16-column UI.
static constexpr u8 ROWS = 4;
static constexpr u8 DEFAULT_ROWS = 4;
static constexpr u8 SPACED_ROWS_5 = 5;
static constexpr u8 SPACED_ROWS_7 = 7;
static constexpr u8 COMPACT_ROWS = 8;
static constexpr u8 MAX_ROWS = COMPACT_ROWS;
static constexpr u8 PIXEL_WIDTH = 192;
static constexpr u8 PIXEL_HEIGHT = 64;
static constexpr u8 CELL_WIDTH = 12;
static constexpr u8 CELL_HEIGHT = 16;

static inline u8 clamp_u8(u8 value, u8 min_value, u8 max_value) {
  if(value < min_value) return min_value;
  if(value > max_value) return max_value;
  return value;
}

static inline u8 maxLineGap(u8 rows, u8 glyph_height) {
  if(rows <= 1) return 0;
  if((u16) rows * glyph_height >= PIXEL_HEIGHT) return 0;
  return (u8) ((PIXEL_HEIGHT - (u16) rows * glyph_height) / (rows - 1));
}

static inline TextProfile defaultTextProfileForRows(u8 rows) {
  rows = clamp_u8(rows, DEFAULT_ROWS, COMPACT_ROWS);
  switch(rows) {
    case DEFAULT_ROWS:
      return {DEFAULT_ROWS, 10, 16, 0};
    case SPACED_ROWS_5:
      return {SPACED_ROWS_5, 10, 10, 2};
    case 6:
      return {6, 10, 8, 2};
    case SPACED_ROWS_7:
      return {SPACED_ROWS_7, 10, 8, 1};
    case COMPACT_ROWS:
    default:
      return {COMPACT_ROWS, 10, 8, 0};
  }
}

static inline TextProfile normalizeTextProfile(TextProfile profile) {
  profile.rows = clamp_u8(profile.rows, DEFAULT_ROWS, COMPACT_ROWS);
  profile.glyph_width = clamp_u8(profile.glyph_width, 5, 10);

  const u8 max_height = PIXEL_HEIGHT / profile.rows;
  profile.glyph_height = clamp_u8(profile.glyph_height, 8, max_height);
  profile.line_gap = clamp_u8(profile.line_gap, 0, maxLineGap(profile.rows, profile.glyph_height));
  return profile;
}
#endif

} // namespace lcd_display

class MK61Display : public Print {
  public:
    MK61Display(void);

    void begin(u8 cols = lcd_display::COLS, u8 rows = lcd_display::ROWS);
    void clear(void);
    void flush(void);
    void beginUpdate(void);
    void endUpdate(void);
    void setRows(u8 rows);
    void setTextProfile(lcd_display::TextProfile profile);
    lcd_display::TextProfile textProfile(void) const;
    void setCursor(u8 x, u8 y);
    void cursorOn(void);
    void cursorOff(void);
    void blinkOn(void);
    void blinkOff(void);
    bool supportsCursor(void) const;
    bool hasHardwareCursor(void) const;
    void createChar(u8 nChar, uint8_t* glyph);
    void writeGlyph(const uint8_t* glyph);
    void clearCustomChars(void);
    u8 cols(void) const { return lcd_display::COLS; }
#if defined(MK61_DISPLAY_LCD1602)
    u8 rows(void) const { return lcd_display::ROWS; }
#else
    u8 rows(void) const { return active_rows; }
#endif

    using Print::print;
    using Print::println;
    using Print::write;

#if ARDUINO >= 100
    virtual size_t write(uint8_t value) override;
#else
    virtual void write(uint8_t value) override;
#endif

  private:
#if defined(MK61_DISPLAY_LCD1602)
    LiquidCrystal lcd;
#else
    static constexpr u8 CUSTOM_GLYPHS = 8;
    static constexpr u8 MAX_RENDER_PAGES = lcd_display::PIXEL_HEIGHT / 8;
    uint8_t render_buffer[lcd_display::PIXEL_WIDTH * MAX_RENDER_PAGES];
    ERM19264_UC1609 lcd;
    ERM19264_UC1609_Screen render_screen;
    uint8_t cells[lcd_display::MAX_ROWS][lcd_display::COLS];
    uint8_t cell_glyphs[lcd_display::MAX_ROWS][lcd_display::COLS][8];
    bool cell_glyph_valid[lcd_display::MAX_ROWS][lcd_display::COLS];
    uint16_t dirty_cols[lcd_display::MAX_ROWS];
    uint8_t custom_glyphs[CUSTOM_GLYPHS][8];
    bool custom_valid[CUSTOM_GLYPHS];
    bool initialized;
    bool screen_dirty;
    bool dirty;
    usize update_depth;
    lcd_display::TextProfile active_profile;
    u8 active_rows;
    u8 cursor_x;
    u8 cursor_y;
    bool cursor_underline;
    bool cursor_blink;
    bool cursor_blink_phase;
    t_time_ms cursor_next_blink_ms;

    void clearShadow(void);
    void clearPhysicalScreen(void);
    static u8 sanitizeRows(u8 rows);
    u8 rowTop(u8 row) const;
    u8 rowPitch(u8 row) const;
    u8 glyphHeight(u8 row) const;
    u8 glyphTop(u8 row) const;
    u8 glyphWidth(void) const;
    u8 glyphLeft(void) const;
    void drawGlyph(u8 x, u8 row_y, u8 row, const uint8_t* glyph);
    void drawDefaultChar(u8 x, u8 row_y, u8 row, u8 value);
    void drawCursor(u8 x, u8 row_y, u8 row, bool block);
    void advanceCursor(void);
    void moveCursorTo(u8 x, u8 y);
    bool cursorOverlayVisible(void) const;
    void markCellDirtyDeferred(u8 x, u8 y);
    void markCursorCellDirty(void);
    void markCellDirty(u8 x, u8 y);
    void markScreenDirty(void);
    void updateCursorBlink(void);
    void renderRun(u8 row, u8 first_col, u8 count);
#endif
};

class MK61DisplayUpdate {
  public:
    explicit MK61DisplayUpdate(MK61Display& display) : display(display) {
      display.beginUpdate();
    }

    ~MK61DisplayUpdate(void) {
      display.endUpdate();
    }

    MK61DisplayUpdate(const MK61DisplayUpdate&) = delete;
    MK61DisplayUpdate& operator=(const MK61DisplayUpdate&) = delete;

  private:
    MK61Display& display;
};

extern MK61Display lcd;

#endif
