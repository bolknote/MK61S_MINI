#include "mk8_codec.hpp"
#include "mk8_span.hpp"
#include <vector>
#include <sys/mman.h>
#include <unistd.h>
#include "mk8_literal.hpp"
#include "utf8_codec.hpp"
#include "utf8_view.hpp"

#include <assert.h>
#include <stdio.h>
#include <string.h>

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
  static_assert(mk8::literal_size("🙂") == 0, "unsupported Unicode is rejected");
  static_assert(mk8::literal_size("\xC0\xAF") == 0, "overlong UTF-8 is rejected");
  static_assert(mk8::literal_size("\177") == 0, "invalid M8 controls are rejected");
  static_assert(sizeof(M8_ARRAY("Настройки")) == 10,
                "a Cyrillic source literal needs only one byte per letter");
  static constexpr auto literal = M8_ARRAY("Настройки → Ёё\0дальше");
  static_assert(sizeof(literal) == 22, "only M8 bytes, including the interior NUL");
  static_assert(literal[10] == (char) mk8::BYTE_RIGHT_ARROW, "private M8 symbol");
  static_assert(literal[12] == (char) 0xA8 && literal[13] == (char) 0xB8,
                "CP1251 exceptions");
  struct MenuEntry { u8 size; bool (*action)(); char text[16]; };
  static constexpr auto menu_entry = M8_PUNCT(15, (bool (*)()) nullptr, "Настройки");
  const MenuEntry* const legacy = mk8::punct_view<MenuEntry>(menu_entry);
  assert(legacy->size == 15 && strcmp(legacy->text, M8("Настройки")) == 0);
  assert(strcmp(M8("Настройки"), "\315\340\361\362\360\356\351\352\350") == 0);
  assert(literal[14] == 0 && literal[15] == (char) 0xE4);
  const char* settings = M8("Настройки");
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

void test_reverse_mapping_rejects_every_unassigned_bmp_codepoint(void) {
  // Derive the inverse from the unchanged forward code-page mapping, rather
  // than duplicating the reverse function's ranges and table search order.
  u8 assigned[65536] = {};
  for(u16 value = 1; value <= 0xFFU; ++value) {
    const u8 byte = (u8) value;
    if(!mk8::valid_byte(byte)) continue;
    const u16 codepoint = mk8::codepoint(byte);
    assert(assigned[codepoint] == 0);
    assigned[codepoint] = byte;
  }
  for(u32 codepoint = 0; codepoint < 65536; ++codepoint) {
    u8 byte = 0x5A;
    const bool converted = mk8::from_codepoint(codepoint, byte);
    assert(converted == (assigned[codepoint] != 0));
    assert(byte == (converted ? assigned[codepoint] : 0x5A));
  }
  const u32 supplementary[] = {0x10000U, 0x10FFFFU, 0x110000U, 0xFFFFFFFFU};
  for(u32 codepoint : supplementary) {
    u8 byte = 0x5A;
    assert(!mk8::from_codepoint(codepoint, byte) && byte == 0x5A);
  }
}

void test_word_spans_at_protected_ends(void) {
  const usize page=(usize)sysconf(_SC_PAGESIZE);
  auto mapping=[&]() {
    auto* p=(u8*)mmap(nullptr,page*3,PROT_NONE,MAP_PRIVATE|MAP_ANON,-1,0);
    assert(p!=MAP_FAILED&&mprotect(p+page,page,PROT_READ|PROT_WRITE)==0);return p;
  };
  u8* input=mapping();u8* output=mapping();
  for(unsigned n=0;n<=31;++n)for(unsigned pattern=0;pattern<3;++pattern) {
    std::vector<u8> text(n);
    for(unsigned i=0;i<n;++i)text[i]=pattern==0?(u8)'A':pattern==1?(u8)0xDF:mk8::BYTE_RIGHT_ARROW;
    std::vector<u8> utf8(n*3);std::vector<u16> wide(n);usize count;
    assert(mk8::to_utf8(text.data(),n,utf8.data(),utf8.size(),count));utf8.resize(count);
    assert(mk8::to_utf16(text.data(),n,wide.data(),n,count));
    for(usize capacity=0;capacity<=n*3;++capacity) {
      u8* in=input+2*page-n;u8* out=output+2*page-capacity;
      if(n)memcpy(in,text.data(),n);usize consumed,written;
      assert(mk8_span::to_utf8(in,n,out,capacity,consumed,written));
      assert(!written||memcmp(out,utf8.data(),written)==0);
      in=input+2*page-utf8.size();if(!utf8.empty())memcpy(in,utf8.data(),utf8.size());
      assert(mk8_span::from_utf8(in,utf8.size(),out,capacity,true,consumed,written));
      assert(!written||memcmp(out,text.data(),written)==0);
      in=input+2*page-n*2;if(n)memcpy(in,wide.data(),n*2);
      const bool ok=mk8_span::from_utf16((const u16*)in,n,out,capacity,written);
      assert(ok==(n<=capacity));if(ok)assert(!n||memcmp(out,text.data(),n)==0);
      in=input+2*page-n;if(n)memcpy(in,text.data(),n);
      out=output+2*page-capacity*2;
      assert(mk8_span::to_utf16(in,n,(u16*)out,capacity,written)==(n<=capacity));
      if(n<=capacity)assert(!n||memcmp(out,wide.data(),n*2)==0);
    }
  }
  assert(munmap(input,page*3)==0&&munmap(output,page*3)==0);
}

void test_bounded_word_spans(void) {
  std::vector<u8> m8;
  for(unsigned byte = 1; byte < 256; ++byte) if(mk8::valid_byte((u8)byte)) m8.push_back((u8)byte);
  for(unsigned pattern = 0; pattern < 5; ++pattern) {
    std::vector<u8> input(513);
    for(usize i = 0; i < input.size(); ++i) input[i] = pattern == 0 ? (u8)(' '+i%95) :
        pattern == 1 ? (u8)(0xC0+i%64) : pattern == 2 ? (i%2 ? (u8)0xDF : (u8)'A') :
        pattern == 3 ? m8[i%m8.size()] : (i%7 ? (u8)0xDF : mk8::BYTE_RIGHT_ARROW);
    std::vector<u8> expected(input.size()*3); usize length;
    assert(mk8::to_utf8(input.data(),input.size(),expected.data(),expected.size(),length));expected.resize(length);
    for(unsigned chunk : {1U,2U,3U,4U,7U,8U,31U,64U,512U}) {
      std::vector<u8> received; usize at = 0;
      while(at < expected.size()) {
        const usize count = expected.size()-at < chunk+3U ? expected.size()-at : chunk+3U;
        std::vector<u8> bytes(count); usize consumed,written;
        assert(mk8_span::from_utf8(expected.data()+at,count,bytes.data(),bytes.size(),at+count==expected.size(),consumed,written));
        assert(consumed && written);received.insert(received.end(),bytes.begin(),bytes.begin()+written);at+=consumed;
      }
      assert(received==input);
    }
    for(usize capacity=0;capacity<=expected.size();++capacity) {
      std::vector<u8> bytes(capacity);usize consumed,written;
      assert(mk8_span::to_utf8(input.data(),input.size(),bytes.data(),capacity,consumed,written));
      assert(written<=capacity && (!written || memcmp(bytes.data(),expected.data(),written)==0));
      usize check=0;for(usize i=0;i<consumed;++i)check+=mk8::utf8(input[i]).size;assert(check==written);
    }
    std::vector<u16> units(input.size());std::vector<u8> back(input.size());usize n;
    assert(mk8_span::to_utf16(input.data(),input.size(),units.data(),units.size(),n)&&n==input.size());
    assert(mk8_span::from_utf16(units.data(),units.size(),back.data(),back.size(),n)&&back==input);
  }
  for(unsigned lane=0;lane<4;++lane)for(unsigned cp=0;cp<65536;++cp) {
    u16 units[]={0x0410,0x0411,0x0412,0x0413};units[lane]=(u16)cp;
    u8 a[4]={},b[4]={};usize n,m;
    const bool expected=mk8::from_utf16(units,4,a,4,n);
    assert(mk8_span::from_utf16(units,4,b,4,m)==expected && n==m && memcmp(a,b,n)==0);
  }
  for(unsigned value=0;value<65536;++value) {
    u8 input[]={'A','B','C','D',(u8)(value>>8),(u8)value,'E','F'};
    u8 a[8]={},b[8]={};usize n,m,consumed;
    const bool expected=mk8::from_utf8(input,sizeof(input),a,sizeof(a),n);
    assert(mk8_span::from_utf8(input,sizeof(input),b,sizeof(b),true,consumed,m)==expected && n==m && memcmp(a,b,n)==0);
  }
}

} // namespace

int main(void) {
  test_bounded_word_spans();
  test_word_spans_at_protected_ends();
  test_scalar_boundaries();
  test_malformed_input();
  test_navigation_uses_the_same_decoder();
  test_mk8_compact_firmware_text();
  test_every_m8_byte_round_trips_at_external_boundaries();
  test_reverse_mapping_rejects_every_unassigned_bmp_codepoint();
  puts("utf8_codec_self_test: ok");
  return 0;
}
