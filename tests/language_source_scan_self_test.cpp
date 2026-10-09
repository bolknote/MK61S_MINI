#include "language_source_scan.hpp"
#include <assert.h>
#include <stdio.h>
#include <vector>

static size_t reference(const uint8_t* p, size_t n) {
  size_t at = 0;
  while(at < n && p[at] != '\r' && p[at] != '\n') ++at;
  return at;
}
static void check(const uint8_t* p, size_t n) {
  assert(language_vm::source_scan::line_end(p, n) == reference(p, n));
}
int main() {
  check(nullptr, 0);
  // All adjacent byte pairs and all lanes catch false delimiters caused by
  // borrow/carry, zero bytes or high M8 bytes next to CR/LF.
  for(unsigned a = 0; a < 256; ++a) for(unsigned b = 0; b < 256; ++b) {
    for(unsigned lane = 0; lane < 4; ++lane) {
      uint8_t p[] = {0, 1, 0x80, 0xFF, '\r', '\n', 0, 1};
      p[lane] = (uint8_t)a; p[lane + 1] = (uint8_t)b;
      check(p, sizeof(p));
#if defined(LANGUAGE_VM_TEST_DSP_SCAN)
      uint32_t word, expected = 0;
      __builtin_memcpy(&word, p, sizeof(word));
      for(unsigned i = 0; i < 4; ++i)
        if(p[i] == '\r' || p[i] == '\n') expected |= 0xFFU << (8 * i);
      assert(language_vm::source_scan::line_mask(word) == expected);
#endif
    }
  }
  uint32_t random = 0x61F411;
  for(unsigned alignment = 0; alignment < 4; ++alignment) {
    for(size_t length = 0; length <= 3584; ++length) {
      // The allocation ends EXACTLY at source+length: ASan detects tail
      // overreads, including absent delimiters and unaligned short ranges.
      std::vector<uint8_t> bytes(length + alignment + (length == 0));
      uint8_t* p = bytes.data() + alignment;
      for(size_t i = 0; i < length; ++i) {
        random ^= random << 13; random ^= random >> 17; random ^= random << 5;
        uint8_t c = (uint8_t)random;
        p[i] = c == '\r' || c == '\n' ? (uint8_t)'x' : c;
      }
      check(p, length);
      const size_t offsets[] = {0, length / 2, length ? length - 1 : 0};
      for(size_t at : offsets) if(at < length) {
        const uint8_t previous = p[at];
        p[at] = '\r'; check(p, length);
        p[at] = '\n'; check(p, length);
        if(at + 1 < length) {
          const uint8_t next = p[at + 1];
          p[at] = '\r'; p[at + 1] = '\n'; check(p, length);
          p[at + 1] = next;
        }
        p[at] = previous;
      }
    }
  }
  puts("Source CR/LF scan: all byte-pair lanes, M8, alignments and exact tails PASS");
}
