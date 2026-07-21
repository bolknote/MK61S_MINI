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
  #include "builtin_font.hpp"
  #include "fmk_font.hpp"
  #include "text_screen.hpp"
#endif

namespace lcd_display {

static constexpr u8 COLS = 16;

enum class BusyFlagStatus : u8 {
  NOT_AVAILABLE,
  ACTIVE,
  FIXED_DELAYS,
};

struct TextProfile {
  u8 rows;
  u8 glyph_width;
  u8 glyph_height;
  u8 line_gap;
};

#if defined(MK61_DISPLAY_LCD1602)
static constexpr u8 ROWS = 2;
static constexpr u8 DDRAM_COLS = 40;
static constexpr u8 DEFAULT_ROWS = ROWS;
static constexpr u8 MAX_ROWS = ROWS;
static constexpr TextProfile defaultTextProfileForRows(u8) {
  return {ROWS, 5, 8, 0};
}
static inline TextProfile normalizeTextProfile(TextProfile) {
  return defaultTextProfileForRows(ROWS);
}
#else
// ROWS задаёт текстовую сетку по умолчанию. Графические дисплеи сохраняют
// 16-столбцовый интерфейс и во время работы переключаются между несколькими
// фиксированными наборами шрифтов.
static constexpr u8 FONT_5X8_ROWS = 6;
static constexpr u8 FONT_5X9_ROWS = 7;
static constexpr u8 FONT_3X5_ROWS = 10;
static constexpr u8 MIN_ROWS = 4; // нижняя граница для расширенных пользовательских профилей
static constexpr u8 ROWS = FONT_5X8_ROWS;
static constexpr u8 DEFAULT_ROWS = FONT_5X8_ROWS;
static constexpr u8 COMPACT_ROWS = 8; // прежний сохраняемый режим «8 строк»
static constexpr u8 MAX_ROWS = FONT_3X5_ROWS;
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

static constexpr TextProfile textProfile5x8(void) {
  return {FONT_5X8_ROWS, 5, 8, 2};
}

static constexpr TextProfile textProfile5x9(void) {
  return {FONT_5X9_ROWS, 5, 9, 0};
}

static constexpr TextProfile textProfile3x5(void) {
  return {FONT_3X5_ROWS, 3, 5, 1};
}

static inline bool isTextProfile3x5(TextProfile profile) {
  return profile.glyph_width == 3 && profile.glyph_height == 5;
}

static constexpr TextProfile defaultTextProfileForRows(u8 rows) {
  if(rows <= FONT_5X8_ROWS) return textProfile5x8();
  if(rows == FONT_5X9_ROWS) return textProfile5x9();
  return textProfile3x5();
}

static inline TextProfile presetTextProfile(TextProfile profile) {
  if(profile.glyph_width <= 3 || profile.rows >= FONT_3X5_ROWS) return textProfile3x5();
  if(profile.glyph_height >= 9 || profile.rows == FONT_5X9_ROWS) return textProfile5x9();
  return textProfile5x8();
}

static inline TextProfile normalizeTextProfile(TextProfile profile) {
#if MK61_ENABLE_EXTENDED_FONT_SETTINGS
  profile.rows = clamp_u8(profile.rows, MIN_ROWS, MAX_ROWS);
  profile.glyph_width = clamp_u8(profile.glyph_width, 3, 10);

  const u8 max_height = PIXEL_HEIGHT / profile.rows;
  profile.glyph_height = clamp_u8(profile.glyph_height, 5, max_height);
  profile.line_gap = clamp_u8(profile.line_gap, 0, maxLineGap(profile.rows, profile.glyph_height));
  return profile;
#else
  return presetTextProfile(profile);
#endif
}
#endif

} // пространство имён lcd_display

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
    void clearCustomChars(void);
#if defined(MK61_DISPLAY_LCD1602)
    bool readCell(u8 x, u8 y, u8& value) const;
    bool copyCustomChar(u8 nChar, u8 glyph[8]) const;
    void clearCustomChar(u8 nChar);
    void renderShiftedViewport(
      const u8 cells[lcd_display::ROWS][lcd_display::DDRAM_COLS], u8 shift);
    void endShiftedViewport(void);
#else
    bool showTopRightOverlay(const u32* rows, u8 width, u8 height,
                             u8 clear_border);
    void hideTopRightOverlay(void);
#endif
    void writeCodepoint(u16 codepoint);
    bool installFont(const u8* data, u16 size);
    bool setFontPreview(const u8* data, u16 size);
    void clearFontPreview(void);
    void useBuiltinFont(void);
    bool externalFontActive(void) const;
    bool suspendExternalFontForUsb(void);
    // Modal-пара подавляет фоновые flush во время просмотра WBMP.
    // Сам showFullscreenBitmap остаётся пригоден для одноразового DFU-сплеша.
    bool beginFullscreenBitmap(void);
    bool showFullscreenBitmap(const u8* bitmap, usize size);
    void endFullscreenBitmap(void);
    bool beginCellAnimation(void);
    bool writeCellAnimationPaletteFrame(const u8 glyphs[8][8],
                                        const u8* cells, usize count);
    void endCellAnimation(void);
    lcd_display::BusyFlagStatus busyFlagStatus(void) const;
    u32 busyFlagTimeouts(void) const;
    u8 cols(void) const { return lcd_display::COLS; }
#if defined(MK61_DISPLAY_LCD1602)
    u8 rows(void) const { return lcd_display::ROWS; }
#else
    u8 rows(void) const { return grid.rows(); }
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
    bool writeCellAnimationFrame(const u8* cells, usize count);
#if defined(MK61_DISPLAY_LCD1602)
    LiquidCrystal lcd;
    u8 ddram_shadow[lcd_display::ROWS][lcd_display::DDRAM_COLS];
    u8 shadow_cursor_x;
    u8 shadow_cursor_y;
    u8 custom_glyphs[8][8];
    bool custom_valid[8];
    u8 display_control;
    bool busy_flag_active;
    u32 busy_flag_timeouts;
    bool shifted_viewport_active;
    u8 shifted_viewport_shift;

    void probeBusyFlag(void);
    void sendByte(u8 value, bool data, u32 fallback_delay_us = 0);
    void sendCommand(u8 value, u32 fallback_delay_us = 0);
    void sendData(u8 value);
    void sendDisplayControl(void);
#else
    static constexpr u8 CUSTOM_GLYPHS = 8;
    static constexpr u8 RENDER_PAGE_HEIGHT = 8;
    static constexpr u8 TOP_RIGHT_OVERLAY_MAX_WIDTH = 32;
    static constexpr u8 TOP_RIGHT_OVERLAY_MAX_HEIGHT = 16;
    uint8_t render_buffer[lcd_display::PIXEL_WIDTH];
    ERM19264_UC1609 lcd;
    ERM19264_UC1609_Screen render_screen;
    text_screen::Grid grid;
    uint8_t custom_glyphs[CUSTOM_GLYPHS][8];
    bool custom_valid[CUSTOM_GLYPHS];
    fmk::Face active_font;
    fmk::Face preview_font;
    bool active_font_enabled;
    bool external_font_suspended;
    bool preview_font_enabled;
    bool initialized;
#if MK61_ENABLE_WBMP_VIEWER
    bool fullscreen_bitmap_active;
#endif
    bool screen_dirty;
    bool dirty;
    usize update_depth;
    lcd_display::TextProfile active_profile;
    lcd_display::TextProfile preview_saved_profile;
    bool cursor_underline;
    bool cursor_blink;
    bool cursor_blink_phase;
    t_time_ms cursor_next_blink_ms;
    bool preview_profile_active;
    u32 top_right_overlay_rows[TOP_RIGHT_OVERLAY_MAX_HEIGHT];
    u8 top_right_overlay_width;
    u8 top_right_overlay_height;
    u8 top_right_overlay_clear_border;
    bool top_right_overlay_visible;

    void clearShadow(void);
    void clearPhysicalScreen(void);
    static u8 sanitizeRows(u8 rows);
    u8 rowTop(u8 row) const;
    u8 rowPitch(u8 row) const;
    u8 glyphHeight(u8 row) const;
    u8 glyphTop(u8 row) const;
    u8 glyphWidth(void) const;
    u8 glyphLeft(void) const;
    void drawGlyph(u8 x, i16 row_y, u8 row, const uint8_t* bitmap, u8 source_width, u8 source_height);
    void drawToken(u8 x, i16 row_y, u8 row, u16 value, bool custom);
    void drawCursor(u8 x, i16 row_y, u8 row, bool block);
    void moveCursorTo(u8 x, u8 y);
    bool cursorOverlayVisible(void) const;
    void markCellDirtyDeferred(u8 x, u8 y);
    void markCursorCellDirty(void);
    void markCellDirty(u8 x, u8 y);
    void markScreenDirty(void);
    void markAllDirty(void);
    void markTopRightOverlayDirty(u8 width, u8 clear_border);
    void drawTopRightOverlay(u8 first_col, u8 count, u8 page_y);
    void updateCursorBlink(void);
    void renderRun(u8 row, u8 first_col, u8 count);
    void applyTextProfile(lcd_display::TextProfile profile, bool exact_geometry = false);
    lcd_display::TextProfile recommendedProfile(const fmk::Metrics& metrics) const;
    const fmk::Face* selectedFont(void) const;
    builtin_font::FaceId fallbackFont(void) const;
    bool resolveToken(u16 value, bool custom, builtin_font::Raster& raster) const;
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

extern MK61Display* main_lcd_pointer;
static inline MK61Display& main_lcd(void) { return *main_lcd_pointer; }

#endif
