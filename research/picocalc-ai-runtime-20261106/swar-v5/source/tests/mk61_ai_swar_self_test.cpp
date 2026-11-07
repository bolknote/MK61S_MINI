#include "mk61_ai_swar.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <initializer_list>
using namespace mk61ai;
namespace {
int oracle(const std::uint8_t *w, const std::int8_t *x) {
  int sum = 0;
  for (unsigned i = 0; i < 32; ++i) sum += (int((w[i / 2] >> (4 * (i & 1))) & 15) - 8) * int(x[i]);
  return sum;
}
std::uint32_t rng = 0x61b200U;
std::uint32_t random_word() { rng ^= rng << 13;rng ^= rng >> 17;rng ^= rng << 5;return rng; }
}
int main() {
  unsigned exhaustive = 0, groups = 0;
  for (unsigned a = 0; a < 16; ++a)
    for (unsigned b = 0; b < 16; ++b)
      for (int x = -128; x <= 127; ++x)
        for (int y = -128; y <= 127; ++y) {
          const auto product = (a + (b << 16)) * swar::pair(std::int8_t(x), std::int8_t(y));
          assert(swar::rounded_high(product) == int(a) * x + int(b) * y);++exhaustive;
        }
  std::uint8_t raw[17];std::int8_t input[32];std::uint32_t packed[16];
  auto check = [&]() {
    const int sum = swar::prepare32(input, packed);
    assert(swar::dot32(raw + 1, packed, sum) == oracle(raw + 1, input));++groups;
  };
  for (int value : {-128, -127, -1, 0, 1, 126, 127})
    for (unsigned byte : {0U, 0x0fU, 0xf0U, 0xffU, 0x88U, 0x7fU}) {
      std::memset(raw, byte, sizeof(raw));
      for (unsigned i = 0; i < 32; ++i) input[i] = std::int8_t(value);
      check();
      for (unsigned i = 0; i < 32; ++i) input[i] = std::int8_t(i & 1 ? value : -1);
      check();
    }
  for (unsigned n = 0; n < 200000; ++n) {
    for (auto &v : raw) v = std::uint8_t(random_word());
    for (auto &v : input) v = std::int8_t(int(random_word() & 255) - 128);
    check();
  }
  std::printf("SWAR PASS: %u exhaustive signed lane/weight combinations; %u full32 groups, carry boundaries, negative lanes, unaligned weights; exact scalar INT8 sums.\n", exhaustive, groups);
}
