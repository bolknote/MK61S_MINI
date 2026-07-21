#ifndef MK61_USB_SCREEN_SURFACE_HPP
#define MK61_USB_SCREEN_SURFACE_HPP

#include "builtin_font.hpp"
#include "fmk_font.hpp"
#include "rust_types.h"
#include "text_screen.hpp"

namespace usb_screen {

static constexpr u16 WIDTH = 192;
static constexpr u8 HEIGHT = 64;
static constexpr u8 PAGE_HEIGHT = 8;
static constexpr u8 PAGE_COUNT = HEIGHT / PAGE_HEIGHT;
static constexpr usize FRAME_BYTES = (usize) WIDTH * HEIGHT / 8U;
static constexpr u8 COLS = 16;
static constexpr u8 CELL_WIDTH = WIDTH / COLS;

struct TextProfile {
  u8 rows;
  u8 glyph_width;
  u8 glyph_height;
  u8 line_gap;
};

constexpr TextProfile profile5x8(void) { return {6, 5, 8, 2}; }
constexpr TextProfile profile5x9(void) { return {7, 5, 9, 0}; }
constexpr TextProfile profile3x5(void) { return {10, 3, 5, 1}; }

TextProfile normalizeProfile(TextProfile profile);

// Software implementation of the graphical display used by USB Screen.  The
// framebuffer is page-major, one byte per x coordinate and eight vertical
// pixels per page.  A set bit means foreground; this is also the wire format.
class Surface {
  public:
    static constexpr u8 CUSTOM_GLYPHS = 8;
    static constexpr u8 OVERLAY_MAX_WIDTH = 32;
    static constexpr u8 OVERLAY_MAX_HEIGHT = 16;

    Surface(void);

    void begin(TextProfile profile = profile5x8());
    void end(void);
    bool active(void) const { return active_; }

    void clear(void);
    void beginUpdate(void);
    void endUpdate(void);
    void flush(t_time_ms now);

    void setTextProfile(TextProfile profile);
    TextProfile textProfile(void) const { return profile_; }
    u8 rows(void) const { return grid_.rows(); }
    void setCursor(u8 x, u8 y);
    void cursorOn(void);
    void cursorOff(void);
    void blinkOn(t_time_ms now);
    void blinkOff(void);
    void writeByte(u8 value);
    void writeCodepoint(u16 codepoint);

    void createChar(u8 slot, const u8 glyph[8]);
    void clearCustomChar(u8 slot);
    void clearCustomChars(void);
    bool copyCustomChar(u8 slot, u8 glyph[8]) const;
    bool readCell(u8 x, u8 y, u16& value, bool& custom) const;

    void setFont(const fmk::Face* font);

    bool beginFullscreenBitmap(void);
    bool showFullscreenBitmap(const u8* bitmap, usize size);
    void endFullscreenBitmap(void);

    bool showTopRightOverlay(const u32* rows, u8 width, u8 height,
                             u8 clear_border);
    void hideTopRightOverlay(void);

    const u8* framebuffer(void) const { return framebuffer_; }
    u32 revision(void) const { return revision_; }

  private:
    static constexpr t_time_ms CURSOR_BLINK_MS = 500;

    u8 framebuffer_[FRAME_BYTES];
    text_screen::Grid grid_;
    u8 custom_glyphs_[CUSTOM_GLYPHS][8];
    bool custom_valid_[CUSTOM_GLYPHS];
    const fmk::Face* font_;
    TextProfile profile_;
    bool active_;
    bool dirty_;
    bool fullscreen_bitmap_active_;
    usize update_depth_;
    bool cursor_underline_;
    bool cursor_blink_;
    bool cursor_blink_phase_;
    t_time_ms cursor_next_blink_ms_;
    u32 revision_;
    u32 overlay_rows_[OVERLAY_MAX_HEIGHT];
    u8 overlay_width_;
    u8 overlay_height_;
    u8 overlay_clear_border_;
    bool overlay_visible_;

    void markDirty(void);
    bool cursorVisible(void) const;
    void updateCursorBlink(t_time_ms now);
    void render(void);
    void clearPixels(void);
    void setPixel(i16 x, i16 y, bool foreground);
    void fillRect(i16 x, i16 y, i16 width, i16 height, bool foreground);
    u8 rowTop(u8 row) const;
    u8 rowPitch(u8 row) const;
    u8 glyphHeight(u8 row) const;
    bool resolveToken(u16 value, bool custom,
                      builtin_font::Raster& raster) const;
    void drawGlyph(u8 cell_x, u8 row, const builtin_font::Raster& raster);
    void drawCursor(u8 cell_x, u8 row, bool block);
    void drawOverlay(void);
};

} // namespace usb_screen

#endif
