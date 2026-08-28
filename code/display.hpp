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

#if defined(MK61_DISPLAY_UC1609) || MK61_ENABLE_USB_SCREEN
  #define MK61_HAS_GRAPHICAL_TEXT_SETTINGS 1
#else
  #define MK61_HAS_GRAPHICAL_TEXT_SETTINGS 0
#endif

#if defined(MK61_DISPLAY_LCD1602)
  #include "character_display_geometry.hpp"
#if defined(MK61_OLED1602_WS0010)
  #include "ws0010_controller.hpp"
  #include "oled_protection.hpp"
#endif
  #include <LiquidCrystal.h>
#else
  #include "ERM19264_UC1609.h"
  #include "builtin_font.hpp"
  #include "fmk_font.hpp"
  #include "text_screen.hpp"
#endif

#if MK61_ENABLE_USB_SCREEN
  #include "usb_screen_surface.hpp"
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

#if MK61_HAS_GRAPHICAL_TEXT_SETTINGS
// Виртуальный USB-дисплей и UC1609 используют общую текстовую геометрию 192x64.
// Эти профили не зависят от геометрии физического LCD1602, чтобы LCD-сборка
// сохраняла выбранный шрифт USB-экрана между сеансами.
static constexpr u8 FONT_10X16_ROWS = 4;
static constexpr u8 FONT_5X8_ROWS = 6;
static constexpr u8 FONT_5X9_ROWS = 7;
static constexpr u8 FONT_3X5_ROWS = 10;
static constexpr u8 MIN_ROWS = 4;
static constexpr u8 COMPACT_ROWS = 8;
static constexpr u8 GRAPHICS_MAX_ROWS = FONT_3X5_ROWS;
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

static constexpr TextProfile textProfile10x16(void) {
  return {FONT_10X16_ROWS, 10, 16, 0};
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

static constexpr TextProfile defaultGraphicalTextProfileForRows(u8 rows) {
  if(rows <= FONT_10X16_ROWS) return textProfile10x16();
  if(rows <= FONT_5X8_ROWS) return textProfile5x8();
  if(rows == FONT_5X9_ROWS) return textProfile5x9();
  return textProfile3x5();
}

static inline TextProfile presetGraphicalTextProfile(TextProfile profile) {
  if(profile.rows <= FONT_10X16_ROWS || profile.glyph_width >= 10 ||
     profile.glyph_height >= 16) return textProfile10x16();
  if(profile.glyph_width <= 3 || profile.rows >= FONT_3X5_ROWS) return textProfile3x5();
  if(profile.glyph_height >= 9 || profile.rows == FONT_5X9_ROWS) return textProfile5x9();
  return textProfile5x8();
}

static inline TextProfile normalizeGraphicalTextProfile(TextProfile profile) {
#if MK61_ENABLE_EXTENDED_FONT_SETTINGS
  profile.rows = clamp_u8(profile.rows, MIN_ROWS, GRAPHICS_MAX_ROWS);
  profile.glyph_width = clamp_u8(profile.glyph_width, 3, 10);

  const u8 max_height = PIXEL_HEIGHT / profile.rows;
  profile.glyph_height = clamp_u8(profile.glyph_height, 5, max_height);
  profile.line_gap = clamp_u8(profile.line_gap, 0, maxLineGap(profile.rows, profile.glyph_height));
  return profile;
#else
  return presetGraphicalTextProfile(profile);
#endif
}
#endif

#if defined(MK61_DISPLAY_LCD1602)
static constexpr u8 ROWS = character_display_geometry::ROWS;
static constexpr u8 DDRAM_COLS = character_display_geometry::DDRAM_COLS;
// A00/A02 retain a full 2x40 diff shadow. WS0010 streams the owner's 2x64
// layout into controller DDRAM and keeps only the visible and Home windows.
#if defined(MK61_OLED1602_WS0010)
static constexpr u8 DDRAM_SHADOW_COLS = COLS;
#else
static constexpr u8 DDRAM_SHADOW_COLS = DDRAM_COLS;
#endif
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
static constexpr u8 ROWS = FONT_5X8_ROWS;
static constexpr u8 DEFAULT_ROWS = FONT_5X8_ROWS;
static constexpr u8 MAX_ROWS = GRAPHICS_MAX_ROWS;

static constexpr TextProfile defaultTextProfileForRows(u8 rows) {
  return defaultGraphicalTextProfileForRows(rows);
}

static inline TextProfile presetTextProfile(TextProfile profile) {
  return presetGraphicalTextProfile(profile);
}

static inline TextProfile normalizeTextProfile(TextProfile profile) {
  return normalizeGraphicalTextProfile(profile);
}
#endif

#if MK61_HAS_GRAPHICAL_TEXT_SETTINGS
static constexpr TextProfile defaultSettingsTextProfile(void) {
  return textProfile5x8();
}

static constexpr TextProfile defaultSettingsTextProfileForRows(u8 rows) {
  return defaultGraphicalTextProfileForRows(rows);
}

static inline TextProfile normalizeSettingsTextProfile(TextProfile profile) {
  return normalizeGraphicalTextProfile(profile);
}
#else
static constexpr TextProfile defaultSettingsTextProfile(void) {
  return defaultTextProfileForRows(DEFAULT_ROWS);
}

static constexpr TextProfile defaultSettingsTextProfileForRows(u8 rows) {
  return defaultTextProfileForRows(rows);
}

static inline TextProfile normalizeSettingsTextProfile(TextProfile profile) {
  return normalizeTextProfile(profile);
}
#endif

#if MK61_ENABLE_USB_SCREEN
static constexpr u8 RUNTIME_MAX_ROWS = GRAPHICS_MAX_ROWS;
#else
static constexpr u8 RUNTIME_MAX_ROWS = MAX_ROWS;
#endif

} // пространство имён lcd_display

class MK61Display : public Print {
  public:
    MK61Display(void);

    void begin(u8 cols = lcd_display::COLS, u8 rows = lcd_display::ROWS);
    // Reinitialises an already powered character controller without losing
    // the visible window, custom glyphs or cursor/display-control state.
    // Currently supported by the explicit WS0010 backend.
    bool reinitialize(void);
#if defined(MK61_OLED1602_WS0010)
    bool supportsWs0010Graphics(void) const {
      return MK61_WS0010_GRAPHICS_100X16 != 0;
    }
    bool beginWs0010Graphics(void);
    bool writeWs0010GraphicsPage(u8 page, u8 first,
                                 const u8* data, usize count);
    bool presentWs0010Graphics(void);
    bool showWs0010GraphicsFrame(const u8* frame, usize size);
    void endWs0010Graphics(void);
    bool returnWs0010Home(void);
    bool shiftWs0010Cursor(bool right);
    bool showWs0010EntryModeTest(bool automatic_shift);
    bool showWs0010ZeroRunTest(void);
    void configureOledProtection(oled_protection::Timeout timeout, u32 now);
    void noteDisplayActivity(u32 now);
    void pollOledProtection(u32 now);
    void setDisplayEnabled(bool enabled, u32 now);
    bool displayEnabled(void) const { return oled_protection_state.awake(); }
    oled_protection::Timeout oledProtectionTimeout(void) const {
      return oled_protection_state.timeout();
    }
#endif
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
    void clearCustomChar(u8 nChar);
#if defined(MK61_DISPLAY_LCD1602)
    bool readCell(u8 x, u8 y, u8& value) const;
    bool copyCustomChar(u8 nChar, u8 glyph[8]) const;
    void renderShiftedViewport(
      const u8 cells[lcd_display::ROWS][lcd_display::DDRAM_COLS], u8 shift);
    // Moves an already loaded native DDRAM layout without retransmitting it.
    // `cells` remains owner-owned and is consulted only to refresh the compact
    // visible-window shadow used by USB/recovery.
    bool shiftShiftedViewport(
      const u8 cells[lcd_display::ROWS][lcd_display::DDRAM_COLS], u8 shift);
#if defined(MK61_OLED1602_WS0010)
    // Rewrites one controller DDRAM row while preserving the other row and
    // the shared hardware shift. This is the independent-scroll path for a
    // 2-line module whose display-shift command necessarily moves both rows.
    bool updateWs0010ShiftedViewportRow(
      const u8 cells[lcd_display::ROWS][lcd_display::DDRAM_COLS],
      u8 row, u8 shift);
#endif
    void endShiftedViewport(void);
#if defined(MK61_OLED1602_WS0010)
    u16 reinitializationCount(void) const { return reinitialization_count; }
    ws0010::InitializationPhase initializationPhase(void) const {
      return initialization_phase;
    }
#endif
#endif
    bool showTopRightOverlay(const u32* rows, u8 width, u8 height,
                             u8 clear_border);
    void hideTopRightOverlay(void);
    void writeCodepoint(u16 codepoint);
    bool installFont(const u8* data, u16 size);
    bool setFontPreview(const u8* data, u16 size);
    void clearFontPreview(void);
    void useBuiltinFont(void);
    bool externalFontActive(void) const;
    bool suspendExternalFontForUsb(void);
    // Modal-пара подавляет фоновые flush во время просмотра WBMP.
    // Сам showFullscreenBitmap остаётся пригоден для одноразового DFU-сплеша.
    bool supportsFullscreenBitmap(void) const {
#if MK61_ENABLE_USB_SCREEN
      if(usb_screen_active) return true;
#endif
#if defined(MK61_DISPLAY_UC1609)
      return true;
#elif defined(MK61_OLED1602_WS0010)
      return MK61_WS0010_GRAPHICS_100X16 != 0;
#else
      return false;
#endif
    }
    u16 fullscreenBitmapWidth(void) const {
#if MK61_ENABLE_USB_SCREEN
      if(usb_screen_active) return usb_screen::WIDTH;
#endif
#if defined(MK61_DISPLAY_UC1609)
      return lcd_display::PIXEL_WIDTH;
#elif defined(MK61_OLED1602_WS0010)
      return MK61_WS0010_GRAPHICS_100X16
          ? ws0010::GRAPHICS_VISIBLE_WIDTH : 0;
#else
      return 0;
#endif
    }
    u16 fullscreenBitmapHeight(void) const {
#if MK61_ENABLE_USB_SCREEN
      if(usb_screen_active) return usb_screen::HEIGHT;
#endif
#if defined(MK61_DISPLAY_UC1609)
      return lcd_display::PIXEL_HEIGHT;
#elif defined(MK61_OLED1602_WS0010)
      return MK61_WS0010_GRAPHICS_100X16 ? ws0010::GRAPHICS_HEIGHT : 0;
#else
      return 0;
#endif
    }
    bool beginFullscreenBitmap(void);
    bool showFullscreenBitmap(const u8* bitmap, usize size);
    void endFullscreenBitmap(void);
    bool beginCellAnimation(void);
    bool writeCellAnimationPaletteFrame(const u8 glyphs[8][8],
                                        const u8* cells, usize count);
    void endCellAnimation(void);
    lcd_display::BusyFlagStatus busyFlagStatus(void) const;
    bool busyFlagObserved(void) const;
    bool busyFlagFaulted(void) const;
    u32 busyFlagTimeouts(void) const;
    u8 cols(void) const { return lcd_display::COLS; }
    u8 cursorX(void) const {
#if MK61_ENABLE_USB_SCREEN
      if(usb_screen_active) return usb_surface.cursorX();
#endif
#if defined(MK61_DISPLAY_LCD1602)
      return shadow_cursor_x;
#else
      return grid.cursorX();
#endif
    }
    u8 cursorY(void) const {
#if MK61_ENABLE_USB_SCREEN
      if(usb_screen_active) return usb_surface.cursorY();
#endif
#if defined(MK61_DISPLAY_LCD1602)
      return shadow_cursor_y;
#else
      return grid.cursorY();
#endif
    }
    u8 rows(void) const {
#if MK61_ENABLE_USB_SCREEN
      if(usb_screen_active) return usb_surface.rows();
#endif
#if defined(MK61_DISPLAY_LCD1602)
      return lcd_display::ROWS;
#else
      return grid.rows();
#endif
    }
    bool graphicsMode(void) const {
#if defined(MK61_DISPLAY_UC1609)
      return true;
#elif defined(MK61_OLED1602_WS0010)
#if MK61_ENABLE_USB_SCREEN
      // USB Screen is a graphics backend even when the physical WS0010 is
      // currently in character mode. Modal graphics owners must therefore
      // see the active virtual display, not the dormant physical mode.
      if(usb_screen_active) return true;
#endif
      return ws0010_graphics_active;
#elif MK61_ENABLE_USB_SCREEN
      return usb_screen_active;
#else
      return false;
#endif
    }

#if MK61_ENABLE_USB_SCREEN
    bool enterUsbScreen(void);
    void leaveUsbScreen(void);
    bool usbScreenActive(void) const { return usb_screen_active; }
    u32 displayModeRevision(void) const { return display_mode_revision; }
    const u8* usbScreenFramebuffer(void) const {
      return usb_surface.framebuffer();
    }
    u32 usbScreenRevision(void) const { return usb_surface.revision(); }
#else
    bool enterUsbScreen(void) { return false; }
    void leaveUsbScreen(void) {}
    bool usbScreenActive(void) const { return false; }
    u32 displayModeRevision(void) const { return 0; }
    const u8* usbScreenFramebuffer(void) const { return NULL; }
    u32 usbScreenRevision(void) const { return 0; }
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
#if !defined(MK61_OLED1602_WS0010)
    LiquidCrystal lcd;
#endif
    u8 ddram_shadow[lcd_display::ROWS][lcd_display::DDRAM_SHADOW_COLS];
#if defined(MK61_OLED1602_WS0010)
    u8 ddram_home_shadow[lcd_display::ROWS][lcd_display::COLS];
#endif
    u8 shadow_cursor_x;
    u8 shadow_cursor_y;
    u8 custom_glyphs[8][8];
    bool custom_valid[8];
    u8 display_control;
    // Bit-packed so richer BF diagnostics do not enlarge MK61Display.
    u8 busy_flag_state;
    u32 busy_flag_timeouts;
    bool shifted_viewport_active;
    u8 shifted_viewport_shift;
#if defined(MK61_OLED1602_WS0010)
    u16 reinitialization_count;
    ws0010::InitializationPhase initialization_phase;
    bool ws0010_graphics_active;
    oled_protection::State oled_protection_state;

    bool initializeWs0010Controller(bool cold_start,
                                    bool display_on_after_init);
    void refreshWs0010VisibleShadow(
      const u8 cells[lcd_display::ROWS][lcd_display::DDRAM_COLS], u8 shift);
    void restoreWs0010DdramAddress(void);
#endif

    void probeBusyFlag(void);
    void sendByte(u8 value, bool data, u32 fallback_delay_us = 0);
    void sendCommand(u8 value, u32 fallback_delay_us = 0);
    void sendData(u8 value);
    void sendDisplayControl(void);
    void writeCharacterCell(u8 value);
#else
    static constexpr u8 CUSTOM_GLYPHS = 8;
    static constexpr u8 RENDER_PAGE_HEIGHT = 8;
    static constexpr u8 RENDER_PAGE_COUNT =
      lcd_display::PIXEL_HEIGHT / RENDER_PAGE_HEIGHT;
    static_assert(lcd_display::PIXEL_HEIGHT % RENDER_PAGE_HEIGHT == 0,
                  "display height must contain whole UC1609 pages");
    static constexpr u8 TOP_RIGHT_OVERLAY_MAX_WIDTH = 32;
    static constexpr u8 TOP_RIGHT_OVERLAY_MAX_HEIGHT = 16;
#if MK61_ENABLE_USB_SCREEN
    // В обычном режиме UC1609 отрисовщику нужна только первая страница на 192 байта.
    // USB-экран повторно использует этот блок как полный кадровый буфер 192x64.
    uint8_t render_buffer[usb_screen::FRAME_BYTES];
#else
    uint8_t render_buffer[lcd_display::PIXEL_WIDTH];
#endif
    ERM19264_UC1609 lcd;
    u8 render_width;
    text_screen::Grid grid;
    uint8_t custom_glyphs[CUSTOM_GLYPHS][8];
    bool custom_valid[CUSTOM_GLYPHS];
    fmk::Face active_font;
    fmk::Face preview_font;
    enum class ActiveFontState : u8 {
      BUILTIN,
      READY,
      SUSPENDED
    };
    ActiveFontState active_font_state;
    bool initialized;
#if MK61_ANY_FULLSCREEN_FILE
    bool fullscreen_bitmap_active;
#endif
    bool screen_dirty;
    bool dirty;
    // Вне текстовой сетки damage создаёт верхняя правая пиксельная накладка.
    u16 extra_dirty_page_cols[RENDER_PAGE_COUNT];
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
    void setRenderPixel(i16 x, i16 y);
    void fillRenderRect(i16 x, i16 y, i16 width, i16 height,
                        bool foreground);
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
    void markTopRightOverlayDirty(u8 width, u8 height, u8 clear_border);
    void drawTopRightOverlay(u8 first_col, u8 count, u8 page_y);
    void updateCursorBlink(void);
    void renderPageRun(u8 page, u8 first_col, u8 count);
    void applyTextProfile(lcd_display::TextProfile profile, bool exact_geometry = false);
    lcd_display::TextProfile recommendedProfile(const fmk::Metrics& metrics) const;
    const fmk::Face* selectedFont(void) const;
    builtin_font::FaceId fallbackFont(void) const;
    bool resolveToken(u16 value, bool custom, builtin_font::Raster& raster) const;
#endif
#if MK61_ENABLE_USB_SCREEN
#if defined(MK61_DISPLAY_LCD1602)
    // Графическую ОЗУ LCD1602 нельзя прочитать, поэтому нужен отдельный буфер.
    u8 usb_framebuffer[usb_screen::FRAME_BYTES];
    lcd_display::TextProfile usb_text_profile;
#endif
    usb_screen::Surface usb_surface;
    bool usb_screen_active;
    u32 display_mode_revision;
    bool physical_screen_enabled;
#if defined(MK61_DISPLAY_LCD1602)
    fmk::Face usb_preview_font;
    usb_screen::TextProfile usb_preview_saved_profile;
    bool usb_preview_font_active;
#endif

    void setPhysicalScreenEnabled(bool enabled);
    static usb_screen::TextProfile usbTextProfile(
      lcd_display::TextProfile profile);
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
