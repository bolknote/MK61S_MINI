#ifndef FMK_FONT_HPP
#define FMK_FONT_HPP

#include "rust_types.h"

namespace fmk {

static constexpr usize HEADER_SIZE = 16;
static constexpr usize RANGE_SIZE = 2;
// FMK2 stores its length in 16 bits, but the current largest SETUP workspace
// and prepared-font BULK arena are 8 KiB. Individual products may impose a
// smaller storage/runtime limit (notably F401).
static constexpr usize MAX_FILE_SIZE = 8192;
static constexpr u8 MAX_GLYPH_WIDTH = 16;
static constexpr u8 MAX_GLYPH_HEIGHT = 32;
static constexpr usize MAX_BITMAP_SIZE =
  ((MAX_GLYPH_WIDTH + 7) / 8) * MAX_GLYPH_HEIGHT;

static constexpr u8 FLAG_MONOSPACED = 0x01;

// Cheap resident-side gate before SETUP.APP reads and fully validates FMK2.
// Keep the interchange header layout here with the decoder constants so a
// format revision cannot leave the M61 `loadfont` preflight behind again.
inline bool plausibleHeader(const u8* data, usize total_size) {
  if(data == nullptr || total_size < HEADER_SIZE ||
     total_size > MAX_FILE_SIZE ||
     data[0] != 'F' || data[1] != 'M' ||
     data[2] != 'K' || data[3] != '2' ||
     (data[4] & (u8) ~FLAG_MONOSPACED) != 0 ||
     data[5] == 0 || data[5] > MAX_GLYPH_WIDTH ||
     data[6] == 0 || data[6] > MAX_GLYPH_HEIGHT ||
     (data[8] == 0 && data[9] == 0) ||
     data[10] == 0 || data[11] != 0) {
    return false;
  }
  const u16 declared_size = (u16) data[12] | ((u16) data[13] << 8);
  return declared_size == total_size &&
      HEADER_SIZE + (usize) data[10] * RANGE_SIZE <= total_size;
}

struct Metrics {
  bool monospaced;
  u8 max_width;
  u8 height;
  u8 default_advance;
  u8 line_gap;
  u16 glyph_count;
};

struct Glyph {
  u8 byte;
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
    const u8* data(void) const { return bytes; }
    usize size(void) const { return byte_count; }
    const Metrics& metrics(void) const { return face_metrics; }

    bool glyph(u8 byte, Glyph& out) const;
    bool glyphAt(u16 index, Glyph& out) const;
    bool decode(const Glyph& glyph, u8* bitmap, usize capacity) const;
    u8 rangeCount(void) const { return range_count; }
    bool rangeAt(u8 index, u8& start, u16& count) const;

  private:
    const u8* bytes;
    usize byte_count;
    u8 range_count;
    u32 stream_bit_offset;
    Metrics face_metrics;

    bool glyphIndex(u8 byte, u16& index) const;
    bool byteAt(u16 index, u8& byte) const;
    bool recordAt(u16 index, Glyph& out) const;
};

u16 checksum(const u8* data, usize size);
bool bitmapPixel(const u8* bitmap, u8 width, u8 x, u8 y);
bool scaleToLcd5x8(const Face& face, const Glyph& glyph, u8 rows[8]);
u8 selectPreviewGlyphs(const Face& face, Glyph out[8]);
// Compiles FMK2 into the internal, uncompressed PFK2 runtime image.  This is
// linked into SETUP.APP and host tools, never needed by the resident renderer.
bool prepare(const Face& face, u8* output, usize capacity, usize& output_size);

} // пространство имён fmk

#endif
