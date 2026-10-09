#define MK61_MEMORY_TEST_WORDS
#include "memory_aux_candidates.hpp"
#include <cassert>
#include <cstring>
#include <cstdio>
#include <vector>
#include <sys/mman.h>
#include <unistd.h>
int main() {
  assert(memory_aux::move_word(nullptr, nullptr, 0) == nullptr);
  assert(memory_aux::fill_word(nullptr, -1, 0) == nullptr);
  for(unsigned n = 0; n <= 513; ++n) for(unsigned sa = 0; sa < 4; ++sa) {
    for(int shift = -32; shift <= 32; ++shift) {
      unsigned char actual[640], expected[640];
      for(unsigned i = 0; i < 640; ++i) actual[i] = expected[i] = (unsigned char) (i * 37);
      assert(memory_aux::move_word(actual + 48 + sa + shift, actual + 48 + sa, n) == actual + 48 + sa + shift);
      std::memmove(expected + 48 + sa + shift, expected + 48 + sa, n);
      assert(std::memcmp(actual, expected, sizeof(actual)) == 0);
    }
    for(int value : {0, -1, 0x1234}) {
      unsigned char actual[520], expected[520];
      std::memset(actual, 0xA7, sizeof(actual)); std::memset(expected, 0xA7, sizeof(expected));
      assert(memory_aux::fill_word(actual + sa, value, n) == actual + sa);
      std::memset(expected + sa, value, n);
      assert(std::memcmp(actual, expected, sizeof(actual)) == 0);
    }
  }
  for(unsigned n : {1024U, 4096U, 8192U, 32769U}) for(int shift : {-513, -17, -1, 0, 1, 17, 513}) {
    std::vector<unsigned char> actual(n + 1100), expected(n + 1100);
    for(unsigned i = 0; i < actual.size(); ++i) actual[i] = expected[i] = (unsigned char) (i * 13);
    memory_aux::move_word(actual.data() + 550 + shift, actual.data() + 550, n);
    std::memmove(expected.data() + 550 + shift, expected.data() + 550, n);
    assert(actual == expected);
  }
  auto sign = [](int n) { return (n > 0) - (n < 0); };
  for(unsigned n = 0; n <= 513; ++n) for(unsigned sa = 0; sa < 4; ++sa) for(unsigned ta = 0; ta < 4; ++ta) {
    std::vector<char> a(n + sa + 2), b(n + ta + 2);
    char* x = a.data() + sa; char* y = b.data() + ta;
    for(unsigned i = 0; i < n; ++i) x[i] = y[i] = (char) (1 + i * 37 % 255);
    x[n] = y[n] = x[n + 1] = y[n + 1] = 0;
    assert(memory_aux::length_unrolled(x) == n);
    for(unsigned limit : {0U, 1U, n / 2, n, n + 3}) {
      assert(memory_aux::bounded_length_unrolled(x, limit) == strnlen(x, limit));
      assert(sign(memory_aux::bounded_compare_unrolled(x, y, limit)) == sign(std::strncmp(x, y, limit)));
    }
    for(unsigned at = 0; at <= n; ++at) {
      const char saved = y[at]; y[at] = (char) ((unsigned char) saved ^ 0x81);
      assert(sign(memory_aux::string_compare_unrolled(x, y)) == sign(std::strcmp(x, y)));
      assert(sign(memory_aux::bounded_compare_unrolled(x, y, n + 1)) == sign(std::strncmp(x, y, n + 1)));
      y[at] = saved;
    }
  }
  const size_t page = (size_t) sysconf(_SC_PAGESIZE);
  auto* a = (unsigned char*) mmap(nullptr, page * 3, PROT_NONE, MAP_PRIVATE | MAP_ANON, -1, 0);
  assert(a != MAP_FAILED && mprotect(a + page, page, PROT_READ | PROT_WRITE) == 0);
  auto* b = (unsigned char*) mmap(nullptr, page * 3, PROT_NONE, MAP_PRIVATE | MAP_ANON, -1, 0);
  assert(b != MAP_FAILED && mprotect(b + page, page, PROT_READ | PROT_WRITE) == 0);
  for(unsigned n = 0; n <= 513; ++n) for(unsigned gap : {1U, 2U, 3U, 4U, 15U, 16U, 17U}) {
    unsigned char* end = a + page * 2;
    for(unsigned i = 0; i < n + gap; ++i) (end - n - gap)[i] = (unsigned char) (i * 31);
    memory_aux::move_word(end - n, end - n - gap, n); // destination ends at guard
    for(unsigned i = 0; i < n; ++i) assert((end - n)[i] == (unsigned char) (i * 31));
    memory_aux::fill_word(end - n, -1, n);
    for(unsigned i = 0; i < n; ++i) assert((end - n)[i] == 255);
  }
  for(unsigned n = 0; n <= 513; ++n) {
    char* s = (char*) (a + page * 2 - n - 1);
    char* t = (char*) (b + page * 2 - n - 1);
    for(unsigned i = 0; i < n; ++i) s[i] = t[i] = 'X';
    s[n] = t[n] = 0;
    assert(memory_aux::length_unrolled(s) == n);
    assert(memory_aux::bounded_length_unrolled(s, n + 8) == n);
    // Separate guarded objects prevent equal-pointer folding from hiding
    // an overread at the terminator during comparison.
    assert(memory_aux::string_compare_unrolled(s, t) == 0);
    assert(memory_aux::bounded_compare_unrolled(s, t, n + 8) == 0);
    if(n) {
      t[n - 1] = (char) 0xFF;
      assert(memory_aux::string_compare_unrolled(s, t) < 0);
      assert(memory_aux::bounded_compare_unrolled(s, t, n + 8) < 0);
    }
  }
  assert(memory_aux::bounded_length_unrolled((char*)a, 0) == 0);
  assert(memory_aux::bounded_compare_unrolled((char*)a, (char*)b, 0) == 0);
  assert(munmap(a, page * 3) == 0);
  assert(munmap(b, page * 3) == 0);
  std::puts("Auxiliary memory candidates: overlap, alignments, return, value truncation and exact guard tails PASS");
}
