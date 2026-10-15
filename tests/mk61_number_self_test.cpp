// Differential coverage of the resident numeric reader against the real
// calculator formatters. Include the real core to exercise both physical ring
// layouts; no formatter or calculator-register I/O is mocked in this test.
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>
#include <vector>

#include "../code/mk61emu_core.cpp"
#include "mk61_ref.hpp"
#include "terminal_core.hpp"

namespace {

constexpr char TERMINAL_SYMBOLS[16] = {
    '0','1','2','3','4','5','6','7','8','9','-','L','C','\303','E',' '
};
constexpr u64 SENTINEL_BITS = 0x405edd2f1a9fbe77ULL;
using Word = std::array<u8, 12>; // Eight leading-first digits, sign, order sign/high/low.

struct Entry {
  bool is_stack;
  int index;
};

u64 cases = 0, accepted = 0, rejected = 0, strict_errors = 0;
u64 permissive_differences = 0;
u32 random_state = 0x4d36314eU;
const char* scenario = "initialization";
Word current_word = {};
bool expanded = false;

u32 random_word() {
  random_state ^= random_state << 13;
  random_state ^= random_state >> 17;
  random_state ^= random_state << 5;
  return random_state;
}

double sentinel() {
  double value;
  const u64 bits = SENTINEL_BITS;
  std::memcpy(&value, &bits, sizeof(value));
  return value;
}

[[noreturn]] void fail(const Entry& entry, const char* message,
                       double actual = 0, double expected = 0) {
  std::fprintf(stderr,
      "FAIL %s expanded=%d %s%d: %s actual=%016llx expected=%016llx word=",
      scenario, expanded, entry.is_stack ? "stack" : "R", entry.index, message,
      (unsigned long long) mk_math::binary64_bits(actual),
      (unsigned long long) mk_math::binary64_bits(expected));
  for(u8 cell : current_word) std::fprintf(stderr, "%02x,", (unsigned) cell);
  std::fputc('\n', stderr);
  std::exit(1);
}

usize physical_base(const Entry& entry) {
  return entry.is_stack
      ? core_61::stack_address((stack) entry.index) + 1
      : (usize) entry.index * 42;
}

void fixture(const Entry& entry, const Word& word) {
  current_word = word;
  const usize base = physical_base(entry);
  for(usize i = 0; i < 8; ++i) ringM[base + (7-i)*3] = word[i];
  ringM[base + 24] = word[8];
  ringM[base + 33] = word[9];
  ringM[base + 30] = word[10];
  ringM[base + 27] = word[11];
}

Word decimal_word(u32 mantissa, int exponent, bool negative) {
  Word word = {};
  for(int digit = 7; digit >= 0; --digit) {
    word[digit] = (u8) (mantissa % 10);
    mantissa /= 10;
  }
  word[8] = negative ? 9 : 0;
  int stored = exponent;
  if(stored < 0) {
    stored += 100;
    word[9] = 9;
  }
  word[10] = (u8) (stored / 10);
  word[11] = (u8) (stored % 10);
  return word;
}

Word integer_word(u32 magnitude, bool negative) {
  if(!magnitude) return decimal_word(0, 0, negative);
  u32 normalized = magnitude;
  int exponent = 0;
  for(u32 rest = magnitude; rest >= 10; rest /= 10) ++exponent;
  for(int digits = exponent; digits < 7; ++digits) normalized *= 10;
  return decimal_word(normalized, exponent, negative);
}

bool canonical(const Word& word) {
  for(usize i = 0; i < 8; ++i) if(word[i] > 9) return false;
  if((word[8] != 0 && word[8] != 9) ||
     (word[9] != 0 && word[9] != 9) || word[10] > 9 || word[11] > 9)
    return false;
  return word[9] == 0 || word[10] != 0 || word[11] != 0;
}

void formatted(const Entry& entry, char (&text)[15], const char* symbols) {
  // Only valid entries reach this function: old invalid-index formatters
  // initialize text[0] alone, not a complete readable display string.
  if(entry.is_stack) read_stack_register((stack) entry.index, text, symbols);
  else MK61Emu_ReadRegister(entry.index, text, symbols);
}

bool try_read(const Entry& entry, double& value) {
  return entry.is_stack
      ? mk61_ref::try_read_stack_number((stack) entry.index, value)
      : mk61_ref::try_read_register_number(entry.index, value);
}

// Frozen permissive reference parser. Unlike IF's strict parser, it accepts
// partial decimal strings produced by nondecimal calculator words.
double legacy_reference_number(const char* value) {
  char buffer[20];
  char* out = buffer;
  if(value[0] == '-') *out++ = '-';
  for(int i = 1; i <= 9; ++i) {
    if(value[i] == ' ') continue;
    *out++ = value[i] == 'O' ? '0' : value[i];
  }
  *out++ = 'e';
  *out++ = value[11] == '-' ? '-' : '+';
  *out++ = value[12] == 'O' ? '0' : value[12];
  *out++ = value[13] == 'O' ? '0' : value[13];
  *out = 0;
  return mk_math::atof(buffer);
}

mk61_ref::Ref reference_for(const Entry& entry) {
  if(!entry.is_stack) return {mk61_ref::Kind::R, (u8) entry.index};
  switch((stack) entry.index) {
    case stack::X: return {mk61_ref::Kind::X, 0};
    case stack::Y: return {mk61_ref::Kind::Y, 0};
    case stack::Z: return {mk61_ref::Kind::Z, 0};
    case stack::T: return {mk61_ref::Kind::T, 0};
    default: fail(entry, "X1 has no reference-language name");
  }
}

void check(const Entry& entry, const Word& word) {
  fixture(entry, word);
  std::array<u8, SIZE_RING_M> before;
  std::memcpy(before.data(), ringM, sizeof(ringM));

  char text[15] = {};
  formatted(entry, text, TERMINAL_SYMBOLS);
  double strict_expected = sentinel();
  const bool strict_ok = terminal_core::parse_mk_display_value(text, strict_expected);

  double fast = sentinel();
  const bool fast_ok = try_read(entry, fast);
  if(fast_ok != canonical(word)) fail(entry, "fast-path acceptance changed");
  if(!fast_ok && mk_math::binary64_bits(fast) != SENTINEL_BITS)
    fail(entry, "rejected fast read changed output", fast, sentinel());
  if(fast_ok && (!strict_ok ||
      mk_math::binary64_bits(fast) != mk_math::binary64_bits(strict_expected)))
    fail(entry, "fast read differs from strict display parser", fast, strict_expected);

  // This is IF's complete numeric-read policy: try the shared numeric reader,
  // then use the real formatter and unchanged strict display parser.
  double strict_actual = sentinel();
  bool actual_ok = try_read(entry, strict_actual);
  if(!actual_ok) {
    formatted(entry, text, TERMINAL_SYMBOLS);
    actual_ok = terminal_core::parse_mk_display_value(text, strict_actual);
  }
  if(actual_ok != strict_ok ||
     mk_math::binary64_bits(strict_actual) != mk_math::binary64_bits(strict_expected))
    fail(entry, "full strict fallback changed status/value", strict_actual, strict_expected);

  // X1 is terminal-only. All remaining entries also exercise the real
  // reference-language reader and its intentionally different legacy parser.
  if(!entry.is_stack || entry.index != (int) stack::X1) {
    formatted(entry, text, mk61_ref::DISPLAY_SYMBOLS);
    const double expected = legacy_reference_number(text);
    double actual = sentinel();
    if(!mk61_ref::read(reference_for(entry), actual))
      fail(entry, "valid reference read failed");
    if(mk_math::binary64_bits(actual) != mk_math::binary64_bits(expected))
      fail(entry, "reference fallback changed value", actual, expected);
    if(!strict_ok || mk_math::binary64_bits(expected) !=
        mk_math::binary64_bits(strict_expected)) ++permissive_differences;
  }
  if(std::memcmp(before.data(), ringM, sizeof(ringM)))
    fail(entry, "numeric read changed calculator ring");
  ++cases;
  if(fast_ok) ++accepted; else ++rejected;
  if(!strict_ok) ++strict_errors;
}

void test_valid_orders(const std::vector<Entry>& entries) {
  scenario = "canonical orders and mantissas";
  for(const Entry& entry : entries)
    for(int exponent = -99; exponent <= 99; ++exponent)
      for(u32 mantissa : {0U,1U,9U,10U,10000000U,12345678U,50000000U,99999999U})
        for(bool negative : {false, true})
          check(entry, decimal_word(mantissa, exponent, negative));
}

void test_integral_subset(const std::vector<Entry>& entries) {
  scenario = "exhaustive normalized integer subset";
  for(const Entry& entry : entries) {
    for(u32 value = 0; value <= 65535U; ++value)
      for(bool negative : {false, true}) check(entry, integer_word(value, negative));
    for(u32 value : {65536U,99999U,100000U,999999U,1000000U,
                    9999999U,10000000U,99999999U})
      for(bool negative : {false, true}) check(entry, integer_word(value, negative));
  }
}

void test_control_nibbles(const std::vector<Entry>& entries) {
  scenario = "all sign/order nibble combinations";
  for(const Entry& entry : entries) {
    Word word = decimal_word(12345678U, 0, false);
    for(unsigned encoded = 0; encoded < 65536U; ++encoded) {
      for(unsigned cell = 0; cell < 4; ++cell)
        word[8+cell] = (u8) ((encoded >> (cell*4)) & 15U);
      check(entry, word);
    }
  }
}

void test_byte_cells(const std::vector<Entry>& entries) {
  scenario = "all full-byte cell mutations";
  for(const Entry& entry : entries)
    for(const Word original : {decimal_word(0, 0, false),
                              decimal_word(10000000U, 0, false),
                              decimal_word(12345678U, -99, true),
                              decimal_word(99999999U, 99, true)})
      for(usize cell = 0; cell < original.size(); ++cell) {
        Word word = original;
        for(unsigned value = 0; value < 256; ++value) {
          word[cell] = (u8) value;
          check(entry, word);
        }
      }
}

void test_random_words(const std::vector<Entry>& entries) {
  scenario = "deterministic multicell and decimal words";
  for(unsigned sample = 0; sample < 100000U; ++sample) {
    const Entry& entry = entries[random_word() % entries.size()];
    Word word;
    if(sample % 3 == 0) {
      word = decimal_word(random_word() % 100000000U,
          (int) (random_word() % 199U) - 99, (random_word() & 1) != 0);
    } else {
      for(u8& cell : word) cell = (u8) (random_word() & (sample & 1 ? 15U : 255U));
    }
    check(entry, word);
  }
}

void test_invalid_entries() {
  scenario = "invalid entries and RF availability";
  // stack is an unfixed enum with enumerators 0..4. Values 5..7 are in its
  // language-defined representation range but are not calculator registers.
  // Casting -1/255 to that enum would itself be undefined, not a reader test.
  for(const Entry entry : {Entry{false,-2147483647}, Entry{false,-1},
                          Entry{false,16}, Entry{false,255}, Entry{false,2147483647},
                          Entry{true,5}, Entry{true,6}, Entry{true,7}}) {
      double value = sentinel();
      std::array<u8, SIZE_RING_M> before;
      std::memcpy(before.data(), ringM, sizeof(ringM));
      if(try_read(entry, value) || mk_math::binary64_bits(value) != SENTINEL_BITS)
        fail(entry, "invalid index accepted or changed output", value, sentinel());
      if(std::memcmp(before.data(), ringM, sizeof(ringM)))
        fail(entry, "invalid read changed calculator ring");
  }
  if(!expanded) {
    double value = sentinel();
    if(mk61_ref::try_read_register_number(15, value) ||
       mk_math::binary64_bits(value) != SENTINEL_BITS)
      fail({false,15}, "unavailable RF fast read changed output", value, sentinel());
    if(mk61_ref::read({mk61_ref::Kind::R,15}, value) ||
       mk_math::binary64_bits(value) != SENTINEL_BITS)
      fail({false,15}, "unavailable RF reference read changed output", value, sentinel());
  }
}

} // namespace

int main() {
  for(bool mode : {false, true}) {
    expanded = mode;
    core_61::set_expanded_program_mode(mode);
    for(u8& cell : ringM) cell = (u8) random_word();
    std::vector<Entry> entries;
    for(int reg = 0; reg < (mode ? 16 : 15); ++reg) entries.push_back({false,reg});
    for(int reg = (int) stack::X1; reg <= (int) stack::T; ++reg)
      entries.push_back({true,reg});
    test_invalid_entries();
    test_valid_orders(entries);
    test_integral_subset(entries);
    test_control_nibbles(entries);
    test_byte_cells(entries);
    test_random_words(entries);
  }
  if(!accepted || !rejected || !strict_errors || !permissive_differences) {
    std::fputs("FAIL differential fixture did not exercise both parsers and fallback\n", stderr);
    return 1;
  }
  std::printf("mk61 numeric reader backend=%d: %llu cases, fast=%llu fallback=%llu "
      "strict_errors=%llu permissive_differences=%llu; exact binary64/status/output/ring PASS\n",
      MK61_MATH_BACKEND, (unsigned long long) cases, (unsigned long long) accepted,
      (unsigned long long) rejected, (unsigned long long) strict_errors,
      (unsigned long long) permissive_differences);
}
