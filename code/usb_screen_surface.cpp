#include "usb_screen_surface.hpp"

#include "display_symbols.hpp"
#if MK61_PROPORTIONAL_UI_FONTS
#include "ui_text_renderer.hpp"
#endif
#if MK61_FIXED_CALCULATOR_FACE
#include "calculator_face.hpp"
#endif

#include <string.h>

namespace usb_screen {

namespace {

static inline bool timeReached(t_time_ms now, t_time_ms target) {
  return (i32) (now - target) >= 0;
}

static inline u8 clamp(u8 value, u8 low, u8 high) {
  if(value < low) return low;
  return value > high ? high : value;
}

} // безымянное пространство имён

TextProfile normalizeProfile(TextProfile profile) {
  const text_screen::FontGeometry geometry =
    text_screen::sanitizeFontGeometry({
      profile.rows,
      profile.glyph_width,
      profile.glyph_height,
      profile.line_gap,
    });
  return {geometry.rows, geometry.width, geometry.height, geometry.line_gap};
}

Surface::Surface(u8* framebuffer)
  : framebuffer_(framebuffer),
    grid_(),
    custom_glyphs_{{0}},
    custom_valid_{false},
    font_(NULL),
    profile_(profile5x8()),
    active_(false),
    dirty_(false),
    fullscreen_bitmap_active_(false),
#if MK61_FIXED_CALCULATOR_FACE
    calculator_face_active_(false),
#endif
    update_depth_(0),
    cursor_underline_(false),
    cursor_blink_(false),
    cursor_blink_phase_(false),
    cursor_next_blink_ms_(0),
    revision_(0),
    overlay_rows_{0},
    overlay_width_(0),
    overlay_height_(0),
    overlay_clear_border_(0),
    overlay_visible_(false)
#if MK61_PROPORTIONAL_UI_FONTS
    , ui_text_active_(false),
    ui_font_enabled_(false),
    ui_face_{ui_font::Family::PIXEL, ui_font::Size::PX12},
    ui_row_gutters_(0),
    ui_row_tails_(0)
#endif
    {
  grid_.reset(profile_.rows, grid_.cols());
}

void Surface::begin(TextProfile profile) {
  profile_ = normalizeProfile(profile);
  active_ = true;
  update_depth_ = 0;
  fullscreen_bitmap_active_ = false;
#if MK61_FIXED_CALCULATOR_FACE
  calculator_face_active_ = false;
#endif
  cursor_underline_ = false;
  cursor_blink_ = false;
  cursor_blink_phase_ = false;
  cursor_next_blink_ms_ = 0;
  overlay_visible_ = false;
  overlay_width_ = 0;
  overlay_height_ = 0;
  overlay_clear_border_ = 0;
#if MK61_PROPORTIONAL_UI_FONTS
  ui_text_active_ = false;
  ui_font_enabled_ = false;
  ui_row_gutters_ = 0;
  ui_row_tails_ = 0;
#endif
  memset(overlay_rows_, 0, sizeof(overlay_rows_));
  memset(custom_glyphs_, 0, sizeof(custom_glyphs_));
  memset(custom_valid_, 0, sizeof(custom_valid_));
  font_ = NULL;
  grid_.reset(profile_.rows);
  grid_.markAll();
  clearPixels();
  dirty_ = true;
  revision_++;
}

void Surface::end(void) {
  active_ = false;
  dirty_ = false;
  fullscreen_bitmap_active_ = false;
#if MK61_FIXED_CALCULATOR_FACE
  calculator_face_active_ = false;
#endif
  update_depth_ = 0;
  cursor_underline_ = false;
  cursor_blink_ = false;
  cursor_blink_phase_ = false;
  cursor_next_blink_ms_ = 0;
  font_ = NULL;
#if MK61_PROPORTIONAL_UI_FONTS
  ui_text_active_ = false;
  ui_font_enabled_ = false;
  ui_row_gutters_ = 0;
  ui_row_tails_ = 0;
#endif
}

void Surface::markDirty(void) {
  if(active_ && !fullscreen_bitmap_active_) dirty_ = true;
}

void Surface::clear(void) {
  if(!active_) return;
#if MK61_FIXED_CALCULATOR_FACE
  calculator_face_active_ = false;
#endif
  grid_.reset(profile_.rows, grid_.cols());
  grid_.markAll();
  cursor_underline_ = false;
  cursor_blink_ = false;
  cursor_blink_phase_ = false;
  cursor_next_blink_ms_ = 0;
  // The top-right clock is an overlay owned independently from the text
  // surface.  The physical UC1609 clear() deliberately preserves it, so the
  // USB mirror must do the same.  Otherwise the calculator redraw performed
  // immediately after ATTACH erases the mirrored clock while rtc_idle_clock
  // still considers that same minute visible and therefore does not repaint
  // it until the minute changes.
#if MK61_PROPORTIONAL_UI_FONTS
  ui_row_gutters_ = 0;
  ui_row_tails_ = 0;
#endif
  markDirty();
}

void Surface::beginUpdate(void) {
  if(active_) update_depth_++;
}

void Surface::endUpdate(void) {
  if(active_ && update_depth_ > 0) update_depth_--;
}

void Surface::setTextProfile(TextProfile profile) {
  setTextLayout(profile, COLS);
}

void Surface::setTextLayout(TextProfile profile, u8 cols) {
  if(!active_) return;
  const TextProfile next = normalizeProfile(profile);
  if(next.rows == profile_.rows &&
     next.glyph_width == profile_.glyph_width &&
     next.glyph_height == profile_.glyph_height &&
     next.line_gap == profile_.line_gap && cols == grid_.cols()) return;
  profile_ = next;
  grid_.reset(profile_.rows, cols);
#if MK61_PROPORTIONAL_UI_FONTS
  ui_row_gutters_ = 0;
  ui_row_tails_ = 0;
#endif
  cursor_underline_ = false;
  cursor_blink_ = false;
  cursor_blink_phase_ = false;
  cursor_next_blink_ms_ = 0;
  markDirty();
}

void Surface::setCursor(u8 x, u8 y) {
  if(!active_) return;
  const u8 old_x = grid_.cursorX();
  const u8 old_y = grid_.cursorY();
  grid_.setCursor(x, y);
  if(cursorVisible() &&
     (old_x != grid_.cursorX() || old_y != grid_.cursorY())) markDirty();
}

void Surface::cursorOn(void) {
  if(!active_ || cursor_underline_) return;
  cursor_underline_ = true;
  markDirty();
}

void Surface::cursorOff(void) {
  if(!active_ || (!cursor_underline_ && !cursor_blink_ &&
                  !cursor_blink_phase_)) return;
  cursor_underline_ = false;
  cursor_blink_ = false;
  cursor_blink_phase_ = false;
  cursor_next_blink_ms_ = 0;
  markDirty();
}

void Surface::blinkOn(t_time_ms now) {
  if(!active_ || cursor_blink_) return;
  cursor_blink_ = true;
  cursor_blink_phase_ = true;
  cursor_next_blink_ms_ = now + CURSOR_BLINK_MS;
  markDirty();
}

void Surface::blinkOff(void) {
  if(!active_ || (!cursor_blink_ && !cursor_blink_phase_)) return;
  cursor_blink_ = false;
  cursor_blink_phase_ = false;
  cursor_next_blink_ms_ = 0;
  markDirty();
}

void Surface::writeByte(u8 value) {
  if(!active_) return;
  if(value == '\r') return;
  const u8 old_x = grid_.cursorX();
  const u8 old_y = grid_.cursorY();
  bool content_changed = false;
  if(value == '\n') grid_.newline();
  else if(value < CUSTOM_GLYPHS && custom_valid_[value]) {
    content_changed = grid_.writeByte(value);
  } else {
    content_changed = grid_.writeCodepoint(value);
  }
  const bool cursor_changed = old_x != grid_.cursorX() ||
                              old_y != grid_.cursorY();
  if(content_changed || (cursorVisible() && cursor_changed)) markDirty();
}

void Surface::writeCodepoint(u16 codepoint) {
  if(!active_ || codepoint == '\r') return;
  const u8 old_x = grid_.cursorX();
  const u8 old_y = grid_.cursorY();
  bool content_changed = false;
  if(codepoint == '\n') grid_.newline();
  else content_changed = grid_.writeCodepoint(codepoint);
  const bool cursor_changed = old_x != grid_.cursorX() ||
                              old_y != grid_.cursorY();
  if(content_changed || (cursorVisible() && cursor_changed)) markDirty();
}

#if MK61_FIXED_CALCULATOR_FACE
void Surface::beginCalculatorFace(void) {
  if(!active_ || calculator_face_active_) return;
  calculator_face_active_ = true;
  cursor_underline_ = false;
  cursor_blink_ = false;
  cursor_blink_phase_ = false;
  cursor_next_blink_ms_ = 0;
  markDirty();
}
#endif

void Surface::seedText(const text_screen::Grid& source,
                       const u8 custom_glyphs[CUSTOM_GLYPHS][8],
                       const bool custom_valid[CUSTOM_GLYPHS],
                       bool cursor_underline, bool cursor_blink,
                       t_time_ms now) {
  if(!active_ || custom_glyphs == NULL || custom_valid == NULL) return;

  grid_.reset(profile_.rows, source.cols());
  memset(custom_glyphs_, 0, sizeof(custom_glyphs_));
  memset(custom_valid_, 0, sizeof(custom_valid_));
  for(u8 slot = 0; slot < CUSTOM_GLYPHS; slot++) {
    if(!custom_valid[slot]) continue;
    memcpy(custom_glyphs_[slot], custom_glyphs[slot],
           sizeof(custom_glyphs_[slot]));
    custom_valid_[slot] = true;
  }

  const u8 rows = source.rows() < grid_.rows()
                ? source.rows() : grid_.rows();
  const u8 cols = source.cols() < grid_.cols()
                ? source.cols() : grid_.cols();
  for(u8 row = 0; row < rows; row++) {
    grid_.setCursor(0, row);
    for(u8 col = 0; col < cols; col++) {
      const u16 value = source.cell(col, row);
      if(source.cellIsCustom(col, row) && value < CUSTOM_GLYPHS &&
         custom_valid_[value]) {
        grid_.writeByte((u8) value);
      } else {
        grid_.writeCodepoint(value);
      }
    }
  }

  grid_.setCursor(source.cursorX(), source.cursorY());
  cursor_underline_ = cursor_underline;
  cursor_blink_ = cursor_blink;
  cursor_blink_phase_ = cursor_blink;
  cursor_next_blink_ms_ = cursor_blink ? now + CURSOR_BLINK_MS : 0;
  grid_.markAll();
  dirty_ = true;
}

void Surface::createChar(u8 slot, const u8 glyph[8]) {
  if(slot >= CUSTOM_GLYPHS || glyph == NULL) return;
  if(custom_valid_[slot] &&
     memcmp(custom_glyphs_[slot], glyph,
            sizeof(custom_glyphs_[slot])) == 0) return;
  memcpy(custom_glyphs_[slot], glyph, sizeof(custom_glyphs_[slot]));
  custom_valid_[slot] = true;
  if(grid_.markCustomSlot(slot)) markDirty();
}

void Surface::clearCustomChar(u8 slot) {
  if(slot >= CUSTOM_GLYPHS || !custom_valid_[slot]) return;
  const bool visible = grid_.markCustomSlot(slot);
  memset(custom_glyphs_[slot], 0, sizeof(custom_glyphs_[slot]));
  custom_valid_[slot] = false;
  if(visible) markDirty();
}

void Surface::clearCustomChars(void) {
  for(u8 slot = 0; slot < CUSTOM_GLYPHS; slot++) clearCustomChar(slot);
}

bool Surface::copyCustomChar(u8 slot, u8 glyph[8]) const {
  if(slot >= CUSTOM_GLYPHS || glyph == NULL || !custom_valid_[slot]) {
    return false;
  }
  memcpy(glyph, custom_glyphs_[slot], sizeof(custom_glyphs_[slot]));
  return true;
}

bool Surface::readCell(u8 x, u8 y, u16& value, bool& custom) const {
  if(!active_ || x >= grid_.cols() || y >= grid_.rows()) return false;
  value = grid_.cell(x, y);
  custom = grid_.cellIsCustom(x, y);
  return true;
}

void Surface::setFont(const prepared_font::Face* font) {
  if(font_ == font) return;
  font_ = font;
  if(active_) {
    grid_.markAll();
    markDirty();
  }
}

#if MK61_PROPORTIONAL_UI_FONTS
void Surface::setUiTextStyle(bool active, bool font_enabled,
                             ui_font::Face face) {
  if(ui_text_active_ == active && ui_font_enabled_ == font_enabled &&
     ui_face_.family == face.family && ui_face_.size == face.size) return;
  ui_text_active_ = active;
  ui_font_enabled_ = font_enabled;
  ui_face_ = face;
  ui_row_gutters_ = 0;
  ui_row_tails_ = 0;
  grid_.markAll();
  markDirty();
}

void Surface::setUiLineDecorations(u8 row, bool leading_gutter,
                                   bool trailing_gutter) {
  if(row >= grid_.rows()) return;
  const u16 bit = (u16) 1U << row;
  const u16 old_gutters = ui_row_gutters_;
  const u16 old_tails = ui_row_tails_;
  if(leading_gutter) ui_row_gutters_ |= bit;
  else ui_row_gutters_ &= (u16) ~bit;
  if(trailing_gutter) ui_row_tails_ |= bit;
  else ui_row_tails_ &= (u16) ~bit;
  if(old_gutters != ui_row_gutters_ || old_tails != ui_row_tails_) {
    grid_.markCell(0, row);
    markDirty();
  }
}
#endif

bool Surface::beginFullscreenBitmap(void) {
  if(!active_) return false;
#if MK61_FIXED_CALCULATOR_FACE
  calculator_face_active_ = false;
#endif
  fullscreen_bitmap_active_ = true;
  cursor_underline_ = false;
  cursor_blink_ = false;
  cursor_blink_phase_ = false;
  cursor_next_blink_ms_ = 0;
  return true;
}

bool Surface::showFullscreenBitmap(const u8* bitmap, usize size) {
  if(!active_ || !fullscreen_bitmap_active_ || bitmap == NULL ||
     size != FRAME_BYTES) return false;
  if(memcmp(framebuffer_, bitmap, FRAME_BYTES) != 0) {
    memcpy(framebuffer_, bitmap, FRAME_BYTES);
    revision_++;
  }
  return true;
}

void Surface::endFullscreenBitmap(void) {
  if(!active_ || !fullscreen_bitmap_active_) return;
  fullscreen_bitmap_active_ = false;
  grid_.markAll();
  markDirty();
}

bool Surface::showTopRightOverlay(const u32* rows, u8 width, u8 height,
                                  u8 clear_border) {
  const u16 total_width = (u16) width + (u16) clear_border * 2U;
  const u16 total_height = (u16) height + (u16) clear_border * 2U;
  if(!active_ || rows == NULL || width == 0 ||
     width > OVERLAY_MAX_WIDTH || height == 0 ||
     height > OVERLAY_MAX_HEIGHT || total_width > WIDTH ||
     total_height > HEIGHT) return false;

  const u32 mask = width == 32 ? 0xFFFFFFFFUL : (((u32) 1U << width) - 1U);
  bool unchanged = overlay_visible_ &&
                   overlay_width_ == width &&
                   overlay_height_ == height &&
                   overlay_clear_border_ == clear_border;
  if(unchanged) {
    for(u8 y = 0; y < height; y++) {
      if(overlay_rows_[y] != (rows[y] & mask)) {
        unchanged = false;
        break;
      }
    }
  }
  if(unchanged) return true;

  overlay_width_ = width;
  overlay_height_ = height;
  overlay_clear_border_ = clear_border;
  overlay_visible_ = true;
  memset(overlay_rows_, 0, sizeof(overlay_rows_));
  for(u8 y = 0; y < height; y++) overlay_rows_[y] = rows[y] & mask;
  markDirty();
  return true;
}

void Surface::hideTopRightOverlay(void) {
  if(!active_ || !overlay_visible_) return;
  overlay_visible_ = false;
  overlay_width_ = 0;
  overlay_height_ = 0;
  overlay_clear_border_ = 0;
  memset(overlay_rows_, 0, sizeof(overlay_rows_));
  markDirty();
}

bool Surface::copyTopRightOverlay(u32 rows[OVERLAY_MAX_HEIGHT], u8& width,
                                  u8& height, u8& clear_border) const {
  if(rows == NULL) return false;
  memset(rows, 0, sizeof(overlay_rows_));
  width = 0;
  height = 0;
  clear_border = 0;
  if(!active_ || !overlay_visible_) return false;
  memcpy(rows, overlay_rows_, sizeof(overlay_rows_));
  width = overlay_width_;
  height = overlay_height_;
  clear_border = overlay_clear_border_;
  return true;
}

bool Surface::cursorVisible(void) const {
  return cursor_underline_ || (cursor_blink_ && cursor_blink_phase_);
}

void Surface::updateCursorBlink(t_time_ms now) {
  if(!cursor_blink_) return;
  if(cursor_next_blink_ms_ == 0) cursor_next_blink_ms_ = now + CURSOR_BLINK_MS;
  if(!timeReached(now, cursor_next_blink_ms_)) return;
  do {
    cursor_next_blink_ms_ += CURSOR_BLINK_MS;
  } while(timeReached(now, cursor_next_blink_ms_));
  cursor_blink_phase_ = !cursor_blink_phase_;
  markDirty();
}

void Surface::flush(t_time_ms now) {
  if(!active_ || update_depth_ != 0 || fullscreen_bitmap_active_) return;
  updateCursorBlink(now);
  if(!dirty_ && !grid_.anyDirty()) return;
  render();
  for(u8 row = 0; row < grid_.rows(); row++) grid_.clearDirty(row);
  dirty_ = false;
  revision_++;
}

void Surface::clearPixels(void) {
  memset(framebuffer_, 0, FRAME_BYTES);
}

void Surface::setPixel(i16 x, i16 y, bool foreground) {
  if(x < 0 || y < 0 || x >= (i16) WIDTH || y >= HEIGHT) return;
  u8& value = framebuffer_[(usize) (y / PAGE_HEIGHT) * WIDTH + (u16) x];
  const u8 bit = (u8) 1U << (y & 7);
  if(foreground) value |= bit;
  else value &= (u8) ~bit;
}

void Surface::fillRect(i16 x, i16 y, i16 width, i16 height,
                       bool foreground) {
  if(width <= 0 || height <= 0) return;
  const i16 x0 = x < 0 ? 0 : x;
  const i16 y0 = y < 0 ? 0 : y;
  const i16 x1 = x + width > (i16) WIDTH ? (i16) WIDTH : x + width;
  const i16 y1 = y + height > HEIGHT ? HEIGHT : y + height;
  for(i16 py = y0; py < y1; py++) {
    for(i16 px = x0; px < x1; px++) setPixel(px, py, foreground);
  }
}

u8 Surface::rowTop(u8 row) const {
  return (u8) (textTop() +
      (u16) row * (profile_.glyph_height + profile_.line_gap));
}

u8 Surface::textTop(void) const {
  if(grid_.cols() <= COLS) return 0;
  const u8 rows = grid_.rows();
  const u16 occupied = (u16) rows * profile_.glyph_height +
      (rows > 0 ? (u16) (rows - 1U) * profile_.line_gap : 0U);
  return occupied < HEIGHT ? (u8) ((HEIGHT - occupied) / 2U) : 0U;
}

u8 Surface::rowPitch(u8 row) const {
  const u8 top = rowTop(row);
  const u8 pitch = profile_.glyph_height + profile_.line_gap;
  if(row + 1 >= grid_.rows()) return HEIGHT - top;
  return top + pitch > HEIGHT ? HEIGHT - top : pitch;
}

u8 Surface::glyphHeight(u8 row) const {
  const u8 pitch = rowPitch(row);
  return profile_.glyph_height < pitch ? profile_.glyph_height : pitch;
}

bool Surface::resolveToken(u16 value, bool custom,
                           builtin_font::Raster& raster) const {
  memset(raster.data, 0, sizeof(raster.data));
  if(custom) {
    const u8 slot = (u8) value;
    if(slot < CUSTOM_GLYPHS && custom_valid_[slot]) {
      raster.width = 5;
      raster.height = 8;
      for(u8 y = 0; y < 8; y++) {
        for(u8 x = 0; x < 5; x++) {
          if((custom_glyphs_[slot][y] & ((u8) 1U << (4U - x))) != 0) {
            raster.data[y] |= (u8) (0x80U >> x);
          }
        }
      }
      return true;
    }
    value = '?';
  }

  if(font_ != NULL) {
    prepared_font::Glyph glyph;
    const u16 unicode = display_symbol::uc1609::unicodeCodepoint(value);
    if(prepared_font::glyphForCodepoint(*font_, unicode, glyph)) {
      raster.width = glyph.width;
      raster.height = glyph.height;
      if(font_->decode(glyph, raster.data, sizeof(raster.data))) return true;
    }
  }

  const builtin_font::FaceId fallback =
    profile_.glyph_width <= 3 || profile_.glyph_height <= 5
      ? builtin_font::FaceId::FONT_3X5
      : builtin_font::FaceId::FONT_5X8;
  if(builtin_font::decode(fallback, value, raster)) return true;
  return value != '?' && builtin_font::decode(fallback, '?', raster);
}

void Surface::drawGlyph(u8 cell_x, u8 cell_width, u8 row,
                        const builtin_font::Raster& raster) {
  const u8 height = glyphHeight(row);
  const u8 max_width = clamp(profile_.glyph_width, 1, 10);
  const u8 width = raster.width < max_width ? raster.width : max_width;
  if(width == 0 || height == 0 || raster.width == 0 || raster.height == 0) {
    return;
  }

  const u8 left = (u8) (cell_x + (cell_width - width) / 2U);
  const u8 top = rowTop(row);
  for(u8 dest_y = 0; dest_y < height; dest_y++) {
    const u8 source_y = (u8) (((u16) dest_y * raster.height) / height);
    for(u8 dest_x = 0; dest_x < width; dest_x++) {
      const u8 source_x = (u8) (((u16) dest_x * raster.width) / width);
      if(fmk::bitmapPixel(raster.data, raster.width, source_x, source_y)) {
        setPixel(left + dest_x, top + dest_y, true);
      }
    }
  }
}

void Surface::drawCursor(u8 cell_x, u8 cell_width, u8 row, bool block) {
  const u8 width = clamp(profile_.glyph_width, 1, 10);
  const u8 height = glyphHeight(row);
  if(width == 0 || height == 0) return;
  const u8 left = (u8) (cell_x + (cell_width - width) / 2U);
  const u8 top = rowTop(row);
  if(block) fillRect(left, top, width, height, true);
  else fillRect(left, top + height - 1, width, 1, true);
}

void Surface::drawOverlay(void) {
  if(!overlay_visible_) return;
  const i16 total_width = (i16) overlay_width_ +
                          (i16) overlay_clear_border_ * 2;
  const i16 total_height = (i16) overlay_height_ +
                           (i16) overlay_clear_border_ * 2;
  const i16 left = (i16) WIDTH - total_width;
  fillRect(left, 0, total_width, total_height, false);
  const i16 content_left = left + overlay_clear_border_;
  const i16 content_top = overlay_clear_border_;
  for(u8 y = 0; y < overlay_height_; y++) {
    for(u8 x = 0; x < overlay_width_; x++) {
      if((overlay_rows_[y] & ((u32) 1U << x)) != 0) {
        setPixel(content_left + x, content_top + y, true);
      }
    }
  }
}

void Surface::render(void) {
#if MK61_FIXED_CALCULATOR_FACE
  if(calculator_face_active_) {
    calculator_face::renderFrame(grid_, framebuffer_);
    drawOverlay();
    return;
  }
#endif
#if MK61_PROPORTIONAL_UI_FONTS
  if(ui_text_active_) {
    renderUi();
    return;
  }
#endif
  clearPixels();
  const bool wide_text = grid_.cols() > COLS;
  u8 cell_width = CELL_WIDTH;
  if(wide_text) {
    cell_width = font_ != NULL && font_->metrics().monospaced
        ? font_->metrics().default_advance
        : (u8) (WIDTH / grid_.cols());
    if(cell_width == 0) cell_width = 1;
  }
  const u8 left_margin = wide_text ? 2U : 0U;
  for(u8 row = 0; row < grid_.rows(); row++) {
    for(u8 col = 0; col < grid_.cols(); col++) {
      const u16 cell_x = (u16) left_margin + (u16) col * cell_width;
      if(cell_x >= WIDTH) break;
      builtin_font::Raster raster = {};
      if(resolveToken(grid_.cell(col, row), grid_.cellIsCustom(col, row),
                      raster)) {
        drawGlyph((u8) cell_x, cell_width, row, raster);
      }
      if(row == grid_.cursorY() && col == grid_.cursorX() && cursorVisible()) {
        drawCursor((u8) cell_x, cell_width, row,
                   cursor_blink_ && cursor_blink_phase_);
      }
    }
  }
  drawOverlay();
}

#if MK61_PROPORTIONAL_UI_FONTS
void Surface::renderUi(void) {
  const ui_text_renderer::Style style = {
    ui_font_enabled_, ui_face_, font_, custom_glyphs_, custom_valid_,
    ui_row_gutters_, ui_row_tails_, grid_.cursorX(), grid_.cursorY(),
    cursor_underline_, cursor_blink_ && cursor_blink_phase_
  };
  for(u8 page = 0; page < PAGE_COUNT; ++page) {
    ui_text_renderer::renderPage(
        grid_, style, page, 0, 16,
        framebuffer_ + (usize) page * WIDTH);
  }
  drawOverlay();
}
#endif

} // пространство имён usb_screen
