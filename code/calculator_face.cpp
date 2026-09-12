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

// kimstik's 16x32 strike: twelve physical cells exactly occupy the 192-pixel
// glass. The full 32-pixel source raster is centred in the 48-pixel calculator
// area below the two status pages.
// Source: https://gist.github.com/kimstik/9210d1a34c91c30b42ed4cb134e908e0
static constexpr i16 DIGIT_TOP = 24;
static constexpr i16 DIGIT_PITCH = 16;

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
  static constexpr u8 LETTER_E = SEG_A | SEG_D | SEG_E | SEG_F | SEG_G;
  if(token >= '0' && token <= '9') return DIGITS[token - '0'];
  switch(token) {
    case 'O': return DIGITS[0];
    case '-': return SEG_G;
    // Keep both halves of E's left stem. Using only the upper segment made
    // Г look like a small hook; deriving the letters from E keeps their full
    // height and the exact slant/chamfers of the selected calculator face.
    case 'L': return LETTER_E & (u8) ~(SEG_A | SEG_G);
    case 'C': return LETTER_E & (u8) ~SEG_G;
    case 'E': return LETTER_E;
    case display_symbol::uc1609::CYR_GHE:
      return LETTER_E & (u8) ~(SEG_D | SEG_G);
    default: return 0;
  }
}

// Pixel-exact segment rows from kimstik/mk61_font16x32.h. Source bits are
// MSB-left, one u16 per 16-pixel row; the eighth plane is the decimal point.
static constexpr u16 GIST_SEGMENT_ROWS[8][32] = {
  { 0x07F0,0x0FE0,0x0FC0,0,0,0,0,0,0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0 },
  { 0,0,0x0006,0x0006,0x000E,0x001E,0x001C,0x001C,
    0x001C,0x003C,0x001C,0x0008,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0 },
  { 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
    0x0018,0x0038,0x0070,0x0070,0x00F0,0x00F0,0x00F0,0x00E0,
    0x0060,0x0060,0,0,0,0,0,0 },
  { 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
    0xE000,0xFE00,0x7F00,0x3F00,0,0,0,0,0 },
  { 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0x2000,
    0x7000,0x7000,0x7000,0x7000,0xF000,0,0,0,0,0,0,0,0,0,0,0 },
  { 0,0,0,0,0,0x1E00,0x1C00,0x1C00,0x1C00,0x3800,0x2000,
    0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0 },
  { 0,0,0,0,0,0,0,0,0,0,0,0,0x07E0,0x0FE0,0x0FC0,
    0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0 },
  { 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
    0x0003,0x0003,0x0003,0x0007,0x0007,0x0007 },
};

void drawSegmentsPage(u8* out, u8 page, i16 x, u8 mask, bool dot = false) {
  for(u8 row = 0; row < 32; ++row) {
    const i16 y = DIGIT_TOP + row;
    if((u8) (y / PAGE_HEIGHT) != page) continue;
    u16 pixels = dot ? GIST_SEGMENT_ROWS[7][row] : 0;
    for(u8 segment = 0; segment < 7; ++segment) {
      if(mask & (1U << segment)) pixels |= GIST_SEGMENT_ROWS[segment][row];
    }
    const u8 page_bit = (u8) (1U << (y & 7));
    for(u8 col = 0; col < 16; ++col) {
      if(pixels & ((u16) 0x8000U >> col)) out[x + col] |= page_bit;
    }
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
  return (i16) slot * DIGIT_PITCH;
}

void drawDigitPage(u8* out, u8 page, i16 x, u16 token) {
  if(token == display_symbol::uc1609::RT_ARROW) drawArrowPage(out, page, x);
  else drawSegmentsPage(out, page, x, segments(token));
}

void drawDecimalPage(u8* out, u8 page, i16 x) {
  drawSegmentsPage(out, page, x, 0, true);
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
