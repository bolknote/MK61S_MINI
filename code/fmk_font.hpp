#ifndef FMK_FONT_HPP
#define FMK_FONT_HPP

#include "rust_types.h"

namespace fmk {

static constexpr usize HEADER_SIZE = 16;
static constexpr usize RANGE_SIZE = 3;
static constexpr usize MAX_FILE_SIZE = 1536;
static constexpr u8 MAX_GLYPH_WIDTH = 16;
static constexpr u8 MAX_GLYPH_HEIGHT = 32;
static constexpr usize MAX_BITMAP_SIZE =
  ((MAX_GLYPH_WIDTH + 7) / 8) * MAX_GLYPH_HEIGHT;

static constexpr u8 FLAG_MONOSPACED = 0x01;

struct Metrics {
  bool monospaced;
  u8 max_width;
  u8 height;
  u8 default_advance;
  u8 line_gap;
  u16 glyph_count;
};

struct Glyph {
  u16 codepoint;
  u16 index;
  u32 record_bit_offset;
  u8 width;
  u8 height;
  u8 advance;
};

class Face {
  public:
    Face(void);

    bool open(const u8* data, usize size);
    void reset(void);
    bool valid(void) const { return bytes != 0; }
    const Metrics& metrics(void) const { return face_metrics; }

    bool glyph(u16 codepoint, Glyph& out) const;
    bool glyphAt(u16 index, Glyph& out) const;
    bool decode(const Glyph& glyph, u8* bitmap, usize capacity) const;

  private:
    const u8* bytes;
    usize byte_count;
    u8 range_count;
    u32 stream_bit_offset;
    Metrics face_metrics;

    bool glyphIndex(u16 codepoint, u16& index) const;
    bool codepointAt(u16 index, u16& codepoint) const;
    bool recordAt(u16 index, Glyph& out) const;
};

u16 checksum(const u8* data, usize size);
bool bitmapPixel(const u8* bitmap, u8 width, u8 x, u8 y);
bool scaleToLcd5x8(const Face& face, const Glyph& glyph, u8 rows[8]);
u8 selectPreviewGlyphs(const Face& face, Glyph out[8]);

} // namespace fmk

#endif
