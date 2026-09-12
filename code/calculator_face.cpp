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

struct Indicator {
  u16 cells[12];
  u16 dots;
  bool leading_dot;
};

u8 segments(u16 token) {
  switch(token) {
    case '0': case 'O': return SEG_A | SEG_B | SEG_C | SEG_D | SEG_E | SEG_F;
    case '1': return SEG_B | SEG_C;
    case '2': return SEG_A | SEG_B | SEG_D | SEG_E | SEG_G;
    case '3': return SEG_A | SEG_B | SEG_C | SEG_D | SEG_G;
    case '4': return SEG_B | SEG_C | SEG_F | SEG_G;
    case '5': return SEG_A | SEG_C | SEG_D | SEG_F | SEG_G;
    case '6': return SEG_A | SEG_C | SEG_D | SEG_E | SEG_F | SEG_G;
    case '7': return SEG_A | SEG_B | SEG_C;
    case '8': return SEG_A | SEG_B | SEG_C | SEG_D | SEG_E | SEG_F | SEG_G;
    case '9': return SEG_A | SEG_B | SEG_C | SEG_D | SEG_F | SEG_G;
    case '-': return SEG_G;
    case 'L': return SEG_D | SEG_E | SEG_F;
    case 'C': return SEG_A | SEG_D | SEG_E | SEG_F;
    case 'E': return SEG_A | SEG_D | SEG_E | SEG_F | SEG_G;
    case display_symbol::uc1609::CYR_GHE: return SEG_A | SEG_F;
    default: return 0;
  }
}

void horizontal(PageCanvas& canvas, i16 x, i16 y) {
  // Bevelled three-pixel stroke: close to a VFD segment, but still crisp on
  // the native 192x64 monochrome matrix.
  canvas.hline(x + 2, y - 1, 6);
  canvas.hline(x + 1, y, 8);
  canvas.hline(x + 2, y + 1, 6);
}

void vertical(PageCanvas& canvas, i16 x, i16 y) {
  // The original indicator has straight, symmetric vertical strokes.  Keep
  // the three-pixel body on one axis and bevel only its two end caps; shifting
  // the lower half makes every digit look broken rather than VFD-like.
  canvas.pixel(x + 1, y);
  for(i16 row = 1; row < 12; ++row) canvas.hline(x, y + row, 3);
  canvas.pixel(x + 1, y + 12);
}

void drawSegments(PageCanvas& canvas, i16 x, u8 mask) {
  static constexpr i16 TOP = 18;
  if(mask & SEG_A) horizontal(canvas, x, TOP);
  if(mask & SEG_G) horizontal(canvas, x, TOP + 18);
  if(mask & SEG_D) horizontal(canvas, x, TOP + 36);
  if(mask & SEG_F) vertical(canvas, x, TOP + 3);
  if(mask & SEG_B) vertical(canvas, x + 7, TOP + 3);
  if(mask & SEG_E) vertical(canvas, x, TOP + 21);
  if(mask & SEG_C) vertical(canvas, x + 7, TOP + 21);
}

void drawArrow(PageCanvas& canvas, i16 x) {
  const i16 y = 36;
  canvas.hline(x + 1, y - 1, 7);
  canvas.hline(x + 1, y, 9);
  canvas.hline(x + 1, y + 1, 7);
  for(i16 n = 0; n < 4; ++n) {
    canvas.pixel(x + 6 + n, y - 4 + n);
    canvas.pixel(x + 6 + n, y + 4 - n);
  }
}

void drawDigit(PageCanvas& canvas, i16 x, u16 token, bool dot) {
  if(token == display_symbol::uc1609::RT_ARROW) drawArrow(canvas, x);
  else drawSegments(canvas, x, segments(token));
  if(dot) {
    // A VFD decimal point belongs to the digit on its left.  It never takes a
    // thirteenth text cell and therefore cannot move the exponent.
    canvas.pixel(x + 11, 55);
    canvas.pixel(x + 12, 55);
    canvas.pixel(x + 11, 56);
    canvas.pixel(x + 12, 56);
  }
}

Indicator readIndicator(const text_screen::Grid& grid) {
  Indicator result = {{' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' '}, 0, false};
  u8 slot = 0;
  for(u8 col = 0; col < grid.cols() && slot < 12; ++col) {
    const u16 token = grid.cell(col, 1);
    if(token == '.') {
      if(slot == 0) result.leading_dot = true;
      else result.dots |= (u16) (1U << (slot - 1U));
      continue;
    }
    result.cells[slot++] = token;
  }
  return result;
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

void render(PageCanvas& canvas, const text_screen::Grid& grid) {
  drawService(canvas, grid);
  const Indicator indicator = readIndicator(grid);
  for(u8 slot = 0; slot < 12; ++slot) {
    const i16 x = 4 + (i16) slot * 14 + (slot >= 9 ? 7 : 0);
    drawDigit(canvas, x, indicator.cells[slot],
              (indicator.dots & ((u16) 1U << slot)) != 0);
  }
  if(indicator.leading_dot) {
    canvas.pixel(2, 55); canvas.pixel(3, 55);
    canvas.pixel(2, 56); canvas.pixel(3, 56);
  }
}

} // namespace

void renderPage(const text_screen::Grid& grid, u8 page, u8 out[WIDTH]) {
  if(out == NULL || page >= PAGE_COUNT) return;
  memset(out, 0, WIDTH);
  PageCanvas canvas(page, out);
  render(canvas, grid);
}

void renderFrame(const text_screen::Grid& grid, u8 out[FRAME_BYTES]) {
  if(out == NULL) return;
  for(u8 page = 0; page < PAGE_COUNT; ++page) {
    renderPage(grid, page, out + (usize) page * WIDTH);
  }
}

} // namespace calculator_face
#endif
