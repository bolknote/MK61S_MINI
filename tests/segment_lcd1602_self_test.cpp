#include "segment_lcd1602.hpp"

#include <cassert>
#include <cstdint>
#include <cstdio>

static uint64_t raster_signature(u8 mask) {
  u8 rows[8] = {};
  segment_lcd1602::custom_rows(mask, rows);
  uint64_t signature = 0;
  for(u8 row : rows) {
    assert((row & ~0x1FU) == 0);
    signature = (signature << 5) | row;
  }
  return signature;
}

int main() {
  using namespace segment_lcd1602;

  // Every one of the 256 mask values has an unambiguous five-by-eight custom
  // raster, even if the frame planner elects to use a CGROM approximation.
  for(unsigned mask = 0; mask < 256; ++mask) {
    for(unsigned previous = 0; previous < mask; ++previous)
      assert(raster_signature((u8) mask) !=
             raster_signature((u8) previous));
    u8 repeated[CELLS] = {};
    for(u8& cell : repeated) cell = (u8) mask;
    const Plan single = plan(repeated);
    assert(single.overflow_count == 0);
    u8 native = 0;
    if(native_character((u8) mask, native)) {
      assert(single.custom_count == 0);
      for(u8 byte : single.characters) assert(byte == native);
    } else {
      assert(single.custom_count == 1 && single.custom_masks[0] == mask);
      for(u8 byte : single.characters) assert(byte == 0);
    }
  }

  for(const NativeGlyph& glyph : NATIVE_GLYPHS) {
    u8 character = 0;
    assert(native_character(glyph.mask, character));
    assert(character == glyph.character);
  }
  const u8 digits[10] = {0x3F, 0x06, 0x5B, 0x4F, 0x66,
                         0x6D, 0x7D, 0x07, 0x7F, 0x6F};
  for(u8 digit = 0; digit < 10; ++digit) {
    u8 character = 0;
    assert(native_character(digits[digit], character));
    assert(character == (u8) ('0' + digit));
  }

#if defined(MK61_LCD1602_A02)
  u8 character = 0;
  assert(native_character(0x31, character) &&
         character == lcd_charset::CYR_GHE);
  assert(native_character(0x37, character) &&
         character == lcd_charset::CYR_PE);
#else
  u8 character = 0;
  assert(!native_character(0x31, character));
  assert(!native_character(0x37, character));
#endif
  assert(!native_character(0xBF, character)); // zero with decimal point
  assert(native_character(0x80, character) && character == '.');
  u8 all_segments[8] = {};
  custom_rows(0xFF, all_segments);
  assert(all_segments[0] == 0x0E &&
         all_segments[1] == 0x11 && all_segments[2] == 0x11 &&
         all_segments[3] == 0x0E &&
         all_segments[4] == 0x11 && all_segments[5] == 0x11 &&
         all_segments[6] == 0x11 && all_segments[7] == 0x0F);

  const u8 ordinary[CELLS] = {
      0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D,
      0x7D, 0x07, 0x7F, 0x6F, 0xBF, 0xBF};
  const Plan familiar = plan(ordinary);
  assert(familiar.custom_count == 1 && familiar.overflow_count == 0);
  for(u8 index = 0; index < 10; ++index)
    assert(familiar.characters[index] == (u8) ('0' + index));
  assert(familiar.custom_masks[0] == 0xBF);
  assert(familiar.characters[10] == 0 && familiar.characters[11] == 0);

  const u8 exactly_eight[CELLS] = {
      0x01, 0x02, 0x03, 0x04, 0x05, 0x09,
      0x0A, 0x0B, 0x01, 0x02, 0x03, 0x04};
  const Plan full = plan(exactly_eight);
  assert(full.custom_count == CUSTOM_GLYPHS && full.overflow_count == 0);
  for(u8 byte : full.characters) assert(byte < CUSTOM_GLYPHS);

  const u8 crowded[CELLS] = {
      0x01, 0x02, 0x03, 0x04, 0x05, 0x09,
      0x0A, 0x0B, 0x0C, 0x0C, 0x0C, 0x0D};
  const Plan limited = plan(crowded);
  assert(limited.custom_count == CUSTOM_GLYPHS);
  assert(limited.custom_masks[0] == 0x0C); // most frequent mask wins
  assert(limited.overflow_count == 2);
  assert(limited.characters[7] == '?' && limited.characters[11] == '?');
  assert(limited.characters[8] == 0 && limited.characters[9] == 0 &&
         limited.characters[10] == 0);

  std::puts("all 256 masks, CGROM mappings, and eight-slot frame planning: OK");
}
