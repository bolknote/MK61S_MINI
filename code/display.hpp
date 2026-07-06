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

#if defined(MK61_DISPLAY_LCD1602)
static constexpr u8 ROWS = 2;
#else
static constexpr u8 ROWS = 4;
static constexpr u8 PIXEL_WIDTH = 192;
static constexpr u8 PIXEL_HEIGHT = 64;
static constexpr u8 CELL_WIDTH = 12;
static constexpr u8 CELL_HEIGHT = 16;
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
    void setCursor(u8 x, u8 y);
    void createChar(u8 nChar, uint8_t* glyph);
    void writeGlyph(const uint8_t* glyph);
    void clearCustomChars(void);
    u8 cols(void) const { return lcd_display::COLS; }
    u8 rows(void) const { return lcd_display::ROWS; }

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
    uint8_t render_buffer[lcd_display::PIXEL_WIDTH * lcd_display::CELL_HEIGHT / 8];
    ERM19264_UC1609 lcd;
    ERM19264_UC1609_Screen render_screen;
    uint8_t cells[lcd_display::ROWS][lcd_display::COLS];
    uint8_t cell_glyphs[lcd_display::ROWS][lcd_display::COLS][8];
    bool cell_glyph_valid[lcd_display::ROWS][lcd_display::COLS];
    uint16_t dirty_cols[lcd_display::ROWS];
    uint8_t custom_glyphs[CUSTOM_GLYPHS][8];
    bool custom_valid[CUSTOM_GLYPHS];
    bool screen_dirty;
    bool dirty;
    usize update_depth;
    u8 cursor_x;
    u8 cursor_y;

    void clearShadow(void);
    void clearPhysicalScreen(void);
    void drawGlyph(u8 x, const uint8_t* glyph);
    void advanceCursor(void);
    void markCellDirty(u8 x, u8 y);
    void markScreenDirty(void);
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
