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

} // namespace

int main(void) {
  test_scalar_boundaries();
  test_malformed_input();
  test_navigation_uses_the_same_decoder();
  puts("utf8_codec_self_test: ok");
  return 0;
}
