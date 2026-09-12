#include "config.h"
#if MK61_FIXED_CALCULATOR_FACE

#include "calculator_face.hpp"

#include "builtin_font.hpp"
#include "display_symbols.hpp"
#include "fmk_font.hpp"

#include <string.h>

namespace calculator_face {
namespace {

class PageCanvas {
 public:
  PageCanvas(u8 page, u8* pixels) : page_(page), pixels_(pixels) {}

  void pixel(i16 x, i16 y) {
    if(x < 0 || x >= (i16) WIDTH || y < 0 || y >= HEIGHT ||
       (u8) (y / PAGE_HEIGHT) != page_) return;
    pixels_[x] |= (u8) (1U << (y & 7));
  }

  void hline(i16 x, i16 y, i16 width) {
    for(i16 px = 0; px < width; ++px) pixel(x + px, y);
  }

 private:
  u8 page_;
  u8* pixels_;
};

enum Segment : u8 {
  SEG_A = 1U << 0,
  SEG_B = 1U << 1,
  SEG_C = 1U << 2,
  SEG_D = 1U << 3,
  SEG_E = 1U << 4,
  SEG_F = 1U << 5,
  SEG_G = 1U << 6,
};

// Twelve physical positions use the whole 192-pixel glass.  A 16-pixel pitch
// leaves five clear columns between 11-pixel digits, while the extra gap keeps
// the two-digit exponent visually separate.  The last vertical segment ends
// at x=190, retaining a one-pixel safety margin at the controller boundary.
static constexpr i16 DIGIT_LEFT = 2;
static constexpr i16 DIGIT_PITCH = 16;
static constexpr i16 EXPONENT_FIRST_SLOT = 9;
static constexpr i16 EXPONENT_GAP = 2;

u8 segments(u16 token) {
  static constexpr u8 DIGITS[10] = {
    SEG_A | SEG_B | SEG_C | SEG_D | SEG_E | SEG_F,
    SEG_B | SEG_C,
    SEG_A | SEG_B | SEG_D | SEG_E | SEG_G,
    SEG_A | SEG_B | SEG_C | SEG_D | SEG_G,
    SEG_B | SEG_C | SEG_F | SEG_G,
    SEG_A | SEG_C | SEG_D | SEG_F | SEG_G,
    SEG_A | SEG_C | SEG_D | SEG_E | SEG_F | SEG_G,
    SEG_A | SEG_B | SEG_C,
    SEG_A | SEG_B | SEG_C | SEG_D | SEG_E | SEG_F | SEG_G,
    SEG_A | SEG_B | SEG_C | SEG_D | SEG_F | SEG_G,
  };
  if(token >= '0' && token <= '9') return DIGITS[token - '0'];
  switch(token) {
    case 'O': return DIGITS[0];
    case '-': return SEG_G;
    case 'L': return SEG_D | SEG_E | SEG_F;
    case 'C': return SEG_A | SEG_D | SEG_E | SEG_F;
    case 'E': return SEG_A | SEG_D | SEG_E | SEG_F | SEG_G;
    case display_symbol::uc1609::CYR_GHE: return SEG_A | SEG_F;
    default: return 0;
  }
}

void horizontalPage(u8* out, i16 x, u8 edge, u8 body) {
  out[x + 1] |= edge;
  for(u8 col = 2; col < 8; ++col) out[x + col] |= body;
  out[x + 8] |= edge;
}

// The fixed geometry is emitted directly in UC1609 page bytes.  This is both
// faster and markedly smaller than clipping every constituent pixel against
// the current page, which matters on the 256-KiB F401 without changing one
// pixel of the reviewed ИВ-2-style face.
void drawSegmentsPage(u8* out, u8 page, i16 x, u8 mask) {
  switch(page) {
    case 2:
      if(mask & SEG_A) horizontalPage(out, x, 0x08, 0x1C);
      if(mask & SEG_F) { out[x] |= 0x80; out[x + 1] |= 0xC0; }
      if(mask & SEG_B) { out[x + 9] |= 0xC0; out[x + 10] |= 0x80; }
      break;
    case 3:
      if(mask & SEG_F) { out[x] = 0xFF; out[x + 1] = 0xFF; }
      if(mask & SEG_B) { out[x + 9] = 0xFF; out[x + 10] = 0xFF; }
      break;
    case 4:
      if(mask & SEG_F) out[x + 1] |= 0x01;
      if(mask & SEG_B) out[x + 9] |= 0x01;
      if(mask & SEG_G) horizontalPage(out, x, 0x08, 0x1C);
      if(mask & SEG_E) { out[x] |= 0x80; out[x + 1] |= 0xC0; }
      if(mask & SEG_C) { out[x + 9] |= 0xC0; out[x + 10] |= 0x80; }
      break;
    case 5:
      if(mask & SEG_E) { out[x] = 0xFF; out[x + 1] = 0xFF; }
      if(mask & SEG_C) { out[x + 9] = 0xFF; out[x + 10] = 0xFF; }
      break;
    case 6:
      if(mask & SEG_E) out[x + 1] |= 0x01;
      if(mask & SEG_C) out[x + 9] |= 0x01;
      if(mask & SEG_D) horizontalPage(out, x, 0x08, 0x1C);
      break;
    default:
      break;
  }
}

void drawArrowPage(u8* out, u8 page, i16 x) {
  static constexpr u8 PAGE4[10] = {
    0x00, 0x38, 0x38, 0x38, 0x38, 0x38, 0x39, 0xBA, 0x54, 0x38
  };
  if(page == 4) {
    for(u8 col = 0; col < sizeof(PAGE4); ++col) out[x + col] |= PAGE4[col];
  } else if(page == 5) {
    out[x + 6] |= 0x01;
  }
}

i16 digitLeft(u8 slot) {
  return DIGIT_LEFT + (i16) slot * DIGIT_PITCH +
      (slot >= EXPONENT_FIRST_SLOT ? EXPONENT_GAP : 0);
}

void drawDigitPage(u8* out, u8 page, i16 x, u16 token) {
  if(token == display_symbol::uc1609::RT_ARROW) drawArrowPage(out, page, x);
  else drawSegmentsPage(out, page, x, segments(token));
}

void drawDecimalPage(u8* out, u8 page, i16 x) {
  if(page != 6) return;
  out[x + 11] |= 0x18;
  out[x + 12] |= 0x18;
}

void __attribute__((noinline)) drawIndicatorPage(
    u8* out, u8 page, const text_screen::Grid& grid) {
  u8 slot = 0;
  for(u8 col = 0; col < grid.cols() && slot < 12; ++col) {
    const u16 token = grid.cell(col, 1);
    if(token == '.') {
      if(slot == 0) {
        if(page == 6) { out[0] |= 0x18; out[1] |= 0x18; }
      } else {
        drawDecimalPage(out, page, digitLeft((u8) (slot - 1U)));
      }
    } else {
      drawDigitPage(out, page, digitLeft(slot), token);
      ++slot;
    }
  }
}

void drawSmallGlyph(PageCanvas& canvas, u16 token, i16 x, i16 y) {
  builtin_font::Raster raster = {};
  if(!builtin_font::decode(builtin_font::FaceId::FONT_5X8, token, raster) &&
     !builtin_font::decode(builtin_font::FaceId::FONT_5X8, '?', raster)) return;
  for(u8 py = 0; py < raster.height; ++py) {
    for(u8 px = 0; px < raster.width; ++px) {
      if(fmk::bitmapPixel(raster.data, raster.width, px, py)) {
        canvas.pixel(x + px, y + py);
      }
    }
  }
}

void drawServiceField(PageCanvas& canvas, const text_screen::Grid& grid,
                      u8 first, u8 count, i16 left, i16 width) {
  u8 begin = first;
  u8 end = (u8) (first + count);
  while(begin < end && grid.cell(begin, 0) == ' ') ++begin;
  while(end > begin && grid.cell((u8) (end - 1U), 0) == ' ') --end;
  const i16 text_width = (i16) (end - begin) * 6 - (end > begin ? 1 : 0);
  i16 pen = left + (width - text_width) / 2;
  for(u8 col = begin; col < end; ++col) {
    drawSmallGlyph(canvas, grid.cell(col, 0), pen, 2);
    pen += 6;
  }
  // Short luminous rails visually separate status from the main VFD without
  // spending another row of the calculator's logical text model.
  canvas.hline(left + 2, 12, width - 4);
  canvas.pixel(left + 1, 11);
  canvas.pixel(left + width - 2, 11);
}

void drawService(PageCanvas& canvas, const text_screen::Grid& grid) {
  drawServiceField(canvas, grid, 0, 5, 1, 61);
  drawServiceField(canvas, grid, 6, 3, 65, 45);
  drawServiceField(canvas, grid, 10, 6, 113, 78);
}

} // namespace

void renderPage(const text_screen::Grid& grid, u8 page, u8 out[WIDTH]) {
  if(out == NULL || page >= PAGE_COUNT) return;
  memset(out, 0, WIDTH);
  PageCanvas canvas(page, out);
  if(page < 2) drawService(canvas, grid);
  if(page >= 2 && page <= 6) drawIndicatorPage(out, page, grid);
}

void renderFrame(const text_screen::Grid& grid, u8 out[FRAME_BYTES]) {
  if(out == NULL) return;
  for(u8 page = 0; page < PAGE_COUNT; ++page) {
    renderPage(grid, page, out + (usize) page * WIDTH);
  }
}

} // namespace calculator_face
#endif
