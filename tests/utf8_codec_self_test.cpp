#include "mk8_codec.hpp"
#include "mk8_strings.inc"
#include "utf8_codec.hpp"
#include "utf8_view.hpp"

#include <assert.h>
#include <stdio.h>

namespace {

void expect_valid(const u8* bytes, usize size, u32 codepoint) {
  const utf8_codec::Decoded decoded = utf8_codec::decode(bytes, size);
  assert(decoded.valid);
  assert(decoded.size == size);
  assert(decoded.codepoint == codepoint);
}

void expect_invalid(const u8* bytes, usize size) {
  const utf8_codec::Decoded decoded = utf8_codec::decode(bytes, size);
  assert(!decoded.valid);
  assert(decoded.size == 1);
  assert(decoded.codepoint == utf8_codec::REPLACEMENT_CODEPOINT);
}

void test_scalar_boundaries(void) {
  static const u8 nul[] = {0x00};
  static const u8 ascii[] = {0x7F};
  static const u8 first_two[] = {0xC2, 0x80};
  static const u8 last_two[] = {0xDF, 0xBF};
  static const u8 first_three[] = {0xE0, 0xA0, 0x80};
  static const u8 before_surrogates[] = {0xED, 0x9F, 0xBF};
  static const u8 after_surrogates[] = {0xEE, 0x80, 0x80};
  static const u8 last_three[] = {0xEF, 0xBF, 0xBF};
  static const u8 first_four[] = {0xF0, 0x90, 0x80, 0x80};
  static const u8 last_four[] = {0xF4, 0x8F, 0xBF, 0xBF};

  expect_valid(nul, sizeof(nul), 0x0000);
  expect_valid(ascii, sizeof(ascii), 0x007F);
  expect_valid(first_two, sizeof(first_two), 0x0080);
  expect_valid(last_two, sizeof(last_two), 0x07FF);
  expect_valid(first_three, sizeof(first_three), 0x0800);
  expect_valid(before_surrogates, sizeof(before_surrogates), 0xD7FF);
  expect_valid(after_surrogates, sizeof(after_surrogates), 0xE000);
  expect_valid(last_three, sizeof(last_three), 0xFFFF);
  expect_valid(first_four, sizeof(first_four), 0x10000);
  expect_valid(last_four, sizeof(last_four), 0x10FFFF);
}

void test_malformed_input(void) {
  static const u8 stray_continuation[] = {0x80};
  static const u8 obsolete_lead[] = {0xC0, 0xAF};
  static const u8 overlong_three[] = {0xE0, 0x9F, 0xBF};
  static const u8 surrogate[] = {0xED, 0xA0, 0x80};
  static const u8 overlong_four[] = {0xF0, 0x8F, 0xBF, 0xBF};
  static const u8 above_unicode[] = {0xF4, 0x90, 0x80, 0x80};
  static const u8 invalid_lead[] = {0xF5, 0x80, 0x80, 0x80};
  static const u8 truncated[] = {0xE2, 0x82};
  static const u8 bad_continuation[] = {0xE2, 0x28, 0xA1};

  expect_invalid(stray_continuation, sizeof(stray_continuation));
  expect_invalid(obsolete_lead, sizeof(obsolete_lead));
  expect_invalid(overlong_three, sizeof(overlong_three));
  expect_invalid(surrogate, sizeof(surrogate));
  expect_invalid(overlong_four, sizeof(overlong_four));
  expect_invalid(above_unicode, sizeof(above_unicode));
  expect_invalid(invalid_lead, sizeof(invalid_lead));
  expect_invalid(truncated, sizeof(truncated));
  expect_invalid(bad_continuation, sizeof(bad_continuation));

  const utf8_codec::Decoded empty = utf8_codec::decode(nullptr, 0);
  assert(!empty.valid && empty.size == 0);
  assert(utf8_codec::decode_cstring("").size == 0);

  // decode_cstring() must stop at NUL instead of speculatively reading the
  // missing continuation bytes.  ASan makes this a regression test for the
  // exact boundary that the old per-caller decoders handled inconsistently.
  static const char truncated_cstring[] = {(char) 0xE2, 0};
  const utf8_codec::Decoded decoded_cstring =
      utf8_codec::decode_cstring(truncated_cstring);
  assert(!decoded_cstring.valid && decoded_cstring.size == 1);
}

void test_navigation_uses_the_same_decoder(void) {
  static const u8 text[] = {0xC0, 0xAF, 0xF0, 0x9F, 0x98, 0x80};
  assert(utf8_view::sequence_length(text, sizeof(text), 0) == 1);
  assert(utf8_view::sequence_length(text, sizeof(text), 1) == 1);
  assert(utf8_view::sequence_length(text, sizeof(text), 2) == 4);
  assert(utf8_view::next_offset(text, sizeof(text), 2) == sizeof(text));
  assert(utf8_view::previous_offset(text, sizeof(text), sizeof(text)) == 2);

  const utf8_codec::Decoded emoji =
      utf8_codec::decode_cstring("\xF0\x9F\x98\x80");
  assert(emoji.valid && emoji.size == 4 && emoji.codepoint == 0x1F600);
}

void test_mk8_compact_firmware_text(void) {
  const char* settings = M8_SETTINGS;
  static const u16 expected[] = {
      0x041D, 0x0430, 0x0441, 0x0442, 0x0440,
      0x043E, 0x0439, 0x043A, 0x0438}; // Настройки
  for(u16 codepoint : expected) assert(mk8::next(settings) == codepoint);
  assert(*settings == 0);

  static const char symbols[] = {
      (char) mk8::BYTE_LEFT_ARROW,
      (char) mk8::BYTE_RIGHT_ARROW,
      (char) mk8::BYTE_UP_ARROW,
      (char) mk8::BYTE_DOWN_ARROW,
      (char) mk8::BYTE_PI,
      (char) mk8::BYTE_SQRT,
      (char) mk8::BYTE_CYCLE_ARROW,
      (char) mk8::BYTE_NOT_EQUAL,
      (char) mk8::BYTE_LESS_EQUAL,
      (char) mk8::BYTE_GREATER_EQUAL,
      (char) mk8::BYTE_MULTIPLY,
      (char) mk8::BYTE_DIVIDE,
      (char) mk8::BYTE_POWER_2,
      (char) mk8::BYTE_POWER_Y,
      (char) mk8::BYTE_POWER_X,
      (char) mk8::BYTE_XOR,
      (char) mk8::BYTE_POWER_MINUS,
      (char) mk8::BYTE_RETURN_ARROW,
      (char) 0x85,
      (char) 0xB0, 0};
  const u16 symbol_codepoints[] = {
      0x2190, 0x2192, 0x2191, 0x2193, 0x03C0, 0x221A,
      0x21BB, 0x2260, 0x2264, 0x2265, 0x00D7, 0x00F7,
      0x00B2, 0x02B8, 0x02E3, 0x22BB, 0x207B, 0x21B5,
      0x2026, 0x00B0};
  const char* cursor = symbols;
  for(u16 codepoint : symbol_codepoints) {
    assert(mk8::next(cursor) == codepoint);
  }
  assert(*cursor == 0);
  assert(mk8::codepoint(0xA8) == 0x0401);
  assert(mk8::codepoint(0xB8) == 0x0451);
  assert(mk8::codepoint(0xC0) == 0x0410);
  assert(mk8::codepoint(0xFF) == 0x044F);
  assert(mk8::codepoint(0x84) == 0x201E);
  assert(mk8::codepoint(0x1F) == 0x21B5);
}

void test_every_m8_byte_round_trips_at_external_boundaries(void) {
  for(u16 value = 1; value <= 0xFFU; ++value) {
    const u8 byte = (u8) value;
    const bool expected_valid = byte == '\t' || byte == '\n' || byte == '\r' ||
        (byte >= mk8::BYTE_LEFT_ARROW && byte != 0x7FU && byte != 0x98U);
    assert(mk8::valid_byte(byte) == expected_valid);
    if(!expected_valid) continue;

    const mk8::Utf8Bytes utf8 = mk8::utf8(byte);
    u8 decoded = 0;
    usize decoded_size = 0;
    assert(mk8::from_utf8(utf8.data, utf8.size, &decoded, 1, decoded_size));
    assert(decoded_size == 1 && decoded == byte);

    u16 utf16 = 0;
    usize utf16_size = 0;
    assert(mk8::to_utf16(&byte, 1, &utf16, 1, utf16_size));
    assert(utf16_size == 1 && utf16 == mk8::codepoint(byte));
    decoded = 0;
    decoded_size = 0;
    assert(mk8::from_utf16(&utf16, 1, &decoded, 1, decoded_size));
    assert(decoded_size == 1 && decoded == byte);
  }

  const u16 surrogate = 0xD800U;
  u8 output = 0;
  usize output_size = 0;
  assert(!mk8::from_utf16(&surrogate, 1, &output, 1, output_size));
}

} // namespace

int main(void) {
  test_scalar_boundaries();
  test_malformed_input();
  test_navigation_uses_the_same_decoder();
  test_mk8_compact_firmware_text();
  test_every_m8_byte_round_trips_at_external_boundaries();
  puts("utf8_codec_self_test: ok");
  return 0;
}
