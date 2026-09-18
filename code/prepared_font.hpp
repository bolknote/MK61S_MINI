#ifndef MK61_PREPARED_FONT_HPP
#define MK61_PREPARED_FONT_HPP

#include "rust_types.h"

// Internal, RAM-only representation of an installed FMK font.  FMK remains
// the compact interchange format on C5; SETUP.APP expands it once into PFK1.
// The resident renderer then performs only a range lookup, one indexed record
// read and a bounded bitmap copy.
namespace prepared_font {

static constexpr usize HEADER_SIZE = 20;
static constexpr usize RANGE_SIZE = 3;
static constexpr usize GLYPH_RECORD_SIZE = 3;
static constexpr usize CRC_OFFSET = 18;
static constexpr usize MAX_IMAGE_SIZE = 8192;
static constexpr u8 MAX_GLYPH_WIDTH = 16;
static constexpr u8 MAX_GLYPH_HEIGHT = 32;
static constexpr usize MAX_BITMAP_SIZE =
    ((MAX_GLYPH_WIDTH + 7U) / 8U) * MAX_GLYPH_HEIGHT;

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
  u16 bitmap_offset;
  u8 width;
  u8 height;
  u8 advance;
};

class Face {
 public:
  Face(void);

  bool open(const u8* data, usize size);
  void reset(void);
  bool valid(void) const { return bytes_ != nullptr; }
  const u8* data(void) const { return bytes_; }
  usize size(void) const { return byte_count_; }
  const Metrics& metrics(void) const { return metrics_; }

  bool glyph(u16 codepoint, Glyph& out) const;
  bool glyphAt(u16 index, Glyph& out) const;
  bool decode(const Glyph& glyph, u8* bitmap, usize capacity) const;

 private:
  const u8* bytes_;
  usize byte_count_;
  u8 range_count_;
  u16 records_offset_;
  u16 bitmap_offset_;
  Metrics metrics_;

  bool glyphIndex(u16 codepoint, u16& index) const;
  bool codepointAt(u16 index, u16& codepoint) const;
  bool recordAt(u16 index, Glyph& out) const;
};

u16 checksum(const u8* data, usize size);

} // namespace prepared_font

#endif
